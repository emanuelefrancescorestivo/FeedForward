"""
plot_metrics.py
---------------
Generates bar charts for the LaTeX report comparing algorithm performances.
"""
import matplotlib.pyplot as plt
import numpy as np

def plot_heuristic_vs_baseline():
    """Average Cost Comparison: Greedy Heuristic vs Random Baseline"""
    labels = ['Random Baseline', 'Greedy Heuristic']
    costs = [18.284, 2.137]  # Your exact final numbers
    
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(labels, costs, color=["#3751FD", "#c3ddf8"], edgecolor='black')
    
    ax.set_ylabel('Average Path Cost (Lower is better)', fontsize=12, fontweight='bold')
    ax.set_title('Algorithm Efficiency: Baseline vs Greedy Heuristic', fontsize=14, fontweight='bold')
    
    # Add numbers on top of bars
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, yval + 0.3, f"{yval:.3f}", 
                ha='center', va='bottom', fontweight='bold', fontsize=12)
        
    plt.savefig('plot_baseline_vs_greedy.png', dpi=300, bbox_inches='tight')
    print("📸 Plot saved: plot_baseline_vs_greedy.png")

def plot_greedy_vs_ilp():
    """Local Minimum Trap: Greedy vs Global Optimal (ILP)"""
    labels = ['Greedy Search', 'Global Optimal (ILP)']
    costs = [9.68, 8.24]
    kcals = [396, 348]
    
    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax1 = plt.subplots(figsize=(8, 6))
    
    # Left Y-Axis: Path Cost
    color = 'tab:blue'
    ax1.set_ylabel('Total Path Cost', color=color, fontsize=12, fontweight='bold')
    bars1 = ax1.bar(x - width/2, costs, width, label='Algorithm Cost', color='#3751FD', edgecolor='black')
    ax1.tick_params(axis='y', labelcolor=color)
    
    # Right Y-Axis: Calories (Constraint)
    ax2 = ax1.twinx()
    color = 'tab:blue'
    ax2.set_ylabel('Total Calories (Limit: 400 kcal)', color=color, fontsize=12, fontweight='bold')
    bars2 = ax2.bar(x + width/2, kcals, width, label='Calories Consumed', color='#c3ddf8', edgecolor='black')
    ax2.tick_params(axis='y', labelcolor=color)
    
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=12, fontweight='bold')
    plt.title('Constrained Optimization: Greedy vs ILP (PuLP)', fontsize=14, fontweight='bold')
    
    # Unified legend
    fig.legend(loc="upper right", bbox_to_anchor=(0.9, 0.9))
    
    fig.tight_layout()
    plt.savefig('plot_greedy_vs_ilp.png', dpi=300, bbox_inches='tight')
    print("📸 Plot saved: plot_greedy_vs_ilp.png")

if __name__ == '__main__':
    print("📊 Generating analytical plots for the report...")
    plot_heuristic_vs_baseline()
    plot_greedy_vs_ilp()
    print("✅ Done!")