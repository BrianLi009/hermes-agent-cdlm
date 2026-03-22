"""
Sudoku-specific helper functions for computing valid candidates.

This module provides domain-specific logic to improve decision quality
by computing which values are actually possible for each empty cell,
based on sudoku constraints (row, column, and 3x3 box).
"""

import re
from typing import Dict, Set, Tuple, Optional, List
from problem_structure import Tree


def extract_grid_from_tree(tree: Tree, grid_size: int = 9) -> Dict[Tuple[int, int], int]:
    """
    Parse the reasoning tree to extract current grid state.
    
    Args:
        tree: The reasoning tree containing deductions
        grid_size: Size of the sudoku grid (default: 9 for 9x9 sudoku)
    
    Returns:
        Dictionary mapping (row, col) tuples to assigned values.
        Only cells with definite assignments are included.
    """
    grid_state = {}
    
    # Pattern to match cell assignments like "Cell (1,2) = 3" or "Cell(1,2) = 3"
    # We look for the most confident assertions
    pattern = r'[Cc]ell\s*\((\d+)\s*,\s*(\d+)\)\s*=\s*(\d+)'
    
    # Iterate through all nodes in the tree
    for node_id, node in tree.nodes.items():
        # Skip conflict nodes
        if hasattr(node, 'is_conflict') and node.is_conflict:
            continue
            
        # Look for cell assignments in the text
        matches = re.findall(pattern, node.text)
        for match in matches:
            row, col, value = int(match[0]), int(match[1]), int(match[2])
            
            # Validate the cell coordinates and value
            if 1 <= row <= grid_size and 1 <= col <= grid_size and 1 <= value <= grid_size:
                # Store the assignment (overwrite if multiple assignments to same cell)
                grid_state[(row, col)] = value
    
    return grid_state


def extract_grid_from_problem(problem_text: str, grid_size: int = 9) -> Dict[Tuple[int, int], int]:
    """
    Parse the initial problem statement to extract given clues.
    
    Args:
        problem_text: The problem statement text
        grid_size: Size of the sudoku grid (default: 9)
    
    Returns:
        Dictionary mapping (row, col) tuples to given values.
    """
    grid_state = {}
    
    # Pattern to match rows like "Row 1:     [9,_,_,5,_,8,_,_,7]"
    row_pattern = r'[Rr]ow\s+(\d+)\s*:\s*\[([^\]]+)\]'
    
    matches = re.findall(row_pattern, problem_text)
    for match in matches:
        row_num = int(match[0])
        values_str = match[1]
        
        # Split by comma and parse values
        values = [v.strip() for v in values_str.split(',')]
        
        for col_num, val_str in enumerate(values, start=1):
            # Check if it's a number (not underscore or empty)
            if val_str.isdigit():
                value = int(val_str)
                if 1 <= value <= grid_size:
                    grid_state[(row_num, col_num)] = value
    
    return grid_state


