# Sudoku-Specific CDLM Implementation

This directory contains domain-specific implementations for solving sudoku puzzles using the CDLM (Conflict-Driven Learning with Models) framework.

## Files

- **`sudoku_helpers.py`**: Core helper functions for sudoku
  - Grid parsing from problem statements and reasoning trees
  - Valid candidate computation based on sudoku constraints
  - Formatting utilities for prompts

- **`sudoku_solver.py`**: Sudoku-specific solver configuration
  - Custom decision prompt function with candidate information
  - Sudoku-specific definitions for deductions and decisions

- **`decision_user_prompt.md`**: Sudoku-specific decision prompt template
  - Includes placeholder for candidate information
  - Guides the model to choose from valid candidates

- **`problem.txt`**: Example 9x9 sudoku puzzle
- **`problem_easy.txt`**: Easier sudoku puzzle for testing

## Key Features

### 1. Candidate Computation
The sudoku solver computes valid candidates for each empty cell based on:
- Row constraints (no duplicate values in row)
- Column constraints (no duplicate values in column)
- Box constraints (no duplicate values in 3x3 box)

This dramatically reduces hallucination and improves decision quality.

### 2. Constrained Branching
Cells are sorted by the number of valid candidates:
- Cells with 1 candidate are essentially solved
- Cells with fewer candidates are prioritized for decisions
- This leads to faster convergence and fewer conflicts

### 3. Modular Design
All sudoku-specific logic is isolated in this directory, keeping the core CDLM framework general-purpose.

## Usage

### Running the Sudoku Solver

```bash
# From the main CDLM directory
python solve.py --problem_file sudoku/problem.txt --problem_type sudoku --verbose
```

### Using Sudoku Helpers in Code

```python
from problem_structure import Problem, Tree
from sudoku.sudoku_solver import create_sudoku_decision_prompt, get_sudoku_definitions

# Get sudoku-specific definitions
deduction_def, decision_def = get_sudoku_definitions()

# Create decision prompt with candidate information
problem = Problem(problem_text)
tree = Tree()
prompt, candidates_info = create_sudoku_decision_prompt(problem, tree)
```

### Example Output (with --verbose)

```
[DECIDE] Sending prompt to decision_agent...
[DECIDE] Domain-specific info:
  Valid candidates for empty cells (based on current grid state):
  
  Cell (1,5): [4]        ← Single candidate
  Cell (2,3): [7]        ← Single candidate
  Cell (1,8): [1, 2]     ← Two candidates
  Cell (2,5): [4, 6]     ← Two candidates
  ...
  
  Note: Cells with fewer candidates are more constrained and often better choices for decisions.
[DECIDE] Result:
  text: "Assign Cell (1,5) = 4"
```

## Implementation Details

### Grid State Extraction
The solver extracts the current grid state from two sources:
1. **Initial clues**: Parsed from the problem statement using regex
2. **Deductions**: Extracted from the reasoning tree

### Candidate Computation Algorithm
For each empty cell (r, c):
1. Start with candidates = {1, 2, 3, 4, 5, 6, 7, 8, 9}
2. Remove values present in row r
3. Remove values present in column c
4. Remove values present in the 3x3 box containing (r, c)
5. Return remaining candidates

### Integration with CDLM
The sudoku solver integrates with CDLM through:
- **Custom decision prompt function**: `create_sudoku_decision_prompt()`
- **Domain-specific definitions**: Passed to the Solver constructor
- **Modular design**: Core CDLM framework remains unchanged

## Benefits Over General Solver

1. **Reduces hallucination**: Model can only choose valid values
2. **Improves decision quality**: Focuses on constrained cells first
3. **Faster convergence**: Fewer conflicts and backtracking steps
4. **Better branching**: Informed decisions based on actual constraints

## Trade-offs

- **Generalization**: Adds domain-specific logic not applicable to all problems
- **Justification**: This is analogous to unit propagation in SAT solvers - a symbolic preprocessing step that makes search tractable
- **Modularity**: All domain-specific code is isolated, so it doesn't affect the general framework

