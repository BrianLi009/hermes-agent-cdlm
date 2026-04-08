---
name: cdlm
description: >
  Conflict-Driven Learning for reasoning. A structured CDCL-style solver that
  maintains an implication graph of deductions and decisions, detects conflicts,
  learns lemmas via backjumping, and systematically explores the solution space.
  Use for combinatorial puzzles, constraint satisfaction, logic problems, planning,
  and any task that benefits from structured search with backtracking.
version: 0.1.0
author: Brian Li
metadata:
  hermes:
    tags: [reasoning, combinatorics, constraint-satisfaction, logic, cdcl, solver]
    category: reasoning
---

# CDLM - Conflict-Driven Learning Method

A systematic reasoning strategy inspired by CDCL (Conflict-Driven Clause Learning)
SAT solvers. Instead of reasoning about a problem in one shot, you maintain an
explicit **reasoning tree** and cycle through structured phases: deduce, check for
conflicts, backtrack with learned lessons, and make decisions to explore new
possibilities.

This method works for **any problem that involves deduction and decisions** --
combinatorial puzzles, scheduling, graph coloring, logic problems, planning under
constraints, and mathematical reasoning in general.

## When to Use

- Combinatorial or constraint satisfaction problems (Sudoku, N-Queens, scheduling, graph coloring)
- Logic puzzles and mathematical proofs requiring case analysis
- Planning problems with constraints that can conflict
- Any problem where you might need to try an assumption, discover it fails, and backtrack with new knowledge
- Problems where single-pass reasoning is unreliable and you need systematic exploration

## When NOT to Use

- Simple factual questions or lookups
- Creative writing or open-ended generation
- Problems with a single obvious solution path that needs no backtracking
- Tasks where approximate answers are acceptable

## Core Concepts

### The Reasoning Tree

The reasoning tree is a directed acyclic graph (DAG) that tracks every logical
step. Each node has:

- **ID**: Unique integer, assigned in order (0, 1, 2, ...)
- **Text**: The actual statement (e.g., "Cell(0,1) = 2")
- **Type**: IMPLICATION (forced by logic) or DECISION (assumed to explore)
- **Decision Level**: How many decisions deep this node is
- **Parents**: Which earlier nodes this was derived from

### Node Types

**Implications** are statements forced by existing knowledge:
> "Row 0 already has 1, 3, 4. Therefore Cell(0,2) = 2." (parents: nodes that established the row contents)

**Decisions** are assumptions made to explore the solution space:
> "Assume Cell(2,1) = 4." (no parents -- this is a choice)

**Conflicts** are contradictions discovered in the current state:
> "CONFLICT: Cell(3,2) must be both 3 and 2." (parents: the nodes that force both values)

### Decision Levels

- **Level 0**: Initial givens and anything deducible purely from the problem statement
- **Level 1**: Everything after the first decision (and deductions following from it)
- **Level N**: Everything after the Nth decision

Decision levels are critical for backtracking -- when a conflict is found, you
backjump to the appropriate level and undo everything above it.

### Learned Lemmas

When a conflict occurs, you analyze which combination of assignments caused it
and encode that as a **lemma** -- a new constraint that prevents the same
conflict pattern. Lemmas persist across backjumps and permanently narrow the
search space.

## CDLM Tools

When this skill is activated via `/cdlm`, you have access to the following tools.
**You MUST use these tools to execute the solver loop and drive every phase
yourself.** The tools do not call any external LLM — *you* are the reasoning
engine, and the tools handle state-machine validation, tree bookkeeping, and
the deterministic conflict-analysis math (1-UIP, learned clause, backjump
level). No API keys are required.

### Available Tools

| Tool | Description |
|------|-------------|
| `cdlm_init(problem_text, problem_type?)` | Initialize a session. Call this first. |
| `cdlm_propagate(deductions)` | Add the implications **you** have derived. |
| `cdlm_conflict_check(is_conflict, reasoning?, parents?)` | Record whether you found a contradiction. |
| `cdlm_solution_check(is_solution, reasoning?, solution_text?)` | Record whether the tree is now a complete solution. |
| `cdlm_decide(text, reasoning?)` | Add an assumption (decision) to explore. |
| `cdlm_backtrack(lemma)` | Run conflict analysis, backjump, and store the lemma you learned. |
| `cdlm_status()` | Show current session state, tree, and allowed actions. |

### How the Tools Work

You — the calling LLM — produce all of the *content* of each phase and pass
it in as arguments. The tools produce all of the *structure*:

* **`cdlm_propagate(deductions=[...])`** — pass a list of
  `{text, reasoning, parents}` objects. Each entry must be **atomic** (one
  fact per item) and must cite the IDs of existing tree nodes that imply it.
  Use `parents=[]` for the initial level-0 givens that come straight from the
  problem statement.