def get_valid_candidates(
    grid_state: Dict[Tuple[int, int], int],
    row: int,
    col: int,
    grid_size: int = 9,
    box_size: int = 3
) -> Set[int]:
    """
    Compute valid candidate values for a specific cell based on sudoku constraints.
    
    Args:
        grid_state: Current grid state with known cell values
        row: Row number (1-indexed)
        col: Column number (1-indexed)
        grid_size: Size of the sudoku grid (default: 9)
        box_size: Size of each box (default: 3 for 3x3 boxes)
    
    Returns:
        Set of valid candidate values (1 to grid_size) for the cell.
        Returns empty set if cell is already filled.
    """
    # If cell is already filled, no candidates
    if (row, col) in grid_state:
        return set()
    
    # Start with all possible values
    candidates = set(range(1, grid_size + 1))
    
    # Remove values in the same row
    for c in range(1, grid_size + 1):
        if (row, c) in grid_state:
            candidates.discard(grid_state[(row, c)])
    
    # Remove values in the same column
    for r in range(1, grid_size + 1):
        if (r, col) in grid_state:
            candidates.discard(grid_state[(r, col)])
    
    # Remove values in the same 3x3 box
    box_row_start = ((row - 1) // box_size) * box_size + 1
    box_col_start = ((col - 1) // box_size) * box_size + 1
    
    for r in range(box_row_start, box_row_start + box_size):
        for c in range(box_col_start, box_col_start + box_size):
            if (r, c) in grid_state:
                candidates.discard(grid_state[(r, c)])
    
    return candidates


def get_all_candidates(
    grid_state: Dict[Tuple[int, int], int],
    grid_size: int = 9,
    box_size: int = 3
) -> Dict[Tuple[int, int], Set[int]]:
    """
    Compute valid candidates for all empty cells in the grid.
    
    Args:
        grid_state: Current grid state with known cell values
        grid_size: Size of the sudoku grid (default: 9)
        box_size: Size of each box (default: 3)
    
    Returns:
        Dictionary mapping (row, col) to sets of valid candidate values.
        Only includes empty cells.
    """
    all_candidates = {}
    
    for row in range(1, grid_size + 1):
        for col in range(1, grid_size + 1):
            if (row, col) not in grid_state:
                candidates = get_valid_candidates(grid_state, row, col, grid_size, box_size)
                if candidates:  # Only include if there are valid candidates
                    all_candidates[(row, col)] = candidates
    
    return all_candidates


def format_candidates_for_prompt(
    candidates_map: Dict[Tuple[int, int], Set[int]],
    max_cells_to_show: int = 20
) -> str:
    """
    Format candidate information for inclusion in the decision prompt.
    
    Args:
        candidates_map: Dictionary mapping (row, col) to sets of candidates
        max_cells_to_show: Maximum number of cells to include (to avoid overwhelming prompt)
    
    Returns:
        Formatted string describing valid candidates for empty cells.
    """
    if not candidates_map:
        return "All cells are filled or no valid candidates remain."
    
    lines = ["Valid candidates for empty cells (based on current grid state):"]
    lines.append("")
    
    # Sort cells by number of candidates (fewer candidates = more constrained = better to decide)
    sorted_cells = sorted(candidates_map.items(), key=lambda x: (len(x[1]), x[0]))
    
    # Limit the number of cells shown
    cells_to_show = sorted_cells[:max_cells_to_show]
    
    for (row, col), candidates in cells_to_show:
        candidates_str = ", ".join(str(c) for c in sorted(candidates))
        lines.append(f"  Cell ({row},{col}): [{candidates_str}]")
    
    if len(sorted_cells) > max_cells_to_show:
        lines.append(f"  ... and {len(sorted_cells) - max_cells_to_show} more empty cells")
    
    lines.append("")
    lines.append("Note: Cells with fewer candidates are more constrained and often better choices for decisions.")
    
    return "\n".join(lines)


def get_candidates_info_for_decision(
    problem_text: str,
    tree: Tree,
    grid_size: int = 9,
    box_size: int = 3
) -> str:
    """
    High-level function to extract grid state and format candidate information.
    
    This is the main function to call from the solver's decide() method.
    
    Args:
        problem_text: The original problem statement
        tree: The current reasoning tree
        grid_size: Size of the sudoku grid (default: 9)
        box_size: Size of each box (default: 3)
    
    Returns:
        Formatted string with candidate information for the decision prompt.
    """
    # Extract initial clues from problem
    grid_state = extract_grid_from_problem(problem_text, grid_size)
    
    # Update with deductions from the tree
    tree_assignments = extract_grid_from_tree(tree, grid_size)
    grid_state.update(tree_assignments)
    
    # Compute candidates for all empty cells
    candidates_map = get_all_candidates(grid_state, grid_size, box_size)
    
    # Format for prompt
    return format_candidates_for_prompt(candidates_map)

