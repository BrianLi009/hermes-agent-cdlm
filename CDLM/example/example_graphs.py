from typing import List
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problem_structure import Problem, Deduction, Tree


def create_sudoku_4x4_graph():
    """
    4x4 Sudoku example demonstrating CDCL-style implication graph
    
    Initial state (given clues):
    [1, _, _, 4]
    [_, 3, _, _]
    [_, _, 2, _]
    [4, _, _, 1]
    
    Goal: Fill in the blanks with numbers 1-4
    Rules: Each row, column, and 2x2 box must contain 1,2,3,4 exactly once
    """
    problem = Problem(
        problem_statement="Solve 4x4 Sudoku puzzle",
        lemmas=[
            "Cell(0,0) = 1",  # Row 0, Col 0
            "Cell(0,3) = 4",
            "Cell(1,1) = 3",
            "Cell(2,2) = 2",
            "Cell(3,0) = 4",
            "Cell(3,3) = 1"
        ]
    )
    
    tree = Tree()
    
    # Level 0: Initial clues/constraints (0 decisions made)
    initial_clues = [
        Deduction(reasoning="Given clue", text="Cell(0,0) = 1", parents=[]),
        Deduction(reasoning="Given clue", text="Cell(0,3) = 4", parents=[]),
        Deduction(reasoning="Given clue", text="Cell(1,1) = 3", parents=[]),
        Deduction(reasoning="Given clue", text="Cell(2,2) = 2", parents=[]),
        Deduction(reasoning="Given clue", text="Cell(3,0) = 4", parents=[]),
        Deduction(reasoning="Given clue", text="Cell(3,3) = 1", parents=[])
    ]
    tree.append_deductions(initial_clues, decision_level=0, is_decision=False)
    
    # Level 0: Initial unit propagations from constraints
    initial_implications = [
        Deduction(reasoning="Row 0 needs 2,3. Col 1 has 3. Box constraint", text="Cell(0,1) = 2", parents=[0, 1, 2]),
        Deduction(reasoning="Row 0 needs only 3 now", text="Cell(0,2) = 3", parents=[0, 1, 6]),
    ]
    tree.append_deductions(initial_implications, decision_level=0, is_decision=False)
    
    # Level 1: First decision (1 decision made)
    decision1 = [
        Deduction(reasoning="Decision", text="Cell(1,0) = 2", parents=[0, 4])
    ]
    tree.append_deductions(decision1, decision_level=1, is_decision=True)
    
    # Level 1: Implications from first decision
    implications1 = [
        Deduction(reasoning="Col 0 constraint: has 1,2,4, needs 3", text="Cell(2,0) = 3", parents=[0, 4, 8]),
        Deduction(reasoning="Row 1 has 2,3, needs 1,4. Col 2 has 2,3", text="Cell(1,2) = 4", parents=[2, 7, 8]),
        Deduction(reasoning="Row 1 has 2,3,4, needs 1", text="Cell(1,3) = 1", parents=[1, 2, 8, 10])
    ]
    tree.append_deductions(implications1, decision_level=1, is_decision=False)
    
    # Level 2: Second decision (2 decisions made)
    decision2 = [
        Deduction(reasoning="Decision", text="Cell(2,1) = 4", parents=[6, 9])
    ]
    tree.append_deductions(decision2, decision_level=2, is_decision=True)
    
    # Level 2: Implications from second decision
    implications2 = [
        Deduction(reasoning="Row 2 has 2,3,4, needs 1", text="Cell(2,3) = 1", parents=[3, 9, 12]),
        Deduction(reasoning="Col 1 has 2,3,4, needs 1", text="Cell(3,1) = 1", parents=[6, 2, 12]),
        Deduction(reasoning="Row 3 has 1,4, col 2 has 2,3,4", text="Cell(3,2) = 3", parents=[4, 5, 7, 10, 14]),
        Deduction(reasoning="Row 3 complete, needs 2", text="Cell(3,2) = 2", parents=[4, 5, 14, 15]),
        Deduction(reasoning="Conflict: Cell(3,2) cannot be both 3 and 2", text="CONFLICT!", parents=[15, 16])
    ]
    tree.append_deductions(implications2, decision_level=2, is_decision=False)
    
    return problem, tree


if __name__ == "__main__":
    # This file can be imported by the visualizer
    pass