* **`cdlm_conflict_check(is_conflict=True, reasoning=..., parents=[...])`** —
  when you spot a contradiction, set `is_conflict=True` and supply the
  `parents` list (the node IDs whose joint assignments produce the conflict).
  These seed the conflict analysis. Use `is_conflict=False` to record that
  the current state is consistent.

* **`cdlm_decide(text=..., reasoning=...)`** — pick the most-constrained
  variable and pass your assumption as `text`. This opens a new decision
  level.

* **`cdlm_solution_check(is_solution=True, solution_text=...)`** — when the
  tree fully determines the answer, pass the final answer in `solution_text`.

* **`cdlm_backtrack(lemma=...)`** — runs 1-UIP / learned clause / backjump
  level computation deterministically from the implication graph, drops every
  node above the backjump level, and stores **your** human-readable `lemma`
  (e.g. `"Cell(1,2) != 1"`) so future propagations are informed by it. The
  return value tells you the backjump level, the UIP node, and the literals
  in the learned clause so you can confirm your reasoning.

Each tool returns the current `state`, the `allowed_actions` list, and a
serialized view of the tree, so you can always tell what's legal next.

> **Node IDs are never recycled.** After `cdlm_backtrack` removes the nodes
> above the backjump level, the next propagation gets the *next unused* ID,
> not the lowest free one. Always read the latest tree (from the previous
> tool's response or `cdlm_status`) to find the actual ID of any node you
> want to cite as a parent.

### State Machine

The tools enforce a valid execution order:

```
cdlm_init → cdlm_propagate (repeat as needed)
          → cdlm_conflict_check
              → conflict found → cdlm_backtrack → cdlm_propagate ...
              → no conflict → cdlm_solution_check or cdlm_decide
                                → solved → done
                                → not solved → cdlm_decide → cdlm_propagate ...
```

If you call a tool in the wrong state, it will return an error telling you
which actions are allowed. Use `cdlm_status` at any time to see where you are.

### Typical Workflow

1. `cdlm_init(problem_text="...")` — set up the session.
2. `cdlm_propagate(deductions=[...])` — pass the level-0 givens (parents `[]`)
   first, then call again to add deductions that follow from them. Repeat
   until no further deductions are visible.
3. `cdlm_conflict_check(is_conflict=..., parents=...)` — report whether you
   spotted a contradiction.
4. If conflict: `cdlm_backtrack(lemma="...")` → go to step 2.
5. If no conflict: `cdlm_solution_check(is_solution=...)` — report whether
   the tree fully solves the problem.
6. If not solved: `cdlm_decide(text="...")` → go to step 2.
7. If solved: report the solution.

### Key Principles

- **Propagate thoroughly** before checking for conflicts. Call `cdlm_propagate`
  multiple times if the tree is still growing — extract ALL deductions before
  moving on.
- **Always conflict-check before deciding.** The state machine enforces this.
- **Backtrack is mandatory after a conflict.** You cannot propagate or decide
  until you've backtracked.
- Each tool returns the current tree state and allowed next actions so you can
  track progress.

## The Solver Loop (What You Do vs. What the Tools Do)

### Propagate

**You** extract every deduction that follows from the current problem + tree
and submit them via `cdlm_propagate(deductions=[...])`. Each deduction must:
- Be **atomic** (one fact per node)
- Cite valid **parents** (the existing node IDs that imply it)
- Be **new** (the tool will skip duplicates by text)
- Follow logically from its parents plus the problem rules and any known
  lemmas

### Conflict Check

**You** examine the tree for contradictions and call
`cdlm_conflict_check(is_conflict=..., reasoning=..., parents=[...])`. When
`is_conflict=True`, the `parents` you supply become the parents of a CONFLICT
node and seed the conflict analysis.

### Backtrack (Conflict Analysis + Backjump)

When you call `cdlm_backtrack(lemma=...)`, the tool:
1. Finds the **1-UIP** (First Unique Implication Point) via graph analysis
2. Builds the **learned clause** from the conflict
3. Calculates the **backjump level**
4. Removes nodes above the backjump level
5. Stores **your** human-readable `lemma` in the problem's known constraints

The 1-UIP, learned clause, and backjump level are all returned to you, so you
can confirm the analysis matches your understanding of the conflict.

### Solution Check

**You** evaluate whether the current tree constitutes a complete solution and
call `cdlm_solution_check(is_solution=..., solution_text=...)`.

### Decide

**You** pick a variable to assume (prefer the most-constrained one) and call
`cdlm_decide(text=..., reasoning=...)`, which creates a new decision level in
the tree.

## Output Requirements

**You MUST output the full reasoning trace, not just the final answer.** The trace
is the primary output -- it shows the user exactly how the solution was derived,
which decisions were explored, what went wrong, and what was learned. The final
answer alone is insufficient.

Every response must include:

1. **The iteration-by-iteration trace** showing every phase executed
2. **The full reasoning tree** at key moments (after propagation, after conflicts, at the end)
3. **The final answer** clearly marked at the end

### Iteration Trace Format

Each iteration must show every phase with its inputs and outputs:

```
--- Iteration 1 ---

[PROPAGATE] Deducing from current state...
  Added [6] IMPLICATION: Cell(0,1) = 2 (Parents: 0, 1, 2)
    Reasoning: Row 0 has {1, 4}. Col 1 has {3}. Only candidate is 2.
  Added [7] IMPLICATION: Cell(0,2) = 3 (Parents: 0, 1, 6)
    Reasoning: Row 0 now has {1, 2, 4}. Only 3 remains.
  No more deductions possible.

[CONFLICT CHECK] Checking for contradictions...
  No conflict detected.

[SOLUTION CHECK] Checking if solved...
  Not yet complete -- 8 cells remain unassigned.

[DECIDE] Making decision...
  Candidates for Cell(1,0): {2} -- forced, adding as implication instead.
  Added [8] IMPLICATION: Cell(1,0) = 2 (Parents: 0, 2, 4)
  Most constrained open cell: Cell(1,2) with candidates {1, 4}.
  Added [9] DECISION: Cell(1,2) = 1
```

When a conflict occurs, show the full analysis:

```
--- Iteration 2 ---

[PROPAGATE] ...
  Added [10] IMPLICATION: Cell(1,3) = 4 (Parents: 9, 2, 8)

[CONFLICT CHECK] Checking for contradictions...
  CONFLICT DETECTED: Cell(1,3) = 4 contradicts Cell(0,3) = 4 in column 3.
  Added [11] CONFLICT (Parents: 1, 10)

[CONFLICT ANALYSIS]
  Conflict at decision level 1.
  Tracing back from conflict...
    Resolve Node 10 (level 1, parents: {9, 2, 8}) -> clause: {1, 9, 2, 8}
    Node 9 is the only level-1 node remaining.
  1-UIP: Node 9 (Cell(1,2) = 1)
  Learned clause: {9} -- Cell(1,2) = 1 causes conflict
  Learned lemma: Cell(1,2) != 1
  Backjump level: 0

[BACKJUMP] Removing all nodes above level 0. Lemma added.
```

### Reasoning Tree Snapshots

Display the full tree state after significant events -- conflicts, backjumps,
and at the end of the solve:

```
=== Reasoning Tree (after backjump) ===
Decision Level 0:
  [0] IMPLICATION: Cell(0,0) = 1 (given)
  [1] IMPLICATION: Cell(0,3) = 4 (given)
  [2] IMPLICATION: Cell(1,1) = 3 (given)
  [3] IMPLICATION: Cell(2,2) = 2 (given)
  [4] IMPLICATION: Cell(3,0) = 4 (given)
  [5] IMPLICATION: Cell(3,3) = 1 (given)
  [6] IMPLICATION: Cell(0,1) = 2 (Parents: 0, 1, 2)
  [7] IMPLICATION: Cell(0,2) = 3 (Parents: 0, 1, 6)
  [8] IMPLICATION: Cell(1,0) = 2 (Parents: 0, 2, 4)

Known Lemmas:
  1. Cell(1,2) != 1  [learned: iteration 2, conflict at level 1]
```

### Final Answer Format

After the solver terminates, output a clear summary:

```
=== SOLUTION FOUND (Iteration 5) ===

Final Reasoning Tree:
  [... full tree ...]

Solve Statistics:
  Total iterations: 5
  Decisions made: 2
  Conflicts encountered: 1
  Lemmas learned: 1
  Total deductions: 14

Answer:
  [1, 2, 3, 4]
  [2, 3, 4, 1]
  [3, 4, 2, 1]  -- wait, validate first
  ...

[Verified by code execution: solution satisfies all constraints.]
```

The statistics help the user understand the difficulty and structure of the
problem -- how much backtracking was needed and how much was learned.

## Use Code Execution

For combinatorial problems, use Python code to:
- Track the state precisely (e.g., a grid, a graph, a set of assignments)
- Compute remaining candidates for each variable
- Verify deductions and detect conflicts programmatically
- Validate the final solution

This prevents arithmetic and bookkeeping errors that are common in pure
text-based reasoning.

## Tips

- **Be thorough in propagation**: Extract ALL deductions before making a decision. Premature decisions lead to unnecessary backtracking.
- **Keep deductions atomic**: "Cell(1,2) = 4" is one deduction. Don't combine: "Cell(1,2) = 4 and Cell(1,3) = 1".
- **Track parents carefully**: Every implication must cite its parents. This is essential for conflict analysis.
- **Learn meaningful lemmas**: After a conflict, the learned lemma should be a useful, general constraint -- not just "that specific assignment was wrong".
- **Prefer constrained variables for decisions**: The most constrained variable (fewest options) is usually the best choice for the next decision.

## References

See `references/conflict-analysis.md` for the detailed conflict analysis algorithm
with worked examples of 1-UIP computation, learned clause extraction, and backjump
level calculation.

See `references/worked-example.md` for a complete walkthrough of CDLM applied to
a 4x4 Sudoku puzzle.
