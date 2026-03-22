"""
Visualization script for CDCL-style implication graphs

Usage:
    python visualize.py

Example:
    python visualize.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from problem_structure import Problem, Tree
from example.example_graphs import create_sudoku_4x4_graph

try:
    import matplotlib.pyplot as plt
    import networkx as nx
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def visualize_tree(problem: Problem, tree: Tree, output_file: str = None):
    """
    Visualize the implication graph using matplotlib and networkx
    Creates a clean, hierarchical DAG visualization with no overlapping edges
    """
    if not HAS_MATPLOTLIB:
        print("Error: matplotlib and networkx are required for visualization")
        print("Install with: pip install matplotlib networkx")
        return
    
    # Create a directed graph
    G = nx.DiGraph()
    
    # Add nodes
    for node_id, node in tree.nodes.items():
        G.add_node(node_id, 
                   text=node.text,
                   level=node.decision_level,
                   is_decision=node.is_decision)
    
    # Add edges (from parents to children) - DIRECTED
    for node_id, node in tree.nodes.items():
        for parent_id in node.parents:
            if parent_id in tree.nodes:
                G.add_edge(parent_id, node_id)
    
    # Create hierarchical layout using Sugiyama algorithm
    # Group nodes by level
    levels_dict = {}
    for node_id, node in tree.nodes.items():
        level = node.decision_level
        if level not in levels_dict:
            levels_dict[level] = []
        levels_dict[level].append(node_id)
    
    # Try different layout methods in order of preference
    pos = None
    
    # Method 1: Try graphviz dot layout (best for DAGs)
    try:
        pos = nx.nx_agraph.graphviz_layout(G, prog='dot')
        # Flip y-axis so root is at top
        pos = {node: (x, -y) for node, (x, y) in pos.items()}
    except:
        pass
    
    # Method 2: Try multipartite layout with manual level assignment
    if pos is None:
        try:
            # Assign subset (level) to each node for multipartite layout
            for node_id, node in tree.nodes.items():
                G.nodes[node_id]['subset'] = node.decision_level
            pos = nx.multipartite_layout(G, subset_key='subset', align='vertical', scale=5)
            # Flip and scale
            pos = {node: (x * 8, -y * 5) for node, (x, y) in pos.items()}
        except:
            pass
    
    # Method 3: Fallback to manual hierarchical layout with better spacing
    if pos is None:
        pos = {}
        max_width = max(len(nodes) for nodes in levels_dict.values()) if levels_dict else 1
        
        for level, node_ids in sorted(levels_dict.items()):
            num_nodes = len(node_ids)
            # Center nodes horizontally with more spacing
            start_x = (max_width - num_nodes) / 2
            for i, node_id in enumerate(sorted(node_ids)):
                x = start_x + i
                y = -level * 4  # Vertical spacing between levels
                pos[node_id] = (x * 6, y)  # Horizontal spacing
    
    # Create figure with light background
    fig, ax = plt.subplots(figsize=(18, 12))
    ax.set_facecolor('#FFF8E7')  # Light beige background like the screenshot
    fig.patch.set_facecolor('#FFF8E7')
    
    # Separate decision and implication nodes
    decision_nodes = [n for n, d in G.nodes(data=True) if d.get('is_decision', False)]
    implication_nodes = [n for n, d in G.nodes(data=True) if not d.get('is_decision', False)]
    
    # Draw nodes with decision level badges
    # Implication nodes (green)
    nx.draw_networkx_nodes(G, pos, 
                          nodelist=implication_nodes,
                          node_color='#90B494',  # Green like in the screenshot
                          node_size=4500,
                          node_shape='s',
                          edgecolors='#4A7C59',
                          linewidths=2.5)
    
    # Decision nodes (orange)
    nx.draw_networkx_nodes(G, pos,
                          nodelist=decision_nodes,
                          node_color='#FF9933',  # Orange like in the screenshot
                          node_size=4500,
                          node_shape='s',
                          edgecolors='#CC6600',
                          linewidths=3)
    
    # Draw directed edges with curved paths to avoid overlap
    # Use different curvature based on edge characteristics
    for edge in G.edges():
        source, target = edge
        # Calculate curvature based on horizontal distance
        x1, y1 = pos[source]
        x2, y2 = pos[target]
        
        # If nodes are at very different horizontal positions, use more curvature
        h_dist = abs(x2 - x1)
        if h_dist > 3:
            rad = 0.3  # More curve for long horizontal edges
        else:
            rad = 0.15  # Less curve for short edges
        
        nx.draw_networkx_edges(G, pos,
                              edgelist=[edge],
                              edge_color='#2E5266',
                              arrows=True,
                              arrowsize=20,
                              arrowstyle='-|>',
                              width=2,
                              node_size=4500,
                              connectionstyle=f'arc3,rad={rad}',
                              min_source_margin=35,
                              min_target_margin=35)
    
    # Draw main node labels (centered)
    labels = {}
    for node_id, node in tree.nodes.items():
        # Truncate long text
        text = node.text if len(node.text) <= 25 else node.text[:22] + "..."
        labels[node_id] = text
    
    nx.draw_networkx_labels(G, pos, labels, 
                           font_size=9, 
                           font_weight='normal',
                           font_family='sans-serif')
    
    # Draw decision level badges (in top-left corner of each node)
    bbox_width = 0.4
    bbox_height = 0.3
    for node_id, node in tree.nodes.items():
        x, y = pos[node_id]
        # Position badge in top-left corner
        badge_x = x - bbox_width
        badge_y = y + bbox_height
        
        # Draw small rectangle badge with rounded corners
        from matplotlib.patches import FancyBboxPatch
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
        
        # Add decision level number
        plt.text(badge_x, badge_y, str(node.decision_level),
                fontsize=9,
                fontweight='bold',
                ha='center',
                va='center',
                zorder=11)
    
    # Add title
    plt.title(f"Implication Graph (DAG)\n{problem.problem_statement}", 
             fontsize=14, fontweight='bold', pad=20)
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#90B494', edgecolor='#4A7C59', label='Implication'),
        Patch(facecolor='#FF9933', edgecolor='#CC6600', label='Decision')
    ]
    plt.legend(handles=legend_elements, loc='upper left', fontsize=10)
    
    plt.axis('off')
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='#FFF8E7')
        print(f"Graph saved to {output_file}")
    else:
        plt.show()


def print_tree_info(problem: Problem, tree: Tree):
    """
    Print textual representation of the tree
    """
    print("=" * 80)
    print("PROBLEM STATEMENT:")
    print(problem.problem_statement)
    print("\nLEMMAS:")
    for i, lemma in enumerate(problem.lemmas):
        print(f"  {i+1}. {lemma}")
    print("\n" + "=" * 80)
    print("IMPLICATION GRAPH:")
    print("=" * 80)
    
    # Group by decision level
    levels = {}
    for node_id, node in tree.nodes.items():
        if node.decision_level not in levels:
            levels[node.decision_level] = []
        levels[node.decision_level].append((node_id, node))
    
    # Print by level
    for level in sorted(levels.keys()):
        print(f"\nDECISION LEVEL {level}:")
        print("-" * 80)
        for node_id, node in sorted(levels[level]):
            node_type = "DECISION" if node.is_decision else "IMPLICATION"
            parent_str = f"parents={node.parents}" if node.parents else "no parents"
            print(f"  [{node_id}] {node_type}: {node.text}")
            print(f"      ({parent_str})")
    
    print("\n" + "=" * 80)
    print(f"STATISTICS:")
    print(f"  Total nodes: {len(tree.nodes)}")
    print(f"  Decision nodes: {sum(1 for n in tree.nodes.values() if n.is_decision)}")
    print(f"  Implication nodes: {sum(1 for n in tree.nodes.values() if not n.is_decision)}")
    print(f"  Max decision level: {max(n.decision_level for n in tree.nodes.values())}")
    print("=" * 80)


def main():
    # Create the sudoku example
    print("Creating 4x4 Sudoku example...")
    problem, tree = create_sudoku_4x4_graph()
    
    # Print textual info
    print_tree_info(problem, tree)
    
    # Visualize
    output_file = "sudoku_4x4_graph.png"
    print(f"\nGenerating visualization...")
    visualize_tree(problem, tree, output_file)


if __name__ == "__main__":
    main()

