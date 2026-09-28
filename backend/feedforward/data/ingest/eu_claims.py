"""
EU Register of nutrition and health claims -> nutrient -> goal edges.

Source: the European Commission's Food and Feed Information Portal, which
publishes the EU Register (Regulation (EC) No 1924/2006) as JSON:

    GET https://ec.europa.eu/food/food-feed-portal/backend/api/policy-items
        ?foodDomain=nut&authorisationType=nut_auth

Commission content may be reused with acknowledgement of the source
(Commission Decision 2011/833/EU). Each claim carries its EFSA opinion.

What becomes an edge
--------------------
* An AUTHORISED claim whose substance resolves to an ontology nutrient and
  whose wording matches a rule in data/eu_claim_rules.json becomes an edge
  with evidence grade A, source "eu_authorised", and the official wording as
  its explanation. That wording is what the app may show consumers.
* A NON-AUTHORISED claim rejected because the effect was not substantiated
  (HC_RR_130 / HC_RR_132) marks the (nutrient, goal) pair "eu_rejected",
  unless an authorised claim covers the same pair. Rejected pairs are not
  routes in the graph; they stay visible with EFSA's reason.
* Everything else is reported: unmapped substances (botanicals, fibres of a
  named cereal, whole foods such as prunes) and claim wordings no rule covers.

Run:
    python -m feedforward.data.ingest.eu_claims --fetch      # download + rebuild
    python -m feedforward.data.ingest.eu_claims --raw FILE   # rebuild from a saved download
"""
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ...ontology.nutrients import resolve

DATA = Path(__file__).resolve().parent.parent
RULES = DATA / "eu_claim_rules.json"
CLAIMS_OUT = DATA / "eu_health_claims.json"
EDGES_OUT = DATA / "goal_edges_eu.json"
REGISTER_URL = ("https://ec.europa.eu/food/food-feed-portal/backend/api/policy-items"
                "?foodDomain=nut&authorisationType=nut_auth")
REGISTER_PAGE = "https://ec.europa.eu/food/food-feed-portal/screen/health-claims/eu-register"

_P = "/policyItemObject/"
_STATUS = {"HCCS_AUTHORISED": "authorised", "HCCS_NON_AUTHORISED": "non_authorised",
           "HCCS_REVOKED": "revoked"}
_TYPE = {"HCLBT_13_1": "art_13_1", "HCLBT_13_5": "art_13_5",
         "HCLBT_14_1_A": "art_14_1_a", "HCLBT_14_1_B": "art_14_1_b"}


@dataclass
class Claim:
    claim_id: str
    substance: str
    status: str                      # authorised | non_authorised | revoked
    claim_type: str
    claim: str                       # the wording (authorised claims: legal text)
    health_relationship: str = ""
    conditions_of_use: str = ""
    restriction: str = ""
    rejection_reason: str = ""
    efsa_opinion: str = ""
    efsa_url: str = ""
    legislation_url: str = ""
    nutrients: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    weight: float = 0.0
    edge_type: str = "positive"
    mapping: str = ""                # mapped | no_goal | unmapped_substance | unmatched_wording


def _clean(text) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _flatten(node, out: dict, path: str = "") -> dict:
    """The register is an entity-attribute-value tree; flatten it to paths."""
    if isinstance(node, dict):
        ident = node.get("valueIdentifier")
        here = f"{path}/{ident}" if ident else path
        if node.get("value") is not None:
            out.setdefault(here, []).append(node["value"])
        for child in node.get("childrenValues") or []:
            _flatten(child, out, here)
    elif isinstance(node, list):
        for child in node:
            _flatten(child, out, path)
    return out


