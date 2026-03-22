from agents import create_agents
from agents import prop_user_prompt, conflict_detection_user_prompt, decision_user_prompt, solution_checker_user_prompt, lemma_deducer_user_prompt
from problem_structure import Tree, Problem
from string import Template
from conflict_analysis import analyze_and_print
from pydantic_ai.usage import UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded

import sys
sys.stdout.reconfigure(encoding='utf-8')

import logfire

# 1. Initialize Logfire
logfire.configure()

# 2. Instrument Pydantic AI globally
logfire.instrument_pydantic_ai()

# Default definitions (can be overridden for specific problem types)
DEFAULT_DEDUCTION = "An implication that must be logically derived from existing knowledge (parents)."
DEFAULT_DECISION = "An assumption or design decision that need not be implied but is assumed to explore the solution space."
# DEFAULT_DECISION = "An assumption regarding the solution of the sudoku puzzle. This can be the exact value of a cell or a relationship between values of cells. This need not be implied but is assumed."

PROP_CODE_INSTRUCTIONS = """\nYou are provided with a python coding tool. You can use this tool to generate and execute python code to help you produce accurate deductions. However dont waste tokens on too many tool calls - no more than 5 tool calls!!"""
DECISION_CODE_INSTRUCTIONS = """\nYou are provided with a python coding tool. You can use this tool to generate and execute python code to help you determine your valid options and make an informed decision. However dont waste tokens on too many tool calls - no more than 3 tool calls."""
SOLUTION_CODE_INSTRUCTIONS = """\nYou are provided with a python coding tool. You can use this tool to generate and execute python code to help you verify whether the current state constitutes a valid solution. However dont waste tokens on too many tool calls - no more than 3 tool calls."""
CONFLICT_CODE_INSTRUCTIONS = """\nYou are provided with a python coding tool. You can use this tool to generate and execute python code to help you detect conflicts and contradictions in the reasoning tree. However dont waste tokens on too many tool calls - no more than 3 tool calls."""

