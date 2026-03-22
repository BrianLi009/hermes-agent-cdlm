"""
Sudoku-specific solver that extends the general CDLM Solver.

This module provides a SudokuSolver class that adds domain-specific
enhancements (like candidate computation) to the general solver.
"""

from string import Template
from typing import Optional
import os

from problem_structure import Problem, Tree
from sudoku.sudoku_helpers import get_candidates_info_for_decision


# Load sudoku-specific prompts
_current_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_current_dir, 'decision_user_prompt.md'), 'r') as f:
    SUDOKU_DECISION_USER_PROMPT = f.read()

# Sudoku-specific definitions
SUDOKU_DEDUCTION = "An implication regarding the solution of the sudoku puzzle. This can be the exact value of a cell or a relationship between values of cells. This must be implied from existing knowledge (parents)."
SUDOKU_DECISION = "An assumption regarding the solution of the sudoku puzzle. This can be the exact value of a cell or a relationship between values of cells. This need not be implied but is assumed."


def create_sudoku_decision_prompt(problem: Problem, tree: Tree) -> str:
    """
    Create a decision prompt with sudoku-specific candidate information.
    
    Args:
        problem: The sudoku problem
        tree: The current reasoning tree
    
    Returns:
        Formatted decision prompt with candidate information
    """
    # Compute valid candidates for sudoku cells to guide decision-making
    candidates_info = get_candidates_info_for_decision(
        str(problem),
        tree
    )
    
    user_prompt = Template(SUDOKU_DECISION_USER_PROMPT).substitute({
        "PROBLEM": str(problem),
        "REASONING_TREE": str(tree),
        "DEFINITION": SUDOKU_DECISION,
        "CANDIDATES": candidates_info
    })
    
    return user_prompt, candidates_info


def get_sudoku_definitions():
    """
    Get sudoku-specific definitions for deductions and decisions.
    
    Returns:
        Tuple of (DEDUCTION_DEFINITION, DECISION_DEFINITION)
    """
    return SUDOKU_DEDUCTION, SUDOKU_DECISION

