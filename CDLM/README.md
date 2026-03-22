# CDLM - Conflict-Driven Learning for Mathematical Reasoning

A framework for representing and visualizing CDCL-style implication graphs for constraint satisfaction problems, inspired by SAT solver techniques.

## Overview

This project defines a data structure for building Directed Acyclic Graphs (DAGs) that represent the implication relationships in a CDCL (Conflict-Driven Clause Learning) solver. The structure tracks:

- **Nodes**: Represent literals/deductions with unique IDs
- **Decision Levels**: The number of decisions made up to that point in the trail
- **Parent Relationships**: Which nodes led to the current deduction
- **Decision vs Implication**: Whether a node is a choice (decision) or a forced consequence (implication)

## Structure

### Core Classes (`problem_structure.py`)

- **Problem**: Defines the problem statement and initial lemmas/constraints
- **Deduction**: Represents a single logical deduction with reasoning, text, and parent dependencies
- **Node**: A node in the implication graph with ID, text, parents, decision level, and decision flag
- **Tree**: The implication graph itself, maintaining nodes and their relationships

### Visualization (`visualize.py`)

Creates clean, hierarchical DAG visualizations with:
- Green nodes for implications
- Orange nodes for decisions
- Yellow badges showing decision levels
- Directed edges showing parent-child relationships
- No overlapping nodes or edges

## Example: 4x4 Sudoku

The included example demonstrates CDCL-style reasoning on a 4x4 Sudoku puzzle.

### Initial Puzzle State

```
[1, _, _, 4]
[_, 3, _, _]
[_, _, 2, _]
[4, _, _, 1]
```

**Rules**: Each row, column, and 2×2 box must contain the numbers 1-4 exactly once.

### Implication Graph Structure

**Decision Level 0 (0 decisions made)**
- 6 given clues: Cell(0,0)=1, Cell(0,3)=4, Cell(1,1)=3, Cell(2,2)=2, Cell(3,0)=4, Cell(3,3)=1
- Unit propagations:
  - Cell(0,1) = 2 (Row 0 needs 2,3; Col 1 has 3; box constraint)
  - Cell(0,2) = 3 (Row 0 only needs 3 now)

**Decision Level 1 (1 decision made)**
- **Decision**: Cell(1,0) = 2
- Unit propagations:
  - Cell(2,0) = 3 (Col 0 has 1,2,4; needs 3)
  - Cell(1,2) = 4 (Row 1 has 2,3; Col 2 has 2,3)
  - Cell(1,3) = 1 (Row 1 complete)

**Decision Level 2 (2 decisions made)**
- **Decision**: Cell(2,1) = 4
- Unit propagations:
  - Cell(2,3) = 1 (Row 2 needs 1)
  - Cell(3,1) = 1 (Col 1 needs 1)
  - Cell(3,2) = 3 (Row 3 reasoning)
  - Cell(3,2) = 2 (Alternative reasoning)
  - **CONFLICT**: Cell(3,2) cannot be both 3 and 2!

### What This Demonstrates

This example shows the core CDCL mechanism:

1. **Initial constraints** (Level 0) are the given clues
2. **Unit propagation** derives immediate consequences from constraints
3. **Decisions** are made when no more unit propagations are possible
4. **More propagations** follow each decision
5. **Conflicts** are detected when contradictory deductions occur
6. The implication graph can then be analyzed (in backtracking) to learn which decisions led to the conflict

In a real CDCL solver, after detecting this conflict at Level 2, the solver would:
- Analyze the conflict to find a learned clause
- Backtrack to an earlier decision level
- Add the learned clause to avoid this conflict in the future
- Try a different decision

## Usage

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Generate Basic Visualization

```bash
python3 visualize.py
```

This will:
1. Print a detailed textual representation of the implication graph
2. Generate `sudoku_4x4_graph.png` showing the visual DAG

### Perform Conflict Analysis

Analyze conflicts in the implication graph to find the learned clause and backjump level:

```bash
# Analyze the Sudoku example (automatically finds the conflict node)
python3 conflict_analysis.py sudoku

# Analyze with a specific conflict node ID
python3 conflict_analysis.py sudoku --conflict-id 17

# Analyze and generate visualization
python3 conflict_analysis.py sudoku --visualize
```

**Parameters:**
- `graph`: The example graph to analyze (currently: `sudoku`)
- `--conflict-id`: Optional. The node ID of the conflict. If not specified, uses the last node in the graph.
- `--visualize`: Optional. Generate a visualization PNG file with the conflict analysis highlighted.

This demonstrates CDCL conflict analysis, showing:
- The conflict node
- The First Unique Implication Point (1-UIP)
- The learned clause
- The decision level to backjump to

### Visualize Conflict Analysis

```bash
python3 visualize_conflict.py
```

This generates an enhanced visualization (`sudoku_conflict_analysis.png`) that highlights:
- **Red node**: The conflict
- **Cyan node**: The 1-UIP (First Unique Implication Point)
- **Yellow nodes**: Nodes in the learned clause
- **Red edges**: Edges involved in the conflict
- The learned clause and backjump level in an info box

### Output

- **Text output**: Shows all nodes grouped by decision level with parent relationships
- **Visualization**: A hierarchical graph with:
  - Nodes arranged by decision level
  - Orange squares for decisions
  - Green squares for implications
  - Yellow badges showing decision level numbers
  - Directed arrows showing dependencies

