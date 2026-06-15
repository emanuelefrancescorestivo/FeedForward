from graph.feedforward import FeedForwardGraph
from graph.algorithms import dijkstra, reconstruct_path

def test_dijkstra_toy():
    g = FeedForwardGraph()
    g.add_edge("A", "B", 1)
    g.add_edge("A", "C", 3)
    g.add_edge("B", "D", 2)
    g.add_edge("C", "D", 4)

    dist, pred = dijkstra(g, "A")

    assert dist["A"] == 0
    assert dist["B"] == 1
    assert dist["C"] == 3
    assert dist["D"] == 3

def test_reconstruct_path():
    g = FeedForwardGraph()
    g.add_edge("A", "B", 1)
    g.add_edge("A", "C", 3)
    g.add_edge("B", "D", 2)
    g.add_edge("C", "D", 4)

    dist, pred = dijkstra(g, "A")
    path = reconstruct_path(pred, "A", "D")

    assert path == ["A", "B", "D"]