class Solver:
    def __init__(
        self, 
        problem: Problem, 
        tree: Tree = None, 
        deduction_effort: int = 1, 
        verbose: bool = False,
        deduction_definition: str = None,
        decision_definition: str = None,
        decision_prompt_fn: callable = None,
        use_code_prop: bool = False,
        use_code_decision: bool = False,
        use_code_solution: bool = False,
        use_code_conflict: bool = False
    ):
        """
        Initialize the CDLM Solver.

        Args:
            problem: The problem to solve
            tree: Optional existing tree to continue from
            deduction_effort: Number of deductions per propagation call
            verbose: Print detailed debugging information
            deduction_definition: Custom definition for deductions (uses DEFAULT_DEDUCTION if None)
            decision_definition: Custom definition for decisions (uses DEFAULT_DECISION if None)
            decision_prompt_fn: Optional function(problem, tree) -> (prompt_str, debug_info)
                               for custom decision prompts. If None, uses default prompt.
        """
        self.problem = problem
        self.tree = tree if tree else Tree()
        self.deduction_effort = deduction_effort
        self.verbose = verbose
        self.deduction_definition = deduction_definition or DEFAULT_DEDUCTION
        self.decision_definition = decision_definition or DEFAULT_DECISION
        self.decision_prompt_fn = decision_prompt_fn
        self.use_code_prop = use_code_prop
        self.use_code_decision = use_code_decision
        self.use_code_solution = use_code_solution
        self.use_code_conflict = use_code_conflict

    def _print_tree_state(self, label: str = "Current Tree State"):
        """Print the current state of the reasoning tree."""
        if not self.verbose:
            return
        print(f"\n  === {label} ===")
        if not self.tree.nodes:
            print("  (empty tree)")
        else:
            # Group by decision level
            levels = {}
            for node_id, node in self.tree.nodes.items():
                if node.decision_level not in levels:
                    levels[node.decision_level] = []
                levels[node.decision_level].append((node_id, node))
            
            for level in sorted(levels.keys()):
                print(f"  Level {level}:")
                for node_id, node in sorted(levels[level]):
                    node_type = "DECISION" if node.is_decision else "IMPLICATION"
                    parents_str = f" (parents: {node.parents})" if node.parents else ""
                    print(f"    [{node_id}] {node_type}: {node.text}{parents_str}")
        print()

    def propagate(self):
        user_prompt = Template(prop_user_prompt).substitute({
            "PROBLEM": str(self.problem),
            "REASONING_TREE": str(self.tree),
            "DEFINITION": self.deduction_definition,
            # "DEDUCTION_EFFORT": str(self.deduction_effort)
        })

        if self.use_code_prop:
            user_prompt += PROP_CODE_INSTRUCTIONS

        if self.verbose:
            print(f"\n  [PROPAGATE] Sending prompt to prop_agent...")
        deductions = []
        try:
            deductions = prop_agent.run_sync(user_prompt, usage_limits=UsageLimits(tool_calls_limit=5)).output
        except UsageLimitExceeded as e:
            print(f"Usage limit hit on prop agent: {e}")
            # print(e)
        if self.verbose:
            print(f"  [PROPAGATE] Received {len(deductions)} deduction(s):")
            for d in deductions:
                print(f"    - \"{d.text}\" (parents: {d.parents})")

        self.tree.append_deductions(deductions)
        
        if self.verbose:
            self._print_tree_state("After Propagation")

        return

    def conflict_check(self):
        user_prompt = Template(conflict_detection_user_prompt).substitute({
            "PROBLEM": str(self.problem),
            "REASONING_TREE": str(self.tree)
        })

        if self.use_code_conflict:
            user_prompt += CONFLICT_CODE_INSTRUCTIONS

        if self.verbose:
            print(f"\n  [CONFLICT CHECK] Sending prompt to conflict_detection_agent...")

        conflict = conflict_detection_agent.run_sync(user_prompt).output

        if self.verbose:
            print(f"  [CONFLICT CHECK] Result:")
            print(f"    is_conflict: {conflict.is_conflict}")
            print(f"    reasoning: {conflict.reasoning}")
            if conflict.is_conflict:
                print(f"    parents (causing conflict): {conflict.parents}")

        if conflict.is_conflict:
            self.tree.append_deductions(conflict)
            if self.verbose:
                self._print_tree_state("After Adding Conflict Node")
        
        return conflict.is_conflict
    
    def solution_check(self):
        user_prompt = Template(solution_checker_user_prompt).substitute({
            "PROBLEM": str(self.problem),
            "REASONING_TREE": str(self.tree)
        })

        if self.use_code_solution:
            user_prompt += SOLUTION_CODE_INSTRUCTIONS

        if self.verbose:
            print(f"\n  [SOLUTION CHECK] Sending prompt to solution_checker_agent...")

        solution = solution_checker_agent.run_sync(user_prompt).output

        if self.verbose:
            print(f"  [SOLUTION CHECK] Result:")
            print(f"    is_solution: {solution.is_solution}")
            if solution.is_solution:
                print(f"    solution_text: {solution.solution_text}")

        return solution
    
    def decide(self):
        # Use custom decision prompt function if provided, otherwise use default
        if self.decision_prompt_fn:
            user_prompt, debug_info = self.decision_prompt_fn(self.problem, self.tree)
            
            if self.verbose:
                print(f"\n  [DECIDE] Sending prompt to decision_agent...")
                if debug_info:
                    print(f"  [DECIDE] Domain-specific info:")
                    # Indent each line for better readability
                    for line in debug_info.split('\n'):
                        if line.strip():
                            print(f"    {line}")
        else:
            # Default decision prompt
            user_prompt = Template(decision_user_prompt).substitute({
                "PROBLEM": str(self.problem),
                "REASONING_TREE": str(self.tree),
                "DEFINITION": self.decision_definition
            })
            
            if self.verbose:
                print(f"\n  [DECIDE] Sending prompt to decision_agent...")

        if self.use_code_decision:
            user_prompt += DECISION_CODE_INSTRUCTIONS
        decision = None
        try:
            decision = decision_agent.run_sync(user_prompt, usage_limits=UsageLimits(tool_calls_limit=5)).output
        except UsageLimitExceeded as e:
            print(f"Usage limit hit on decision agent: {e}")
            # print(e)

        if self.verbose:
            print(f"  [DECIDE] Result:")
            print(f"    text: \"{decision.text}\"")

        if decision.text != "" and decision.text is not None:
            self.tree.append_deductions(decision)
            if self.verbose:
                self._print_tree_state("After Decision")

        return
    
    def lemma_extract(self, user_prompt: str):
        if self.verbose:
            print(f"\n  [LEMMA EXTRACT] Sending prompt to lemma_deducer_agent...")

        lemma = lemma_deducer_agent.run_sync(user_prompt).output

        if self.verbose:
            print(f"  [LEMMA EXTRACT] Learned lemma: \"{lemma}\"")

        self.problem.lemmas.append(lemma)