## Creating Your Own Examples

To create a custom example, modify `example/example_graphs.py`:

```python
def create_your_example():
    problem = Problem(
        problem_statement="Your problem",
        lemmas=["Initial constraint 1", "Initial constraint 2"]
    )
    
    tree = Tree()
    
    # Level 0: Initial constraints
    tree.append_deductions([
        Deduction(reasoning="Given", text="Constraint 1", parents=[])
    ], decision_level=0, is_decision=False)
    
    # Level 1: First decision
    tree.append_deductions([
        Deduction(reasoning="Decision", text="Choice 1", parents=[0])
    ], decision_level=1, is_decision=True)
    
    # Level 1: Implications from decision
    tree.append_deductions([
        Deduction(reasoning="Propagation", text="Consequence", parents=[0, 1])
    ], decision_level=1, is_decision=False)
    
    return problem, tree
```

## Key Concepts

### Decision Level Definition

In CDCL, the **decision level** of a literal in the trail is the number of decision literals appearing before and up to that literal in the trail.

- Level 0: No decisions made yet (only initial constraints and their propagations)
- Level 1: After 1st decision and all its propagations
- Level 2: After 2nd decision and all its propagations
- And so on...

### Node Connectivity

All nodes (except Level 0 axioms) must have at least one parent, ensuring a connected DAG that traces the reasoning chain.

### Conflict Analysis and 1-UIP

When a conflict is detected, CDCL performs **conflict analysis** to learn why the conflict occurred:

1. **Start with the conflict clause**: The parents of the conflict node
2. **Perform resolution backward**: Replace literals with their antecedents (parents) working backward through the trail
3. **Find the 1-UIP**: The First Unique Implication Point - the first node in the conflict level such that all paths from the decision to the conflict pass through it
4. **Extract learned clause**: The clause formed at the 1-UIP cut, which will prevent this same conflict in the future
5. **Determine backjump level**: The second-highest decision level in the learned clause

This follows the algorithm described in the [Aalto University CDCL notes](https://users.aalto.fi/~tjunttil/2020-DP-AUT/notes-sat/cdcl.html).

### The ConflictAnalyzer Class

The `conflict_analysis.py` module provides programmatic access to conflict analysis:

```python
from conflict_analysis import ConflictAnalyzer
from example.example_graphs import create_sudoku_4x4_graph

# Load a graph
problem, tree = create_sudoku_4x4_graph()

# Create analyzer
analyzer = ConflictAnalyzer(tree)

# Analyze a conflict (e.g., node 17)
learned_clause, uip_node_id, backjump_level = analyzer.analyze_conflict(17)

print(f"1-UIP: {uip_node_id}")
print(f"Learned Clause: {learned_clause}")
print(f"Backjump to Level: {backjump_level}")
```

## Directory Structure

```
CDLM/
├── solve.py                    # Main solver (general CDLM framework)
├── problem_structure.py        # Core data structures (Problem, Tree, Node, etc.)
├── agents.py                   # LLM agents and prompt templates
├── conflict_analysis.py        # Conflict analysis and 1-UIP computation
├── visualize.py                # Graph visualization
├── *_user_prompt.md           # General prompt templates
├── example/                    # Example graphs
│   └── example_graphs.py
└── sudoku/                     # Sudoku-specific implementations
    ├── sudoku_helpers.py       # Grid parsing and candidate computation
    ├── sudoku_solver.py        # Sudoku-specific solver configuration
    ├── decision_user_prompt.md # Sudoku-specific decision prompt
    ├── problem.txt             # Example 9x9 sudoku puzzle
    ├── problem_easy.txt        # Easier sudoku puzzle
    └── README.md               # Sudoku-specific documentation
```

## Command-Line Usage

### Solver

```bash
# Set environment variables
export OPENAI_API_KEY=<your_api_key>
export OPENAI_BASE_URL=<your_base_url>

# Run logfire auth to visualize LLM calls
logfire auth

# Solve a sudoku puzzle (with domain-specific helpers)
python3 solve.py --problem_file sudoku/problem.txt --problem_type sudoku --verbose

# Solve with general solver (no domain-specific helpers)
python3 solve.py --problem_file sudoku/problem.txt --problem_type general --verbose

# Additional options
python3 solve.py --help
```

**Solver Options:**
- `--problem_file`: Path to problem file (required)
- `--problem_type`: Type of problem - `sudoku` (with helpers) or `general` (default: sudoku)
- `--deduction_effort`: Number of deductions per iteration (default: 1)
- `--max_iterations`: Maximum iterations before giving up (default: 100)
- `--verbose` or `-v`: Print detailed debugging information
- `--visualize`: Output file for graph visualization (e.g., 'graph.png')
- `--use_code_prop`: Use when you want to give the propagation agent a coding environment
- `--use_code_decision`: When when you want to give the decision agent a coding environment

**Command-Line Usage: Conflict Analysis**

```bash
# Analyze with automatic conflict detection
python3 conflict_analysis.py sudoku

# Specify conflict node explicitly
python3 conflict_analysis.py sudoku --conflict-id 17
```

**Returns:**
- `learned_clause`: Set of node IDs forming the learned clause
- `uip_node_id`: The node ID of the 1-UIP
- `backjump_level`: The decision level to backjump to