def parse_register(raw: list) -> list[Claim]:
    claims = []
    for item in raw:
        flat = _flatten(item, {})

        def first(key: str) -> str:
            values = flat.get(_P + key)
            return _clean(values[0]) if values else ""

        claims.append(Claim(
            claim_id=first("policyItemCode"),
            substance=first("hcCharacteristicWrapper/hcNutSubFoodCat"),
            status=_STATUS.get(first("hcCharacteristicWrapper/hcClaimStatus"), "unknown"),
            claim_type=_TYPE.get(first("hcCharacteristicWrapper/hcClaimType"), ""),
            claim=first("hcClaimWrapper/hcClaim"),
            health_relationship=first("hcClaimWrapper/hcHealthRelationship"),
            conditions_of_use=first("hcClaimWrapper/hcCondOfUse"),
            restriction=first("hcClaimWrapper/hcRestrictionOfUse"),
            rejection_reason=first("hcClaimWrapper/hcReasonsForNonAuth"),
            efsa_opinion=first("hcEfsaOpinionReferenceWrapper/hcEfsaOpinionReferenceMap/hcEfsaQuestionNbr"),
            efsa_url=first("hcEfsaOpinionReferenceWrapper/hcEfsaOpinionReferenceMap/hcEfsaQuestionUrl"),
            legislation_url=first("hcLegislationsWrapper/hcLegislationsComplex/hcEurLexUrl"),
        ))
    return claims


def load_rules(path: Path = RULES) -> dict:
    rules = json.loads(path.read_text(encoding="utf-8"))
    rules["_compiled"] = [(re.compile(r["pattern"]), r) for r in rules["rules"]]
    return rules


def map_claim(claim: Claim, rules: dict) -> Claim:
    """Resolve the substance and the goal. Mutates and returns ``claim``."""
    override = rules["substances"].get(claim.substance)
    if override is not None:
        claim.nutrients = list(override.get("nutrients", []))
        if override.get("type"):
            claim.edge_type = override["type"]
    else:
        resolved = resolve(claim.substance)
        claim.nutrients = [resolved.nutrient_id] if resolved else []
    if not claim.nutrients:
        claim.mapping = "unmapped_substance"
        return claim
    # Authorised claims are matched on their legal wording; rejected ones on
    # the health relationship EFSA assessed (their "claim" is often empty).
    text = _fold(claim.claim if claim.status == "authorised" else
                 (claim.health_relationship or claim.claim))
    for pattern, rule in rules["_compiled"]:
        if pattern.search(text):
            claim.goals = list(rule["goals"])
            claim.weight = float(rule.get("weight", 0.0))
            if rule.get("type") and claim.edge_type == "positive":
                claim.edge_type = rule["type"]
            claim.mapping = "mapped" if claim.goals else "no_goal"
            return claim
    claim.mapping = "unmatched_wording"
    return claim


def _citation(claim: Claim) -> str:
    return f"EFSA Journal {claim.efsa_opinion}" if claim.efsa_opinion else claim.claim_id