def run_solver(
    problem: Problem, 
    tree: Tree = None, 
    deduction_effort: int = 1, 
    max_iterations: int = 100, 
    verbose: bool = False,
    deduction_definition: str = None,
    decision_definition: str = None,
    decision_prompt_fn: callable = None,
    use_code_prop: bool = False,
    use_code_decision: bool = False,
    use_code_solution: bool = False,
    use_code_conflict: bool = False
) -> str:
    """
    Run the CDCL-style solver.

    Args:
        problem: The problem to solve
        tree: Optional existing tree to continue from
        deduction_effort: Number of deductions per propagation call
        max_iterations: Maximum iterations before giving up (default: 100)
        verbose: Print detailed debugging information (default: False)
        deduction_definition: Custom definition for deductions
        decision_definition: Custom definition for decisions
        decision_prompt_fn: Optional custom function for decision prompts

    Returns:
        Solution text if found, None otherwise
    """
    solver = Solver(
        problem,
        tree,
        deduction_effort=deduction_effort,
        verbose=verbose,
        deduction_definition=deduction_definition,
        decision_definition=decision_definition,
        decision_prompt_fn=decision_prompt_fn,
        use_code_prop=use_code_prop,
        use_code_decision=use_code_decision,
        use_code_solution=use_code_solution,
        use_code_conflict=use_code_conflict
    )
    
    iteration = 1
    no_progress_count = 0  # Track iterations with no progress

    while iteration <= max_iterations:
        print(f"---------- Iteration {iteration} ----------")
        
        tree_size_before = len(solver.tree.nodes)
        
        print(f"propagating...")
        solver.propagate()

        print(f"conflict checking...")
        is_conflict = solver.conflict_check()

        if is_conflict:
            print(f"conflict detected! analyzing...")
            no_progress_count = 0  # Reset no-progress counter on conflict
            try:
                learned_clause, uip_node_id, backjump_level = analyze_and_print(solver.tree)
                if learned_clause is None:
                    print("Error: Could not analyze conflict")
                    return None
                
                # Build constraint string safely - check nodes exist before accessing
                constraint_parts = []
                for nid in sorted(learned_clause):
                    if nid in solver.tree.nodes:
                        constraint_parts.append(solver.tree.nodes[nid].text)
                    else:
                        print(f"Warning: Node {nid} in learned clause no longer exists")
                
                if not constraint_parts:
                    print("Error: No valid nodes in learned clause")
                    return None
                
                user_prompt = Template(lemma_deducer_user_prompt).substitute({
                    "PROBLEM": str(solver.problem),
                    "CONSTRAINTS": f"  NOT({' AND '.join(constraint_parts)})"
                })
                solver.tree.remove_nodes(backjump_level)
                print(f"extracting lemma...")
                solver.lemma_extract(user_prompt)
            except Exception as e:
                print(f"Error during conflict analysis: {e}")
                return None
        else:
            print(f"no conflict detected! checking for solution...")
            solution = solver.solution_check()
            if solution.is_solution:
                return solution.solution_text
            
            print(f"no solution found! making a decision...")
            tree_size_before_decision = len(solver.tree.nodes)
            solver.decide()
            tree_size_after_decision = len(solver.tree.nodes)
            
            # Check if decision was made (tree grew)
            if tree_size_after_decision == tree_size_before_decision:
                no_progress_count += 1
                print(f"Warning: No decision was made (empty decision). No-progress count: {no_progress_count}")
                
                if no_progress_count >= 3:
                    print("Error: Solver stuck - no progress after 3 consecutive iterations")
                    return None
            else:
                no_progress_count = 0

        iteration += 1
    
    print(f"Error: Maximum iterations ({max_iterations}) reached without finding a solution")
    return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--problem_file",
        type=str,
        required=True,
        help="The file containing the problem description."
    )
    
    parser.add_argument(
        "--problem_type",
        type=str,
        default="sudoku",
        choices=["sudoku", "general"],
        help="Type of problem to solve. 'sudoku' uses domain-specific helpers, 'general' uses default solver (default: sudoku)."
    )
    
    parser.add_argument(
        "--deduction_effort",
        type=int,
        default=1,
        help="Number of deductions the propagation agent should make per iteration (default: 1)."
    )
    
    parser.add_argument(
        "--max_iterations",
        type=int,
        default=100,
        help="Maximum number of iterations before giving up (default: 100)."
    )
    
    parser.add_argument(
        "--visualize",
        type=str,
        default=None,
        help="Output file for graph visualization (e.g., 'graph.png'). Requires matplotlib and networkx."
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed debugging information about deductions, decisions, and tree state."
    )
    
    parser.add_argument(
        "--use_code_prop",
        action="store_true",
        help="Use code tool in the propagation agent."
    )
    
    parser.add_argument(
        "--use_code_decision",
        action="store_true",
        help="Use code tool in the decision agent."
    )

    parser.add_argument(
        "--use_code_solution",
        action="store_true",
        help="Use code tool in the solution checker agent."
    )

    parser.add_argument(
        "--use_code_conflict",
        action="store_true",
        help="Use code tool in the conflict detection agent."
    )

    args = parser.parse_args()
    prop_agent, conflict_detection_agent, decision_agent, solution_checker_agent, lemma_deducer_agent = create_agents(
        use_code_prop=args.use_code_prop,
        use_code_decision=args.use_code_decision,
        use_code_solution=args.use_code_solution,
        use_code_conflict=args.use_code_conflict
    )

    with open(args.problem_file, "r") as f:
        problem_text = f.read()
    
    problem = Problem(problem_text)
    tree = Tree()

    # Configure solver based on problem type
    if args.problem_type == "sudoku":
        from sudoku.sudoku_solver import create_sudoku_decision_prompt, get_sudoku_definitions
        deduction_def, decision_def = get_sudoku_definitions()
        
        print("Using sudoku-specific solver with candidate computation...")
        solution = run_solver(
            problem, 
            tree=tree, 
            deduction_effort=args.deduction_effort, 
            max_iterations=args.max_iterations, 
            verbose=args.verbose,
            deduction_definition=deduction_def,
            decision_definition=decision_def,
            decision_prompt_fn=create_sudoku_decision_prompt,
            use_code_prop=args.use_code_prop,
            use_code_decision=args.use_code_decision,
            use_code_solution=args.use_code_solution,
            use_code_conflict=args.use_code_conflict
        )
    else:
        print("Using general solver...")
        solution = run_solver(
            problem,
            tree=tree,
            deduction_effort=args.deduction_effort,
            max_iterations=args.max_iterations,
            verbose=args.verbose,
            use_code_prop=args.use_code_prop,
            use_code_decision=args.use_code_decision,
            use_code_solution=args.use_code_solution,
            use_code_conflict=args.use_code_conflict
        )

    print(f"Solution: {solution}")
    
    if args.visualize:
        from visualize import visualize_tree
        print(f"\nGenerating visualization...")
        visualize_tree(problem, tree, args.visualize)


            
            
















    