"""
Graph-level gap report.

NetworkX is not the recommendation store — Dijkstra stays on the hand-written
adjacency list. This module builds a small nutrient→goal digraph from the
edges the engine already graded and asks two research questions:

  * which nutrients are hubs (high degree across goals)
  * which taxonomy goals have thin positive coverage

It is computed once, on a graph of tens of edges, and cached by the caller.
It is not on the recommendation path, so growing the food corpus does not
make a query slower.
"""
from __future__ import annotations

from . import taxonomy


def coverage_report(goal_edges: list[dict], *, thin_below: int = 2) -> dict:
    import networkx as nx

    g = nx.DiGraph()
    positive = [e for e in goal_edges if e.get("type", "positive") == "positive"]
    for edge in positive:
        g.add_edge(edge["nutrient"], edge["goal"], weight=float(edge.get("weight", 0)))

    degree = nx.degree_centrality(g) if g.number_of_nodes() else {}
    # Betweenness on a graph this small is cheap and highlights nutrients that
    # sit on paths between other nutrients and goals. Isolated goal nodes
    # (negative-only) are added below so thin goals are visible.
    between = nx.betweenness_centrality(g) if g.number_of_nodes() else {}

    by_goal: dict[str, list[str]] = {}
    for edge in positive:
        by_goal.setdefault(edge["goal"], []).append(edge["nutrient"])

    taxonomy_ids = [goal.id for goal in taxonomy.all_goals()]
    thin = []
    for goal_id in taxonomy_ids:
        nutrients = by_goal.get(goal_id, [])
        if len(nutrients) < thin_below:
            thin.append({
                "goal": goal_id,
                "positive_edges": len(nutrients),
                "nutrients": nutrients,
            })

    orphan_goals = sorted(set(by_goal) - set(taxonomy_ids))
    hubs = sorted(
        ((n, degree.get(n, 0.0)) for n in g.nodes if n not in taxonomy_ids and n in degree),
        key=lambda item: item[1],
        reverse=True,
    )
    eu_goals = {e["goal"] for e in positive if e.get("evidence_source") == "eu_authorised"}
    return {
        "positive_edges": len(positive),
        # Taxonomy goals with no positive route at all: the app must say that
        # no nutrient has established evidence for them, not invent one.
        "evidence_gaps": [g for g in taxonomy_ids if g not in by_goal],
        # Goals whose routes rest only on curated literature, with no
        # authorised EU health claim behind any of them.
        "goals_without_eu_claim": [g for g in taxonomy_ids if g in by_goal and g not in eu_goals],
        "nutrient_hubs": [
            {"nutrient": n, "degree_centrality": round(c, 4),
             "betweenness": round(between.get(n, 0.0), 4)}
            for n, c in hubs[:8]
        ],
        "thin_goals": thin,
        "orphan_goals": orphan_goals,
        "goals_with_positive_edges": len(set(taxonomy_ids) & set(by_goal)),
        "taxonomy_goals": len(taxonomy_ids),
    }
