"""
engine/recommender.py
=====================
The recommendation service — the orchestration layer the API talks to.

  1. foods_for_goal(goal)      -> ranked, explained foods for a goal
  2. explain(food, goal)       -> the strongest food -> nutrient -> goal path,
                                  plus every route's contribution
  3. similar_foods(food)       -> nutritionally similar foods / substitutes

Ranking uses engine/scoring.py: what one realistic portion delivers, as a
share of daily need, adjusted for bioavailability, combined over all routes
to the goal, and penalised for sodium / saturated fat / sugars. Scores are
precomputed once per goal at startup, so a query is a walk down a sorted
list. The reverse-Dijkstra pass from each goal (edge cost = -log strength)
supplies the strongest route for each food's explanation.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

from .graph import FeedForwardGraph
from .portions import portion_for
from .schema import Food
from .algorithms import (dijkstra_reverse, reconstruct_path_reverse,
                         cosine_similarity, k_shortest_paths, reconstruct_path,
                         dijkstra)


# ---------------------------------------------------------------------------
# Dietary filtering (kept from the original, tightened)
# ---------------------------------------------------------------------------
SUGAR_LOW = 5.0
PROTEIN_HIGH = 15.0

# Keywords match a whole word or its plural ("sardine" / "sardines"), never
# part of a word: "ham" must not match "champignon", "pate" not "pates"
# (pasta), "porc" not "porcini". A trailing "*" marks a stem matched as a
# prefix ("anchov*" → anchovy, anchovies). English (USDA) and French
# (OpenFoodFacts) names, plus USDA flesh categories.
_MEAT_FISH = (
    "meat", "meats", "fish", "beef", "pork", "chicken", "viande", "poisson", "boeuf",
    "porc", "thon", "tuna", "atun", "saumon", "salmon", "sardine", "maquereau",
    "anchois", "anchov*", "morue", "cod", "cabillaud", "colin", "merlu", "hareng",
    "herring", "mackerel", "trout", "truite", "crab", "crevette", "shrimp",
    "prawn", "lobster", "homard", "surimi", "jambon", "ham", "hamburger", "bacon",
    "lard", "lardons",
    "poulet", "dinde", "turkey", "lamb", "agneau", "veau", "veal", "bison",
    "venison", "duck", "canard", "goose", "goat", "rabbit", "lapin", "caribou",
    "elk", "moose", "deer", "bear", "boar", "sanglier", "poultry", "game",
    "sausage", "saucisse", "saucisson", "salami", "chorizo", "pepperoni",
    "frankfurter", "bologna", "liver", "foie", "kidney", "rognon", "spleen",
    "giblets", "tripe", "heart", "tongue", "sweetbread", "gelatin", "gelatine",
    "snail", "escargot", "mollus*", "clam", "oyster", "huitre", "mussel",
    "scallop", "squid", "calamar", "octopus", "poulpe", "eel", "roe", "caviar",
    "rillettes", "terrine", "frog", "halibut", "pollock", "haddock",
    "tilapia", "carp", "catfish", "swordfish", "whitefish", "finfish", "shellfish",
    "seal", "whale", "walrus", "sea lion", "cockle", "conch", "abalone", "whelk",
    "periwinkle", "tunicate", "sea urchin", "sea cucumber", "jellyfish", "krill",
    "chiton", "gumboots", "limpet", "animal", "steak", "sirloin", "mutton",
    "brisket", "tenderloin", "meatball", "meatloaf", "burger", "cheeseburger",
    "nugget", "gyro", "kebab", "carne", "pollo", "jamon", "veal", "oxtail",
)
_ANIMAL_NOT_VEGAN = (
    "dairy", "milk", "cheese", "yogurt", "yoghurt", "lait", "fromage", "yaourt",
    "skyr", "kefir", "cream", "creme", "butter", "beurre", "buttermilk", "whey",
    "casein", "ghee", "egg", "oeuf", "honey", "miel", "mozzarella", "parmesan",
    "ricotta",
)
# Phrases removed before matching because they contain a keyword but are not
# the animal product ("lamb's lettuce", "coconut milk", "eggplant", ...).
_NOT_ANIMAL = (
    "lambs lettuce", "lamb s lettuce", "lambsquarters", "coconut meat", "nut meat",
    "meatless", "meat extender", "meat substitute", "meat analog", "crab apple",
    "crabapple", "eggplant", "honeydew", "butternut", "butterbur", "butterhead",
    "peanut butter", "cocoa butter", "nut butter", "almond butter", "apple butter",
    "shea butter", "coconut milk", "coconut cream", "almond milk", "soy milk",
    "soymilk", "oat milk", "rice milk", "lait de coco", "creme de coco",
    "lait d amande", "lait de soja", "boisson vegetale", "cream of tartar",
    "heart of palm", "hearts of palm", "artichoke hearts", "coeur de palmier",
    "beurre de cacahuete", "milk thistle", "creme de marrons", "kidney bean",
    "haricot rouge", "bear s garlic", "animal crackers", "hearty", "bearnaise",
    "kidney beans", "beans kidney", "goat cheese", "goats cheese", "cheese goat",
    "goat milk", "goats milk", "milk goat", "veggie burger", "vegetable burger",
    "meatless burger", "bean burger", "soy burger", "burger vegetal",
)
# Mixed dishes and branded restaurant items often do not name their meat
# ("DOUBLE QUARTER POUNDER"). For a dietary restriction a false "yes" is
# worse than a false "no", so in these categories a food passes vegetarian /
# vegan only if its name says so explicitly.
_UNCERTAIN_CATEGORIES = (
    "fast foods", "restaurant foods", "meals, entrees, and side dishes",
    "american indian/alaska native foods", "soups, sauces, and gravies",
    "microwave meals", "plats prepares", "prepared meals", "sandwiches",
)
# Explicit claims only: "Chili with beans" and "Soup, vegetable" can still be
# made with beef or chicken stock.
_VEGETARIAN_MARKERS = (
    "vegetarian", "vegan", "veggie", "meatless", "without meat", "sans viande",
    "vegetarien", "vegetalien", "vegetal", "margherita",
)
_VEGAN_MARKERS = ("vegan", "vegetalien", "vegetal", "plant-based", "plant based")
_VEGAN_UNSURE = ("shake", "milkshake", "smoothie", "custard", "pudding", "mayonnaise")
# French words that differ from a meat word only by an accent, which _norm
# strips: "pâté" (meat) vs "pâtes" (pasta), "moules" (mussels) vs "moulé"
# (moulded cheese). Matched on the accented, lowercase name.
_MEAT_ACCENTED = ("pâté", "pâtés", "moule", "moules")
# The taxonomy has no infant demographic. Infant formulas and baby foods are
# fortified per 100 g in a way that outranks foods an adult would eat. They
# stay searchable; they are not recommendations for the goals we ship.
_INFANT = ("babyfood", "baby food", "infant formula", "infant")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text) if w]


def _mentions(text: str, keywords: tuple[str, ...]) -> bool:
    """True if ``text`` contains a keyword as a word (or plural, or stem*)."""
    flat = f" {' '.join(_words(text))} "
    for phrase in _NOT_ANIMAL:
        flat = flat.replace(f" {phrase} ", " ")
    words = set(flat.split())
    for k in keywords:
        if " " in k:
            if f" {k} " in flat or f" {k}s " in flat:
                return True
        elif k.endswith("*"):
            stem = k[:-1]
            if any(w.startswith(stem) for w in words):
                return True
        elif k in words or f"{k}s" in words or f"{k}es" in words or f"{k}x" in words:
            return True
    return False


# Marine-mammal products cannot be sold in the EU (products of all pinnipeds —
# seals, sea lions, walrus: Regulation (EC) No 1007/2009; cetaceans are
# strictly protected). USDA lists them under Alaska Native foods; they stay
# searchable but are never recommended here.
_NOT_SOLD_IN_EU = ("seal", "oogruk", "whale", "walrus", "beluga", "narwhal", "sea lion")
# FeedForward recommends foods. Fish and cod-liver oils are sold as food
# supplements in the EU (Directive 2002/46/EC) and are dosed, not eaten.
_SUPPLEMENTS = ("fish oil", "cod liver oil", "huile de foie", "dietary supplement",
                "complement alimentaire")
# Listed raw, these are unsafe: pokeweed shoots are toxic without repeated
# boiling, raw taro leaves carry irritant calcium oxalate raphides, raw
# cassava releases cyanide.
_UNSAFE_AS_LISTED = ("pokeberry", "pokeweed", "poke shoots")
_UNSAFE_RAW = ("taro leaves", "cassava")


def is_infant_food(food: Food) -> bool:
    text = _norm(food.name + " " + food.category)
    return any(k in text for k in _INFANT)


def is_not_sold_in_eu(food: Food) -> bool:
    flat = f" {' '.join(_words(_norm(food.name)))} "
    return any(f" {k} " in flat or f" {k}s " in flat for k in _NOT_SOLD_IN_EU)


def is_supplement(food: Food) -> bool:
    name = " ".join(_words(_norm(food.name)))
    return any(k in name for k in _SUPPLEMENTS)


def is_unsafe_as_listed(food: Food) -> bool:
    name = " ".join(_words(_norm(food.name)))
    if any(k in name for k in _UNSAFE_AS_LISTED):
        return True
    return "raw" in name.split() and any(k in name for k in _UNSAFE_RAW)


# Product decision (2026-09-26): USDA's "American Indian/Alaska Native Foods"
# (beaver, tunicates, Navajo stews, wild-harvested greens) are traditional
# foods of North American communities, not part of the EU food supply the app
# advises on. They stay searchable, but are not recommended.
_SEARCH_ONLY_CATEGORIES = ("american indian/alaska native foods",)


def is_search_only_category(food: Food) -> bool:
    category = _norm(food.category)
    return any(c in category for c in _SEARCH_ONLY_CATEGORIES)


def is_industrial_ingredient(food: Food) -> bool:
    """
    Ingredients for food manufacture rather than foods people buy and eat:
    defatted seed/soy flours and meals (press-cake by-products), cottonseed
    flour, meal and kernels, and anything USDA labels "industrial".
    """
    words = set(_words(_norm(food.name)))
    if "industrial" in words or "defatted" in words:
        return True
    name = _norm(food.name)
    if "flour" in words and ("low-fat" in name or "low fat" in name or "lowfat" in name):
        return True
    if "cottonseed" in words and words & {"flour", "meal", "kernels"}:
        return True
    return "meal" in words and bool(words & {"seed", "soy", "sesame", "safflower"})


# Product decision (2026-09-26): formulated drinks — drink powders, vitamin
# waters, flavoured "drinks", meal-replacement and sports shakes — meet EU
# claims through added vitamins, often with sugar the data does not report.
# They are treated like supplements: searchable, not recommended.
_FORMULATED_DRINKS = (
    "drink mix", "vitamin water", "meal replacement", "energy drink", "sports drink",
    "fruit punch", "fruit-flavored drink", "flavor drink", "flavored drink",
    "protein shake", "nutritional shake", "meal supplement drink", "high protein shake",
    "powder, prepared", "drink powder", "breakfast type",
)


def is_formulated_drink(food: Food) -> bool:
    name = _norm(food.name)
    if any(k in name for k in _FORMULATED_DRINKS):
        return True
    words = set(_words(name))
    return ("beverages" in words or "drink" in words) and "powder" in words


def is_excluded_food(food: Food) -> bool:
    """
    Never recommended by default: infant foods, products not sold in the EU,
    supplements and formulated drinks, foods unsafe in the form listed,
    industrial ingredients and search-only categories. All stay searchable.
    """
    return (is_infant_food(food) or is_not_sold_in_eu(food)
            or is_supplement(food) or is_formulated_drink(food)
            or is_unsafe_as_listed(food)
            or is_industrial_ingredient(food) or is_search_only_category(food))


# Preparation words dropped when deciding whether two entries are the same
# food ("Lentils, mature seeds, cooked, boiled, without salt" vs "..., raw").
_PREPARATION = (
    "raw", "cooked", "boiled", "braised", "roasted", "fried", "pan-fried", "drained",
    "salt", "simmered", "steamed", "baked", "dry heat", "moist heat", "frozen",
    "canned", "heated", "microwaved", "grilled", "broiled", "stewed", "unprepared",
    "prepared", "solids and liquids", "cru", "cuit",
)


def food_family(name: str) -> str:
    """The food with preparation stripped: first three descriptive parts."""
    parts = [p.strip() for p in _norm(name).split(",")]
    kept = [p for p in parts if p and not any(w in p for w in _PREPARATION)]
    return ", ".join(kept[:3]) or _norm(name)


def satisfies(food: Food, constraint: str) -> bool:
    text = _norm(food.name + " " + food.category)
    if constraint == "low_sugar":
        return food.nutrients.get("sugars", 0) < SUGAR_LOW
    if constraint == "high_protein":
        return food.nutrients.get("proteins", 0) > PROTEIN_HIGH
    if constraint in ("vegetarian", "vegan"):
        accented = set(re.split(r"[^\w]+", unicodedata.normalize(
            "NFC", f"{food.name} {food.category}".lower())))
        if accented & set(_MEAT_ACCENTED):
            return False
        category = _norm(food.category)
        name = re.sub(r"\b(no|without|sans)\s+\w+", " ", _norm(food.name))
        claims_vegetarian = any(m in name for m in _VEGETARIAN_MARKERS)
        claims_vegan = any(m in name for m in _VEGAN_MARKERS)
        if any(c in category for c in _UNCERTAIN_CATEGORIES) and not claims_vegetarian:
            return False
    if constraint == "vegetarian":
        # An explicit claim covers meat analogues ("burger végétarien").
        return claims_vegetarian or not _mentions(text, _MEAT_FISH)
    if constraint == "vegan":
        if claims_vegan:
            return True
        return not _mentions(text, _MEAT_FISH + _ANIMAL_NOT_VEGAN + _VEGAN_UNSURE)
    if constraint == "low_sodium":
        return food.nutrients.get("sodium", 0) < 120
    if constraint == "high_fiber":
        return food.nutrients.get("fiber", 0) > 6
    return True


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------
@dataclass
class PathStep:
    node_id: str
    name: str
    node_type: str


@dataclass
class Explanation:
    food_id: str
    food_name: str
    goal: str
    total_cost: float             # -log(strength) of the strongest path
    steps: list[PathStep]
    nutrient: str = ""
    evidence: str = ""
    evidence_label: str = ""
    consumer_label: str = ""
    citations: list[str] = field(default_factory=list)
    note: str = ""
    # What one portion delivers along every route to the goal, strongest first.
    portion_g: float = 0.0
    portion_group: str = ""
    contributions: list[dict] = field(default_factory=list)
    penalties: list[dict] = field(default_factory=list)
    pairing: str = ""
    # True when ``note`` is the wording of an authorised EU health claim, the
    # only kind of health wording the app may present as a claim.
    eu_claim: bool = False
    evidence_source: str = ""


@dataclass
class Recommendation:
    food_id: str
    food_name: str
    category: str
    score: float                 # goal score in [0, 1], higher = better
    match: float                 # the same score on 0-100
    explanation: Explanation | None = None


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------
class Recommender:
    def __init__(self, graph: FeedForwardGraph, foods: list[Food],
                 edge_meta: dict | None = None) -> None:
        from .scoring import GoalScorer
        self.graph = graph
        self.foods = foods
        self.food_by_id = {f.id: f for f in foods}
        edge_meta = edge_meta or {}
        self.edge_meta = edge_meta.get("edges", {})
        self.scorer: GoalScorer = edge_meta.get("scorer") or GoalScorer(
            [{"nutrient": k.split("->")[0], "goal": k.split("->")[1],
              "weight": v.get("base_weight", 0.5), "type": v.get("edge_type", "positive")}
             for k, v in self.edge_meta.items()])
        # Reverse Dijkstra from every goal: pred gives each food's strongest
        # route (the explanation); dist is -log of that route's strength.
        self._goal_dist: dict[str, dict[str, float]] = {}
        self._goal_pred: dict[str, dict[str, str | None]] = {}
        # Goal score per food (all routes combined, penalties applied) and the
        # food ids sorted by it. A query is a walk down this list.
        self._scores: dict[str, dict[str, float]] = {}
        self._ranked: dict[str, list[str]] = {}
        # Other demographics are scored on first use and cached: the DRIs
        # change, so shares of need, UL checks and the ranking change too.
        self._goal_edges: list[dict] | None = edge_meta.get("goal_edges")
        self._scorers = {self.scorer.demo: self.scorer}
        self._demo_scores: dict[tuple, dict[str, float]] = {}
        self._demo_ranked: dict[tuple, list[str]] = {}
        self._precompute_goals()

    # -- precompute ---------------------------------------------------------
    def _precompute_goals(self) -> None:
        for goal in self.graph.nodes_of_type("goal"):
            dist, pred = dijkstra_reverse(self.graph, goal)
            self._goal_dist[goal] = dist
            self._goal_pred[goal] = pred
            scores: dict[str, float] = {}
            for food in self.foods:
                if dist.get(food.id, math.inf) == math.inf:
                    continue
                value = self.scorer.score_value(food, goal)
                if value > 0:
                    scores[food.id] = value
            self._scores[goal] = scores
            self._ranked[goal] = self._order(scores)

    def refresh(self) -> None:
        self._goal_dist.clear()
        self._goal_pred.clear()
        self._scores.clear()
        self._ranked.clear()
        self._precompute_goals()

    # -- helpers ----------------------------------------------------------
    def _cost_to_goal(self, food_id: str, goal: str) -> float:
        return self._goal_dist.get(goal, {}).get(food_id, math.inf)

    # Everyday foods first: order by goal score x (FLOOR + (1 - FLOOR) x
    # familiarity). An unfamiliar food keeps at least FLOOR of its weight, so a
    # uniquely good one can still appear; its displayed score is unchanged.
    FAMILIARITY_FLOOR = 0.5

    def _order(self, scores: dict[str, float]) -> list[str]:
        floor = self.FAMILIARITY_FLOOR

        def key(fid: str):
            fam = self.food_by_id[fid].familiarity
            return (-scores[fid] * (floor + (1 - floor) * fam), fid)
        return sorted(scores, key=key)

    def scorer_for(self, demo=None):
        """The GoalScorer for a demographic (default: the engine's)."""
        from .scoring import GoalScorer
        if demo is None or demo == self.scorer.demo or self._goal_edges is None:
            return self.scorer
        if demo not in self._scorers:
            self._scorers[demo] = GoalScorer(self._goal_edges, demo=demo)
        return self._scorers[demo]

    def _is_default(self, demo) -> bool:
        return self.scorer_for(demo) is self.scorer

    def ranked(self, goal: str, demo=None) -> list[str]:
        if self._is_default(demo):
            return self._ranked.get(goal, [])
        key = (demo, goal)
        if key not in self._demo_ranked:
            scorer = self.scorer_for(demo)
            dist = self._goal_dist.get(goal, {})
            scores = {}
            for food in self.foods:
                if dist.get(food.id, math.inf) == math.inf:
                    continue
                value = scorer.score_value(food, goal)
                if value > 0:
                    scores[food.id] = value
            self._demo_scores[key] = scores
            self._demo_ranked[key] = self._order(scores)
        return self._demo_ranked[key]

    def goal_score(self, food_id: str, goal: str, demo=None) -> float:
        if self._is_default(demo):
            return self._scores.get(goal, {}).get(food_id, 0.0)
        self.ranked(goal, demo)
        return self._demo_scores[(demo, goal)].get(food_id, 0.0)

    @staticmethod
    def _match(score: float) -> float:
        return round(100.0 * score, 1)

    def _eligible(self, food: Food, constraints: list[str]) -> bool:
        if is_excluded_food(food):
            return False
        return all(satisfies(food, c) for c in constraints)

    # -- core queries -----------------------------------------------------
    def foods_for_goal(self, goal: str, constraints: list[str] | None = None,
                       k: int = 10, explain: bool = True,
                       diversify: bool = True, demo=None) -> list[Recommendation]:
        """
        Top-k foods for a goal. With ``diversify`` (the default) the list shows
        one entry per food family (spleen raw / spleen braised count once) and
        at most ``max(2, ceil(k / 4))`` per portion group (ten breakfast
        cereals in a row is one answer, not ten). Held-back foods fill the
        list only if the corpus runs out of alternatives. Order within the
        accepted foods is always by score.
        """
        constraints = constraints or []
        ranked = self.ranked(goal, demo)
        if not ranked:
            return []
        group_cap = max(2, math.ceil(k / 4))
        families: set[str] = set()
        groups: dict[str, int] = {}
        chosen: list[str] = []
        held: list[str] = []
        for food_id in ranked:
            food = self.food_by_id.get(food_id)
            if food is None or not self._eligible(food, constraints):
                continue
            if diversify:
                family = food_family(food.name)
                group = portion_for(food).group
                if family in families or groups.get(group, 0) >= group_cap:
                    held.append(food_id)
                    continue
                families.add(family)
                groups[group] = groups.get(group, 0) + 1
            chosen.append(food_id)
            if len(chosen) >= k:
                break
        chosen.extend(held[: max(0, k - len(chosen))])
        position = {fid: i for i, fid in enumerate(ranked)}
        chosen.sort(key=lambda fid: position[fid])

        out: list[Recommendation] = []
        for food_id in chosen:
            food = self.food_by_id[food_id]
            score = self.goal_score(food_id, goal, demo)
            rec = Recommendation(
                food_id=food.id, food_name=food.name, category=food.category,
                score=round(score, 4), match=self._match(score))
            if explain:
                rec.explanation = self.explain(food.id, goal, demo)
            out.append(rec)
        return out

    def explain(self, food_id: str, goal: str, demo=None) -> Explanation | None:
        """
        The strongest food -> nutrient -> goal path (from the reverse-Dijkstra
        predecessors) with its evidence, plus every other route's contribution
        and any penalty, so the score can be traced term by term.
        """
        pred = self._goal_pred.get(goal)
        if not pred or food_id not in self.food_by_id:
            return None
        path = reconstruct_path_reverse(pred, goal, food_id)
        if not path or path[-1] != goal:
            return None
        steps = [PathStep(n, self.graph.display_name(n),
                          self.graph.node_type.get(n, "")) for n in path]
        food = self.food_by_id[food_id]
        nutrient = path[1] if len(path) >= 3 else ""
        meta = self.edge_meta.get(f"{nutrient}->{goal}", {})
        detail = self.scorer_for(demo).score(food, goal)
        if not self._is_default(demo) and detail.contributions:
            # The strongest route can change with the DRIs; rebuild it.
            top = detail.contributions[0].nutrient
            path = [food_id, top, goal]
            steps = [PathStep(n, self.graph.display_name(n),
                              self.graph.node_type.get(n, "")) for n in path]
            nutrient = top
            meta = self.edge_meta.get(f"{nutrient}->{goal}", {})
        contributions = [{
            "nutrient": c.nutrient,
            "name": self.graph.display_name(c.nutrient),
            "amount": c.delivery.amount,
            "percent_of_need": c.delivery.percent_of_need,
            "relative_bioavailability": c.delivery.relative_bioavailability,
            "exceeds_upper_limit": c.delivery.exceeds_ul,
            "delivery_strength": round(c.delivery.strength, 4),
            "association": round(c.association, 4),
            "evidence": c.evidence,
            "eu_claim": bool(self.edge_meta.get(f"{c.nutrient}->{goal}", {}).get("eu_claim")),
            "strength": round(c.strength, 4),
        } for c in detail.contributions]
        penalties = [{
            "nutrient": p.nutrient, "share_of_daily_limit": p.share_of_limit,
            "factor": p.factor, "goal_specific": p.goal_specific, "kind": p.kind,
        } for p in detail.penalties if p.factor < 0.999]
        return Explanation(
            food_id=food_id, food_name=food.name, goal=goal,
            total_cost=round(-math.log(detail.contributions[0].strength), 4)
            if detail.contributions else round(self._cost_to_goal(food_id, goal), 4),
            steps=steps, nutrient=nutrient,
            evidence=meta.get("evidence", ""),
            evidence_label=meta.get("evidence_label", ""),
            consumer_label=meta.get("consumer_label", ""),
            citations=meta.get("citations", []),
            note=meta.get("explanation", ""),
            portion_g=portion_for(food).grams,
            portion_group=portion_for(food).group,
            contributions=contributions,
            penalties=penalties,
            pairing=self._pairing_note(food, goal, detail.pairings),
            eu_claim=bool(meta.get("eu_claim")),
            evidence_source=meta.get("evidence_source", ""),
        )

    def _pairing_note(self, food: Food, goal: str, enhancers: list[str]) -> str:
        """An enhancer is worth mentioning only if it acts on this food's form."""
        if "vitamin-c" in enhancers and food.nutrients.get("iron", 0) > 0 \
                and not food.is_animal_source:
            meta = self.edge_meta.get(f"vitamin-c->{goal}", {})
            return ("Pair with a vitamin C source (peppers, citrus, kiwi) to raise "
                    "absorption of this food's plant iron."
                    + (f" {meta['explanation']}" if meta.get("explanation") else ""))
        return ""

    def explain_multi(self, food_id: str, goal: str, k: int = 3) -> list[list[PathStep]]:
        """Top-k distinct explanation paths via Yen's algorithm (forward graph)."""
        paths = k_shortest_paths(self.graph, food_id, goal, k)
        result: list[list[PathStep]] = []
        for _cost, p in paths:
            result.append([PathStep(n, self.graph.display_name(n),
                                    self.graph.node_type.get(n, "")) for n in p])
        return result

    def similar_foods(self, food_id: str, k: int = 5,
                      constraints: list[str] | None = None) -> list[Recommendation]:
        """
        Foods with the most similar nutritional profile (cosine similarity).

        Each dimension is expressed in "days of need" per 100 g (amount / DRI,
        limit nutrients / daily limit, energy / 2000 kcal), so milligrams of
        sodium do not outweigh micrograms of vitamin B12 simply by their unit.
        With ``constraints`` (e.g. ["vegetarian"]) this finds substitutes.
        """
        target = self.food_by_id.get(food_id)
        if target is None:
            return []
        constraints = constraints or []
        vec = self._profile_vector(target)
        sims: list[tuple[float, Food]] = []
        for f in self.foods:
            if f.id == food_id or not self._eligible(f, constraints):
                continue
            s = cosine_similarity(vec, self._profile_vector(f))
            if s > 0:
                sims.append((s, f))
        sims.sort(key=lambda x: (-x[0], x[1].id))
        # The same food with or without salt, raw or boiled, is not an
        # alternative: keep one entry per family, and none of the target's.
        seen = {food_family(target.name)}
        out: list[Recommendation] = []
        for s, f in sims:
            family = food_family(f.name)
            if family in seen:
                continue
            seen.add(family)
            out.append(Recommendation(food_id=f.id, food_name=f.name, category=f.category,
                                      score=round(s, 4), match=round(s * 100, 1)))
            if len(out) >= k:
                break
        return out

    def _profile_vector(self, food: Food) -> dict[str, float]:
        cache = self.__dict__.setdefault("_profile_cache", {})
        if food.id in cache:
            return cache[food.id]
        from .reference import LIMIT_NUTRIENTS, reference_value
        vec: dict[str, float] = {}
        for n, amount in food.nutrients.items():
            if amount <= 0:
                continue
            if n in LIMIT_NUTRIENTS:
                vec[n] = amount / LIMIT_NUTRIENTS[n]
            elif n == "energy-kcal":
                vec[n] = amount / 2000.0
            else:
                ref = reference_value(n, self.scorer.demo)
                if ref and ref.rda_ai > 0:
                    vec[n] = amount / ref.rda_ai
        cache[food.id] = vec
        return vec

    def goals_for_food(self, food_id: str) -> list[dict]:
        """Which goals does this food support, and how strongly? (food's map)"""
        if food_id not in self.food_by_id:
            return []
        out: list[dict] = []
        for goal in self.graph.nodes_of_type("goal"):
            score = self.goal_score(food_id, goal)
            if score <= 0:
                continue
            exp = self.explain(food_id, goal)
            out.append({
                "goal": goal,
                "match": self._match(score),
                "nutrient": exp.nutrient if exp else "",
                "evidence": exp.evidence if exp else "",
                "citations": exp.citations if exp else [],
            })
        out.sort(key=lambda d: d["match"], reverse=True)
        return out

    # ------------------------------------------------------------------
    # Rich scientific profile (density + %DV + anti-nutrients + cautions)
    # ------------------------------------------------------------------
    def food_profile(self, food_id: str, demo=None) -> dict | None:
        """
        Assemble a food's full scientific profile: nutrient contributions as
        % of daily need, nutrient-density score with breakdown, detected
        anti-nutrients, goals supported, and any informational cautions.

        This is the analytical backbone behind the food-detail screen and the
        professional tier.
        """
        from .reference import percent_of_need, DEFAULT_DEMOGRAPHIC, is_limit_nutrient, percent_of_limit
        from .density import density_breakdown
        from .cautions import cautions_for_food

        food = self.food_by_id.get(food_id)
        if not food:
            return None
        demo = demo or DEFAULT_DEMOGRAPHIC

        # Nutrient breakdown with %DV (per 100 g)
        nutrient_rows = []
        for n, amt in food.nutrients.items():
            if amt <= 0:
                continue
            row = {"nutrient": n, "amount": amt}
            if is_limit_nutrient(n):
                row["percent_of_limit"] = percent_of_limit(n, amt)
                row["kind"] = "limit"
            else:
                pct = percent_of_need(n, amt, demo)
                if pct is not None:
                    row["percent_of_need"] = pct
                row["kind"] = "beneficial"
            nutrient_rows.append(row)
        nutrient_rows.sort(key=lambda r: r.get("percent_of_need", 0), reverse=True)

        db = density_breakdown(food, demo)
        cautions = cautions_for_food(food)

        portion = portion_for(food)
        return {
            "food_id": food.id,
            "food_name": food.name,
            "category": food.category,
            "portion_g": portion.grams,
            "portion_group": portion.group,
            "nutri_score": food.nutri_score,
            "nova": food.nova,
            "density_score": db.score,
            "density_breakdown": {
                "qualifying_sum": db.qualifying_sum,
                "limiting_sum": db.limiting_sum,
                "top_contributors": db.top_contributors,
            },
            "anti_nutrients": sorted(food.anti_nutrients or set()),
            "is_animal_source": food.is_animal_source,
            "nutrients": nutrient_rows,
            "goals_supported": self.goals_for_food(food_id),
            "cautions": [
                {"context": c.context, "severity": c.severity,
                 "message": c.message, "disposition": c.disposition,
                 "citations": c.citations}
                for c in cautions
            ],
        }

    def analyze_meal(self, food_ids: list[str], demo=None) -> dict:
        """
        Analyze a *combination* of foods as a meal: total absorbable delivery of
        key minerals accounting for the interaction matrix, plus aggregate
        density. This is where the bioavailability engine pays off — the whole
        is not the sum of the parts.
        """
        from .bioavailability import effective_absorption
        from .reference import percent_of_need, DEFAULT_DEMOGRAPHIC
        demo = demo or DEFAULT_DEMOGRAPHIC

        meal = [self.food_by_id[f] for f in food_ids if f in self.food_by_id]
        if not meal:
            return {"foods": [], "note": "No valid foods."}

        # Focus on absorption-sensitive minerals
        tracked = ["iron", "calcium", "zinc", "magnesium", "vitamin-a"]
        results = {}
        for nutrient in tracked:
            total_raw = 0.0
            total_absorbable = 0.0
            for food in meal:
                amt = food.nutrients.get(nutrient, 0)
                if amt <= 0:
                    continue
                total_raw += amt
                factor = effective_absorption(nutrient, food, meal=meal).factor
                total_absorbable += amt * factor
            if total_raw > 0:
                results[nutrient] = {
                    "raw_amount": round(total_raw, 2),
                    "absorbable_amount": round(total_absorbable, 3),
                    "absorption_pct": round(100 * total_absorbable / total_raw, 1),
                    "percent_of_need_absorbable": percent_of_need(
                        nutrient, total_absorbable, demo),
                }
        return {
            "foods": [f.name for f in meal],
            "minerals": results,
            "total_kcal": sum(f.nutrients.get("energy-kcal", 0) for f in meal),
        }
