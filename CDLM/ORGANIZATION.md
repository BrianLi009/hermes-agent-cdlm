# CDLM Codebase Organization

This document explains how the codebase is organized to separate general CDLM framework code from domain-specific implementations.

## Design Principles

1. **General Framework**: Core CDLM logic remains in the root directory and is problem-agnostic
2. **Domain-Specific**: Problem-specific implementations are in subdirectories (e.g., `sudoku/`)
3. **Modularity**: Domain-specific code can be easily added or removed without affecting the core framework
4. **Extensibility**: New problem types can be added by creating new subdirectories with similar structure

## Directory Structure

```
CDLM/
├── Core Framework (General)
│   ├── solve.py                    # Main solver with pluggable components
│   ├── problem_structure.py        # Core data structures
│   ├── agents.py                   # LLM agents
│   ├── conflict_analysis.py        # Conflict analysis (CDCL)
│   ├── visualize.py                # Graph visualization
│   ├── *_user_prompt.md           # General prompt templates
│   └── example/                    # Example graphs
│
└── Domain-Specific (Sudoku)
    └── sudoku/
        ├── sudoku_helpers.py       # Grid parsing, candidate computation
        ├── sudoku_solver.py        # Sudoku-specific solver config
        ├── decision_user_prompt.md # Sudoku decision prompt
        ├── problem*.txt            # Example problems
        └── README.md               # Sudoku-specific docs
```

## How It Works

### General Framework (Root Directory)

The core `Solver` class in `solve.py` accepts optional parameters for customization:

```python
class Solver:
    def __init__(
        self,
        problem: Problem,
        tree: Tree = None,
        deduction_effort: int = 1,
        verbose: bool = False,
        deduction_definition: str = None,      # Custom deduction definition
        decision_definition: str = None,        # Custom decision definition
        decision_prompt_fn: callable = None     # Custom decision prompt function
    ):
```

**Key Features:**
- Uses default definitions if none provided
- Uses default decision prompt if no custom function provided
- Completely problem-agnostic

### Domain-Specific Implementation (sudoku/)

Each domain-specific directory should provide:

1. **Helper Functions**: Domain logic (e.g., `sudoku_helpers.py`)
2. **Solver Configuration**: Custom definitions and prompt functions (e.g., `sudoku_solver.py`)
3. **Prompts**: Domain-specific prompt templates (e.g., `decision_user_prompt.md`)
4. **Examples**: Sample problems (e.g., `problem.txt`)
5. **Documentation**: Domain-specific README

**Example: Sudoku**

```python
# sudoku/sudoku_solver.py
def create_sudoku_decision_prompt(problem: Problem, tree: Tree) -> tuple:
    """
    Custom decision prompt function for sudoku.
    Returns: (prompt_string, debug_info_string)
    """
    candidates_info = get_candidates_info_for_decision(str(problem), tree)
    prompt = Template(SUDOKU_DECISION_USER_PROMPT).substitute({
        "PROBLEM": str(problem),
        "REASONING_TREE": str(tree),
        "DEFINITION": SUDOKU_DECISION,
        "CANDIDATES": candidates_info
    })
    return prompt, candidates_info
```

### Integration in solve.py

The main script detects problem type and loads appropriate configuration:

```python
if args.problem_type == "sudoku":
    from sudoku.sudoku_solver import create_sudoku_decision_prompt, get_sudoku_definitions
    deduction_def, decision_def = get_sudoku_definitions()
    
    solution = run_solver(
        problem, tree=tree,
        deduction_definition=deduction_def,
        decision_definition=decision_def,
        decision_prompt_fn=create_sudoku_decision_prompt,
        ...
    )
else:
    # Use general solver with defaults
    solution = run_solver(problem, tree=tree, ...)
```

## Adding New Problem Types

To add a new problem type (e.g., SAT, Graph Coloring, etc.):

1. **Create directory**: `mkdir problem_type/`

2. **Create helper module**: `problem_type/helpers.py`
   - Implement domain-specific logic
   - Parse problem statements
   - Compute domain-specific information

3. **Create solver config**: `problem_type/solver.py`
   - Define `DEDUCTION_DEFINITION` and `DECISION_DEFINITION`
   - Implement `create_decision_prompt(problem, tree) -> (prompt, debug_info)`
   - Implement `get_definitions() -> (deduction_def, decision_def)`

4. **Create prompts**: `problem_type/decision_user_prompt.md`
   - Domain-specific prompt template
   - Include placeholders: `$PROBLEM`, `$REASONING_TREE`, `$DEFINITION`
   - Add domain-specific placeholders as needed

5. **Add to solve.py**: Update the main script
   ```python
   parser.add_argument(
       "--problem_type",
       choices=["sudoku", "general", "your_new_type"],
       ...
   )
   
   if args.problem_type == "your_new_type":
       from your_new_type.solver import create_decision_prompt, get_definitions
       ...
   ```

6. **Document**: Create `problem_type/README.md`

## Benefits of This Organization

1. **Separation of Concerns**: General framework vs domain-specific logic
2. **Maintainability**: Easy to update core framework without affecting domains
3. **Extensibility**: Simple to add new problem types
4. **Clarity**: Clear where to find code for specific problems
5. **Reusability**: Core framework can be used for any problem type
6. **Testing**: Can test general and domain-specific code independently

## Example Usage

```bash
# Sudoku with domain-specific helpers
python3 solve.py --problem_file sudoku/problem.txt --problem_type sudoku

# General solver (no domain-specific helpers)
python3 solve.py --problem_file sudoku/problem.txt --problem_type general

# Future: SAT solver
python3 solve.py --problem_file sat/problem.cnf --problem_type sat
```

## Migration Notes

**Before reorganization:**
- All code in root directory
- Sudoku-specific logic mixed with general code
- Hard to distinguish framework from domain logic

**After reorganization:**
- Clear separation between framework and domains
- Sudoku code isolated in `sudoku/` directory
- Easy to add new problem types
- Core framework remains clean and general

