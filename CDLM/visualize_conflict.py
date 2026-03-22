"""
Visualize conflict analysis with 1-UIP cut highlighted

This script extends the basic visualization to show:
1. The implication graph with the conflict
2. The 1-UIP node highlighted
3. The learned clause nodes highlighted
4. Visual indication of the cut separating reason side from conflict side
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from problem_structure import Problem, Tree
from example.example_graphs import create_sudoku_4x4_graph
from conflict_analysis import ConflictAnalyzer

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch
    import networkx as nx
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def visualize_conflict_analysis(tree: Tree, conflict_node_id: int, output_file: str = None):
    """
    Visualize the implication graph with conflict analysis highlighted.
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib and networkx are required for visualization")
        return
    
    # Perform conflict analysis
    analyzer = ConflictAnalyzer(tree)
    learned_clause, uip_node_id, backjump_level = analyzer.analyze_conflict(conflict_node_id)
    
    # Create directed graph
    G = nx.DiGraph()
    
    for node_id, node in tree.nodes.items():
        G.add_node(node_id, 
                   text=node.text,
                   level=node.decision_level,
                   is_decision=node.is_decision)
    
    for node_id, node in tree.nodes.items():
        for parent_id in node.parents:
            if parent_id in tree.nodes:
                G.add_edge(parent_id, node_id)
    
    # Create layout
    levels_dict = {}
    for node_id, node in tree.nodes.items():
        level = node.decision_level
        if level not in levels_dict:
            levels_dict[level] = []
        levels_dict[level].append(node_id)
    
    # Try graphviz layout
    pos = None
    try:
        pos = nx.nx_agraph.graphviz_layout(G, prog='dot')
        pos = {node: (x, -y) for node, (x, y) in pos.items()}
    except:
        pass
    
    if pos is None:
        try:
            for node_id, node in tree.nodes.items():
                G.nodes[node_id]['subset'] = node.decision_level
            pos = nx.multipartite_layout(G, subset_key='subset', align='vertical', scale=5)
            pos = {node: (x * 8, -y * 5) for node, (x, y) in pos.items()}
        except:
            pass
    
    if pos is None:
        pos = {}
        max_width = max(len(nodes) for nodes in levels_dict.values()) if levels_dict else 1
        for level, node_ids in sorted(levels_dict.items()):
            num_nodes = len(node_ids)
            start_x = (max_width - num_nodes) / 2
            for i, node_id in enumerate(sorted(node_ids)):
                x = start_x + i
                y = -level * 4
                pos[node_id] = (x * 6, y)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(18, 12))
    ax.set_facecolor('#FFF8E7')
    fig.patch.set_facecolor('#FFF8E7')
    
    # Categorize nodes
    conflict_level = tree.nodes[conflict_node_id].decision_level
    
    # Color nodes based on their role
    normal_implications = []
    normal_decisions = []
    learned_clause_nodes = list(learned_clause)
    uip_nodes = [uip_node_id]
    conflict_nodes = [conflict_node_id]
    
    for node_id in tree.nodes:
        if node_id == conflict_node_id:
            continue
        elif node_id == uip_node_id:
            continue
        elif node_id in learned_clause:
            continue
        elif tree.nodes[node_id].is_decision:
            normal_decisions.append(node_id)
        else:
            normal_implications.append(node_id)
    
    # Draw normal implication nodes (green)
    if normal_implications:
        nx.draw_networkx_nodes(G, pos, 
                              nodelist=normal_implications,
                              node_color='#90B494',
                              node_size=4500,
                              node_shape='s',
                              edgecolors='#4A7C59',
                              linewidths=2.5)
    
    # Draw normal decision nodes (orange)
    if normal_decisions:
        nx.draw_networkx_nodes(G, pos,
                              nodelist=normal_decisions,
                              node_color='#FF9933',
                              node_size=4500,
                              node_shape='s',
                              edgecolors='#CC6600',
                              linewidths=3)
    
    # Draw learned clause nodes (yellow)
    if learned_clause_nodes:
        nx.draw_networkx_nodes(G, pos,
                              nodelist=learned_clause_nodes,
                              node_color='#FFE66D',
                              node_size=4500,
                              node_shape='s',
                              edgecolors='#DAA520',
                              linewidths=4)
    
    # Draw 1-UIP node (bright blue)
    if uip_nodes:
        nx.draw_networkx_nodes(G, pos,
                              nodelist=uip_nodes,
                              node_color='#4ECDC4',
                              node_size=4500,
                              node_shape='s',
                              edgecolors='#00796B',
                              linewidths=5)
    
    # Draw conflict node (red)
    if conflict_nodes:
        nx.draw_networkx_nodes(G, pos,
                              nodelist=conflict_nodes,
                              node_color='#FF6B6B',
                              node_size=4500,
                              node_shape='s',
                              edgecolors='#C92A2A',
                              linewidths=5)
    
    # Draw edges
    for edge in G.edges():
        source, target = edge
        x1, y1 = pos[source]
        x2, y2 = pos[target]
        
        h_dist = abs(x2 - x1)
        rad = 0.3 if h_dist > 3 else 0.15
        
        # Highlight edges involved in conflict
        if target == conflict_node_id or target == uip_node_id or target in learned_clause:
            edge_color = '#C92A2A'
            width = 3
        else:
            edge_color = '#2E5266'
            width = 2
        
        nx.draw_networkx_edges(G, pos,
                              edgelist=[edge],
                              edge_color=edge_color,
                              arrows=True,
                              arrowsize=20,
                              arrowstyle='-|>',
                              width=width,
                              node_size=4500,
                              connectionstyle=f'arc3,rad={rad}',
                              min_source_margin=35,
                              min_target_margin=35)
    
    # Draw labels
    labels = {}
    for node_id, node in tree.nodes.items():
        text = node.text if len(node.text) <= 25 else node.text[:22] + "..."
        labels[node_id] = text
    
    nx.draw_networkx_labels(G, pos, labels, 
                           font_size=9, 
                           font_weight='normal',
                           font_family='sans-serif')
    
    # Draw decision level badges
    bbox_width = 0.4
    bbox_height = 0.3
    for node_id, node in tree.nodes.items():
        x, y = pos[node_id]
        badge_x = x - bbox_width
        badge_y = y + bbox_height
        
        badge = FancyBboxPatch(
            (badge_x - 0.15, badge_y - 0.12),
            0.3, 0.24,
            boxstyle="round,pad=0.05",
            facecolor='#FFD700',
            edgecolor='#CC9900',
            linewidth=1.5,
            zorder=10
        )
        ax.add_patch(badge)
        
        plt.text(badge_x, badge_y, str(node.decision_level),
                fontsize=9,
                fontweight='bold',
                ha='center',
                va='center',
                zorder=11)
    
    # Add title with conflict analysis info
    title = f"Conflict Analysis - 1-UIP Cut\n"
    title += f"Conflict at node {conflict_node_id}, 1-UIP: node {uip_node_id}, Backjump to level {backjump_level}"
    plt.title(title, fontsize=14, fontweight='bold', pad=20)
    
    # Add legend
    legend_elements = [
        mpatches.Patch(facecolor='#90B494', edgecolor='#4A7C59', label='Implication'),
        mpatches.Patch(facecolor='#FF9933', edgecolor='#CC6600', label='Decision'),
        mpatches.Patch(facecolor='#FFE66D', edgecolor='#DAA520', label='Learned Clause'),
        mpatches.Patch(facecolor='#4ECDC4', edgecolor='#00796B', label='1-UIP'),
        mpatches.Patch(facecolor='#FF6B6B', edgecolor='#C92A2A', label='Conflict')
    ]
    plt.legend(handles=legend_elements, loc='upper left', fontsize=10)
    
    # Add learned clause info box
    info_text = f"Learned Clause: {{{', '.join(map(str, sorted(learned_clause)))}}}\n"
    info_text += f"Backjump Level: {backjump_level}"
    plt.text(0.02, 0.02, info_text,
            transform=fig.transFigure,
            fontsize=10,
            verticalalignment='bottom',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.axis('off')
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='#FFF8E7')
        print(f"Conflict analysis visualization saved to {output_file}")
    else:
        plt.show()


if __name__ == "__main__":
    print("Creating Sudoku 4x4 example with conflict...")
    problem, tree = create_sudoku_4x4_graph()
    
    # Find the conflict node
    conflict_node_id = max(tree.nodes.keys())
    
    print(f"Analyzing conflict at node {conflict_node_id}...\n")
    
    # Print analysis
    from conflict_analysis import analyze_and_print
    analyze_and_print(tree, conflict_node_id)
    
    # Visualize
    print("\nGenerating visualization with 1-UIP cut highlighted...")
    visualize_conflict_analysis(tree, conflict_node_id, "sudoku_conflict_analysis.png")