def build_edges(claims: list[Claim], rules: dict) -> dict:
    """
    Authorised edges, rejected pairs, and a report. Pure function of the
    parsed claims and the rules, so it is deterministic and testable offline.
    """
    authorised: dict[tuple[str, str], dict] = {}
    for c in claims:
        if c.status != "authorised" or c.mapping != "mapped":
            continue
        for nutrient in c.nutrients:
            for goal in c.goals:
                edge = authorised.setdefault((nutrient, goal), {
                    "nutrient": nutrient, "goal": goal, "weight": 0.0,
                    "type": c.edge_type, "evidence_grade": "A",
                    "evidence_source": "eu_authorised",
                    "claims": [], "claim_ids": [], "citations": [],
                })
                edge["weight"] = max(edge["weight"], c.weight)
                if c.claim not in edge["claims"]:
                    edge["claims"].append(c.claim)
                edge["claim_ids"].append(c.claim_id)
                cite = _citation(c)
                if cite not in edge["citations"]:
                    edge["citations"].append(cite)
                if c.conditions_of_use and "conditions_of_use" not in edge:
                    edge["conditions_of_use"] = c.conditions_of_use

    demote = {k for k, v in rules["rejection_reasons"].items() if v.get("demote")}
    rejected: dict[tuple[str, str], dict] = {}
    for c in claims:
        if c.status != "non_authorised" or c.mapping != "mapped":
            continue
        if c.rejection_reason not in demote:
            continue
        for nutrient in c.nutrients:
            for goal in c.goals:
                if (nutrient, goal) in authorised:
                    continue
                entry = rejected.setdefault((nutrient, goal), {
                    "nutrient": nutrient, "goal": goal, "relationships": [],
                    "reason": rules["rejection_reasons"][c.rejection_reason]["text"],
                    "reason_code": c.rejection_reason, "citations": [],
                })
                rel = c.health_relationship or c.claim
                if rel and rel not in entry["relationships"]:
                    entry["relationships"].append(rel)
                cite = _citation(c)
                if cite not in entry["citations"]:
                    entry["citations"].append(cite)

    def explanation(edge: dict) -> str:
        return ". ".join(c.rstrip(". ") for c in edge["claims"][:2]) + "."

    edges = []
    for (_n, _g), edge in sorted(authorised.items()):
        edge["explanation"] = explanation(edge)
        edges.append(edge)
    report = {
        "authorised_claims": sum(1 for c in claims if c.status == "authorised"),
        "authorised_mapped": sum(1 for c in claims if c.status == "authorised" and c.mapping == "mapped"),
        "authorised_no_goal": sum(1 for c in claims if c.status == "authorised" and c.mapping == "no_goal"),
        "unmapped_substances": sorted({c.substance for c in claims
                                       if c.status == "authorised" and c.mapping == "unmapped_substance"}),
        "unmatched_wordings": sorted({f"{c.substance}: {c.claim}" for c in claims
                                      if c.mapping == "unmatched_wording" and c.status == "authorised"}),
    }
    return {"goal_edges": edges, "rejected": sorted(rejected.values(),
                                                    key=lambda e: (e["nutrient"], e["goal"])),
            "report": report}


def fetch_register(timeout: int = 300) -> list:  # pragma: no cover - network
    import requests
    response = requests.get(REGISTER_URL, timeout=timeout, headers={
        "Accept": "application/json",
        "User-Agent": "FeedForward/1.0 (nutrition research; EU register import)",
    })
    response.raise_for_status()
    return response.json()


def rebuild(raw: list, *, retrieved_at: str | None = None) -> dict:
    rules = load_rules()
    claims = [map_claim(c, rules) for c in parse_register(raw)]
    result = build_edges(claims, rules)
    retrieved_at = retrieved_at or datetime.now(timezone.utc).date().isoformat()
    provenance = {
        "source": "EU Register of nutrition and health claims (Regulation (EC) No 1924/2006)",
        "url": REGISTER_PAGE, "api": REGISTER_URL, "retrieved_at": retrieved_at,
        "licence": "European Commission content, reuse authorised with acknowledgement "
                   "of the source (Commission Decision 2011/833/EU)",
    }
    # The claims file keeps what the edges were built from: every authorised
    # claim, and every rejected claim about a nutrient we track.
    kept = [asdict(c) for c in claims
            if c.status == "authorised" or (c.nutrients and c.status == "non_authorised")]
    CLAIMS_OUT.write_text(json.dumps({"provenance": provenance, "claims": kept},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    EDGES_OUT.write_text(json.dumps({"provenance": provenance, **result},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def _cli() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Import the EU health claims register.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fetch", action="store_true", help="download the register")
    group.add_argument("--raw", type=Path, help="a saved download (JSON)")
    parser.add_argument("--save-raw", type=Path, help="with --fetch: keep the download")
    args = parser.parse_args()
    if args.fetch:
        raw = fetch_register()
        if args.save_raw:
            args.save_raw.write_text(json.dumps(raw), encoding="utf-8")
    else:
        raw = json.loads(args.raw.read_text(encoding="utf-8"))
    result = rebuild(raw)
    rep = result["report"]
    print(f"{len(result['goal_edges'])} authorised edges, {len(result['rejected'])} rejected pairs; "
          f"{rep['authorised_mapped']}/{rep['authorised_claims']} authorised claims mapped, "
          f"{rep['authorised_no_goal']} with no goal in the taxonomy.")
    for w in rep["unmatched_wordings"]:
        print("  unmatched:", w)


if __name__ == "__main__":
    _cli()
