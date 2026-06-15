"""
app/analytics.py
----------------
Advanced graph analytics using NetworkX for reporting and visualization.
"""
import networkx as nx
import matplotlib.pyplot as plt
from networkx.algorithms import community

def build_nx_graph(custom_graph):
    """Converts our hand-written graph to NetworkX for offline analysis."""
    G = nx.Graph()
    for node, edges in custom_graph.adj.items():
        for neighbor, weight in edges:
            G.add_edge(node, neighbor, weight=weight)
    return G

def run_centrality_analysis(nx_graph):
    print("\n--- 🌐 GRAPH CENTRALITY ANALYSIS ---")
    # Betweenness Centrality: Identifies the biggest "bridges" in the graph
    betweenness = nx.betweenness_centrality(nx_graph, weight='weight')
    
    # Sort and filter to show only Nutrients (assuming goals have '_' and foods are long IDs)
    nutrients = {k: v for k, v in betweenness.items() if not k.isdigit() and '_' not in k}
    top_nutrients = sorted(nutrients.items(), key=lambda x: x[1], reverse=True)
    
    print("Most Central Nutrients (Broadest Health Impact):")
    for nutrient, score in top_nutrients[:5]:
        print(f"  ⭐ {nutrient.title()}: {score:.4f}")
    return top_nutrients

def run_community_detection(nx_graph):
    print("\n--- 🏘️ LOUVAIN COMMUNITY DETECTION ---")
    # Louvain finds natural clusters based on edge density
    communities = community.louvain_communities(nx_graph, weight='weight')
    
    print(f"Detected {len(communities)} distinct nutritional communities.")
    
    # Let's peek at what's inside the first 3 communities
    for i, c in enumerate(communities[:3], 1):
        # Sample a few recognizable names from each community
        sample = [node for node in c if not node.isdigit()][:5] 
        print(f"  Community {i} Sample: {', '.join(sample)}")

def plot_graph(nx_graph):
    """Generates a professional bipartite visual plot for the final report."""
    plt.figure(figsize=(14, 10))
    
    # 1. Filter out Foods (keep only Nutrients and Goals)
    subset = [n for n in nx_graph.nodes if not n.isdigit()]
    subgraph = nx_graph.subgraph(subset).copy()
    
    # 2. Remove isolated nodes (the ones floating away with 0 connections)
    subgraph.remove_nodes_from(list(nx.isolates(subgraph)))
    
    # 3. Separate into two columns for a clean Bipartite layout
    goals = [n for n in subgraph.nodes if '_' in n or n == 'energy']
    nutrients = [n for n in subgraph.nodes if n not in goals]
    
    # 4. Generate the layout
    pos = nx.bipartite_layout(subgraph, nutrients)
    
    # 5. Draw Nutrients (Green Circles)
    nx.draw_networkx_nodes(subgraph, pos, nodelist=nutrients, 
                           node_color='#a8e6cf', node_size=1800, edgecolors='gray')
    
    # 6. Draw Goals (Blue Squares)
    nx.draw_networkx_nodes(subgraph, pos, nodelist=goals, 
                           node_color='#ffaebc', node_size=2500, node_shape='s', edgecolors='gray')
    
    # 7. Draw Edges and Labels
    nx.draw_networkx_edges(subgraph, pos, alpha=0.4, edge_color='gray', width=1.5)
    nx.draw_networkx_labels(subgraph, pos, font_size=10, font_weight='bold')
    
    plt.title("Bipartite Topology: Nutrients to Physiological Goals", fontsize=16, fontweight='bold')
    plt.axis("off")
    plt.tight_layout()
    plt.savefig("graph_topology_fixed.png", dpi=300, bbox_inches='tight') # High resolution
    print("\n📸 Professional Bipartite visualization saved to 'graph_topology_fixed.png'!")