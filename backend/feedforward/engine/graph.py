"""
engine/graph.py
===============
The weighted tripartite graph (Food -> Nutrient -> Goal).

This preserves the university project's hand-written adjacency-list design
(no NetworkX as the backing store), and adds two things a product needs:

  * a REVERSE adjacency index, so we can traverse Goal -> Nutrient -> Food
    efficiently. This is the fix for the 587 ms recommendation latency: instead
    of running Dijkstra from every one of ~1,800 food nodes, we run it once
    from each goal on the reversed graph and cache the result.
  * node typing and id<->name maps, so results are human-readable (the old
    ``foods_for_goal`` returned raw product IDs).
"""
from __future__ import annotations

from collections import defaultdict


class FeedForwardGraph:
    def __init__(self) -> None:
        # forward: source -> [(dest, weight), ...]
        self.adj: dict[str, list[tuple[str, float]]] = {}
        # reverse: dest -> [(source, weight), ...]
        self.radj: dict[str, list[tuple[str, float]]] = defaultdict(list)
        # node metadata
        self.node_type: dict[str, str] = {}      # id -> "food" | "nutrient" | "goal"
        self.name_of: dict[str, str] = {}        # id -> display name

    # -- construction ------------------------------------------------------
    def add_node(self, node_id: str, node_type: str | None = None,
                 name: str | None = None) -> None:
        if node_id not in self.adj:
            self.adj[node_id] = []
        if node_type:
            self.node_type[node_id] = node_type
        if name:
            self.name_of[node_id] = name

    def add_edge(self, source: str, destination: str, weight: float) -> None:
        if source not in self.adj:
            self.add_node(source)
        if destination not in self.adj:
            self.add_node(destination)
        self.adj[source].append((destination, weight))
        self.radj[destination].append((source, weight))

    # -- access ------------------------------------------------------------
    def neighbours(self, node_id: str) -> list[tuple[str, float]]:
        return self.adj.get(node_id, [])

    def reverse_neighbours(self, node_id: str) -> list[tuple[str, float]]:
        return self.radj.get(node_id, [])

    def display_name(self, node_id: str) -> str:
        return self.name_of.get(node_id, node_id)

    def nodes_of_type(self, node_type: str) -> list[str]:
        return [n for n, t in self.node_type.items() if t == node_type]

    # -- stats -------------------------------------------------------------
    @property
    def num_nodes(self) -> int:
        return len(self.adj)

    @property
    def num_edges(self) -> int:
        return sum(len(v) for v in self.adj.values())

    def summary(self) -> dict[str, int]:
        types = defaultdict(int)
        for t in self.node_type.values():
            types[t] += 1
        return {
            "nodes": self.num_nodes,
            "edges": self.num_edges,
            "food": types["food"],
            "nutrient": types["nutrient"],
            "goal": types["goal"],
        }
