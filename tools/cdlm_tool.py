#!/usr/bin/env python3
"""
CDLM Tool — Conflict-Driven Learning for Mathematical Reasoning

Exposes the CDLM solver as a set of Hermes tools with state-machine-enforced
transitions.  The LLM controls pacing (e.g. multiple propagations before a
conflict check) while code enforces that invalid transitions cannot happen.

State machine:
    INIT            → can: propagate
    PROPAGATED      → can: propagate, conflict_check
    NO_CONFLICT     → can: propagate, solution_check, decide
    CONFLICT        → must: backtrack
    DECIDED         → can: propagate
    SOLVED          → done (session is finished)

Tools registered:
    cdlm_init           — create a session with a problem statement
    cdlm_propagate      — derive logical implications from the current tree
    cdlm_conflict_check — check for contradictions in the tree
    cdlm_decide         — make an assumption to explore the search space
    cdlm_solution_check — check if the problem has been solved
    cdlm_backtrack      — analyze conflict, learn a lemma, and backjump
    cdlm_status         — show current session state (tree, state, problem)
"""

import json
import logging
import os
import sys
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------

STATES = {
    "INIT",
    "PROPAGATED",
    "NO_CONFLICT",
    "CONFLICT",
    "DECIDED",
    "SOLVED",
}

VALID_TRANSITIONS = {
    "INIT":         {"propagate"},
    "PROPAGATED":   {"propagate", "conflict_check"},
    "NO_CONFLICT":  {"propagate", "solution_check", "decide"},
    "CONFLICT":     {"backtrack"},
    "DECIDED":      {"propagate"},
    # SOLVED is terminal
}

# ---------------------------------------------------------------------------
# CDLM imports (lazy, from the CDLM subdir)
# ---------------------------------------------------------------------------

_CDLM_DIR = Path(__file__).resolve().parent.parent / "CDLM"


def _ensure_cdlm_path():
    """Add CDLM directory to sys.path so its modules can be imported."""
    cdlm_str = str(_CDLM_DIR)
    if cdlm_str not in sys.path:
        sys.path.insert(0, cdlm_str)


def _get_cdlm_modules():
    """Lazy-import CDLM modules.

    CDLM's agents.py reads prompt files via relative paths, so we temporarily
    chdir into the CDLM directory during import.
    """
    _ensure_cdlm_path()
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(str(_CDLM_DIR))
        from problem_structure import Tree, Problem, Deduction, Decision, Conflict, Solution
        from conflict_analysis import ConflictAnalyzer, analyze_and_print
        from agents import create_agents
        from agents import (
            prop_user_prompt,
            conflict_detection_user_prompt,
            decision_user_prompt,
            solution_checker_user_prompt,
            lemma_deducer_user_prompt,
        )
    finally:
        os.chdir(old_cwd)
    return {
        "Tree": Tree,
        "Problem": Problem,
        "Deduction": Deduction,
        "Decision": Decision,
        "Conflict": Conflict,
        "Solution": Solution,
        "ConflictAnalyzer": ConflictAnalyzer,
        "analyze_and_print": analyze_and_print,
        "create_agents": create_agents,
        "prop_user_prompt": prop_user_prompt,
        "conflict_detection_user_prompt": conflict_detection_user_prompt,
        "decision_user_prompt": decision_user_prompt,
        "solution_checker_user_prompt": solution_checker_user_prompt,
        "lemma_deducer_user_prompt": lemma_deducer_user_prompt,
    }


# ---------------------------------------------------------------------------
# Session storage
# ---------------------------------------------------------------------------

_sessions: Dict[str, Dict[str, Any]] = {}

# Default definitions (match CDLM solve.py defaults)
DEFAULT_DEDUCTION = "An implication that must be logically derived from existing knowledge (parents)."
DEFAULT_DECISION = "An assumption or design decision that need not be implied but is assumed to explore the solution space."


def _get_session(task_id: str) -> Optional[Dict[str, Any]]:
    return _sessions.get(task_id)


def _validate_transition(session: Dict[str, Any], action: str) -> Optional[str]:
    """Return an error message if the transition is invalid, else None."""
    state = session["state"]
    if state == "SOLVED":
        return "Session is already solved. Start a new session with cdlm_init."
    allowed = VALID_TRANSITIONS.get(state, set())
    if action not in allowed:
        return (
            f"Invalid action '{action}' in state '{state}'. "
            f"Allowed actions: {sorted(allowed)}"
        )
    return None


def _tree_summary(session: Dict[str, Any]) -> str:
    """Return a concise summary of the tree state."""
    tree = session["tree"]
    node_count = len(tree.nodes)
    decision_level = tree.curr_decision_level
    state = session["state"]
    return (
        f"State: {state} | Nodes: {node_count} | "
        f"Decision level: {decision_level}"
    )


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def cdlm_init(problem_text: str, problem_type: str = "general", **kwargs) -> str:
    """Initialize a CDLM session with a problem statement."""
    task_id = kwargs.get("task_id", "default")

    m = _get_cdlm_modules()
    problem = m["Problem"](problem_text)
    tree = m["Tree"]()

    # Create LLM agents for the session
    agents = m["create_agents"](
        use_code_prop=False,
        use_code_decision=False,
        use_code_solution=False,
        use_code_conflict=False,
    )
    prop_agent, conflict_agent, decision_agent, solution_agent, lemma_agent = agents

    session = {
        "problem": problem,
        "tree": tree,
        "problem_type": problem_type,
        "state": "INIT",
        "iteration": 0,
        "agents": {
            "prop": prop_agent,
            "conflict": conflict_agent,
            "decision": decision_agent,
            "solution": solution_agent,
            "lemma": lemma_agent,
        },
        "modules": m,
    }

    _sessions[task_id] = session

    return json.dumps({
        "success": True,
        "message": f"CDLM session initialized for problem type '{problem_type}'.",
        "problem": str(problem),
        "status": _tree_summary(session),
    })


def cdlm_propagate(**kwargs) -> str:
    """Derive logical implications from the current reasoning tree."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return json.dumps({"error": "No active CDLM session. Call cdlm_init first."})

    err = _validate_transition(session, "propagate")
    if err:
        return json.dumps({"error": err})

    m = session["modules"]
    prop_agent = session["agents"]["prop"]
    problem = session["problem"]
    tree = session["tree"]

    user_prompt = Template(m["prop_user_prompt"]).substitute({
        "PROBLEM": str(problem),
        "REASONING_TREE": str(tree),
        "DEFINITION": DEFAULT_DEDUCTION,
    })

    from pydantic_ai.usage import UsageLimits
    from pydantic_ai.exceptions import UsageLimitExceeded

    deductions = []
    try:
        deductions = prop_agent.run_sync(
            user_prompt, usage_limits=UsageLimits(tool_calls_limit=5)
        ).output
    except UsageLimitExceeded as e:
        logger.warning("Usage limit hit on prop agent: %s", e)

    tree.append_deductions(deductions)
    session["state"] = "PROPAGATED"

    deduction_texts = [d.text for d in deductions]
    return json.dumps({
        "success": True,
        "deductions_count": len(deductions),
        "deductions": deduction_texts,
        "status": _tree_summary(session),
        "tree": str(tree),
    })


def cdlm_conflict_check(**kwargs) -> str:
    """Check for contradictions in the reasoning tree."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return json.dumps({"error": "No active CDLM session. Call cdlm_init first."})

    err = _validate_transition(session, "conflict_check")
    if err:
        return json.dumps({"error": err})

    m = session["modules"]
    conflict_agent = session["agents"]["conflict"]
    problem = session["problem"]
    tree = session["tree"]

    user_prompt = Template(m["conflict_detection_user_prompt"]).substitute({
        "PROBLEM": str(problem),
        "REASONING_TREE": str(tree),
    })

    conflict = conflict_agent.run_sync(user_prompt).output

    if conflict.is_conflict:
        tree.append_deductions(conflict)
        session["state"] = "CONFLICT"
        return json.dumps({
            "success": True,
            "is_conflict": True,
            "reasoning": conflict.reasoning,
            "message": "Conflict detected! You must call cdlm_backtrack next.",
            "status": _tree_summary(session),
            "tree": str(tree),
        })
    else:
        session["state"] = "NO_CONFLICT"
        return json.dumps({
            "success": True,
            "is_conflict": False,
            "reasoning": conflict.reasoning,
            "message": "No conflict. You can propagate more, check for a solution, or make a decision.",
            "status": _tree_summary(session),
        })


def cdlm_decide(**kwargs) -> str:
    """Make an assumption/decision to explore the search space."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return json.dumps({"error": "No active CDLM session. Call cdlm_init first."})

    err = _validate_transition(session, "decide")
    if err:
        return json.dumps({"error": err})

    m = session["modules"]
    decision_agent = session["agents"]["decision"]
    problem = session["problem"]
    tree = session["tree"]

    user_prompt = Template(m["decision_user_prompt"]).substitute({
        "PROBLEM": str(problem),
        "REASONING_TREE": str(tree),
        "DEFINITION": DEFAULT_DECISION,
    })

    from pydantic_ai.usage import UsageLimits
    from pydantic_ai.exceptions import UsageLimitExceeded

    decision = None
    try:
        decision = decision_agent.run_sync(
            user_prompt, usage_limits=UsageLimits(tool_calls_limit=5)
        ).output
    except UsageLimitExceeded as e:
        logger.warning("Usage limit hit on decision agent: %s", e)

    if decision and decision.text:
        tree.append_deductions(decision)
        session["state"] = "DECIDED"
        return json.dumps({
            "success": True,
            "decision": decision.text,
            "reasoning": decision.reasoning,
            "status": _tree_summary(session),
            "tree": str(tree),
        })
    else:
        return json.dumps({
            "success": False,
            "message": "Decision agent returned empty decision. Try propagating more first.",
            "status": _tree_summary(session),
        })


def cdlm_solution_check(**kwargs) -> str:
    """Check if the problem has been solved by the current reasoning tree."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return json.dumps({"error": "No active CDLM session. Call cdlm_init first."})

    err = _validate_transition(session, "solution_check")
    if err:
        return json.dumps({"error": err})

    m = session["modules"]
    solution_agent = session["agents"]["solution"]
    problem = session["problem"]
    tree = session["tree"]

    user_prompt = Template(m["solution_checker_user_prompt"]).substitute({
        "PROBLEM": str(problem),
        "REASONING_TREE": str(tree),
    })

    solution = solution_agent.run_sync(user_prompt).output

    if solution.is_solution:
        session["state"] = "SOLVED"
        return json.dumps({
            "success": True,
            "is_solution": True,
            "solution": solution.solution_text,
            "message": "Problem solved!",
            "status": _tree_summary(session),
        })
    else:
        # Stay in NO_CONFLICT — user can still propagate, decide, or check again
        return json.dumps({
            "success": True,
            "is_solution": False,
            "reasoning": solution.reasoning,
            "message": "Not yet solved. Continue propagating or make a decision.",
            "status": _tree_summary(session),
        })


def cdlm_backtrack(**kwargs) -> str:
    """Analyze the conflict, learn a lemma, and backjump."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return json.dumps({"error": "No active CDLM session. Call cdlm_init first."})

    err = _validate_transition(session, "backtrack")
    if err:
        return json.dumps({"error": err})

    m = session["modules"]
    tree = session["tree"]
    problem = session["problem"]
    lemma_agent = session["agents"]["lemma"]

    try:
        learned_clause, uip_node_id, backjump_level = m["analyze_and_print"](tree)
        if learned_clause is None:
            return json.dumps({
                "error": "Could not analyze conflict.",
                "status": _tree_summary(session),
            })

        # Build constraint string from learned clause
        constraint_parts = []
        for nid in sorted(learned_clause):
            if nid in tree.nodes:
                constraint_parts.append(tree.nodes[nid].text)

        if not constraint_parts:
            return json.dumps({
                "error": "No valid nodes in learned clause.",
                "status": _tree_summary(session),
            })

        # Learn a new lemma
        user_prompt = Template(m["lemma_deducer_user_prompt"]).substitute({
            "PROBLEM": str(problem),
            "CONSTRAINTS": f"  NOT({' AND '.join(constraint_parts)})",
        })

        # Backjump: remove nodes above the backjump level
        tree.remove_nodes(backjump_level)

        # Extract lemma
        lemma = lemma_agent.run_sync(user_prompt).output
        problem.lemmas.append(lemma)

        session["state"] = "PROPAGATED"  # After backtrack, can propagate again

        return json.dumps({
            "success": True,
            "learned_lemma": lemma,
            "backjump_level": backjump_level,
            "uip_node": uip_node_id,
            "learned_clause_nodes": sorted(learned_clause),
            "message": f"Backtracked to level {backjump_level}. Learned lemma: {lemma}",
            "status": _tree_summary(session),
            "tree": str(tree),
        })

    except Exception as e:
        logger.exception("Error during conflict analysis: %s", e)
        return json.dumps({
            "error": f"Conflict analysis failed: {type(e).__name__}: {e}",
            "status": _tree_summary(session),
        })


def cdlm_status(**kwargs) -> str:
    """Show current CDLM session state."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return json.dumps({"error": "No active CDLM session. Call cdlm_init first."})

    state = session["state"]
    allowed = sorted(VALID_TRANSITIONS.get(state, set()))

    return json.dumps({
        "state": state,
        "allowed_actions": allowed,
        "problem": str(session["problem"]),
        "tree": str(session["tree"]),
        "status": _tree_summary(session),
    })


# ---------------------------------------------------------------------------
# Availability gate
# ---------------------------------------------------------------------------

_cdlm_active = False


def activate_cdlm():
    """Enable CDLM tools for this process."""
    global _cdlm_active
    _cdlm_active = True


def deactivate_cdlm():
    """Disable CDLM tools for this process."""
    global _cdlm_active
    _cdlm_active = False


def check_cdlm_available() -> bool:
    return _cdlm_active


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

CDLM_INIT_SCHEMA = {
    "name": "cdlm_init",
    "description": (
        "Initialize a CDLM (Conflict-Driven Learning) session for solving a "
        "combinatorial reasoning problem. Provide the problem statement as text. "
        "This sets up the reasoning tree and LLM agents needed for the solve loop."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "problem_text": {
                "type": "string",
                "description": "The full problem statement to solve.",
            },
            "problem_type": {
                "type": "string",
                "description": "Type of problem: 'general' (default) or 'sudoku'.",
                "default": "general",
            },
        },
        "required": ["problem_text"],
    },
}

CDLM_PROPAGATE_SCHEMA = {
    "name": "cdlm_propagate",
    "description": (
        "Derive logical implications (deductions) from the current reasoning tree. "
        "Can be called multiple times before checking for conflicts. "
        "Each call adds new nodes to the implication graph."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CDLM_CONFLICT_CHECK_SCHEMA = {
    "name": "cdlm_conflict_check",
    "description": (
        "Check the reasoning tree for contradictions. Must be called after at least "
        "one propagation. If a conflict is found, you MUST call cdlm_backtrack next."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CDLM_DECIDE_SCHEMA = {
    "name": "cdlm_decide",
    "description": (
        "Make an assumption/decision to explore the solution space. Only available "
        "after a conflict check finds no conflict. Increments the decision level."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CDLM_SOLUTION_CHECK_SCHEMA = {
    "name": "cdlm_solution_check",
    "description": (
        "Check if the current reasoning tree constitutes a complete solution. "
        "Only available after a conflict check finds no conflict."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CDLM_BACKTRACK_SCHEMA = {
    "name": "cdlm_backtrack",
    "description": (
        "Analyze the conflict in the reasoning tree, find the 1-UIP, learn a new "
        "lemma (constraint), and backjump to an earlier decision level. Only available "
        "when a conflict has been detected."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

CDLM_STATUS_SCHEMA = {
    "name": "cdlm_status",
    "description": (
        "Show the current CDLM session state: problem, reasoning tree, "
        "current state, and allowed next actions."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from tools.registry import registry

registry.register(
    name="cdlm_init",
    toolset="cdlm",
    schema=CDLM_INIT_SCHEMA,
    handler=lambda args, **kw: cdlm_init(
        problem_text=args.get("problem_text", ""),
        problem_type=args.get("problem_type", "general"),
        **kw,
    ),
    check_fn=check_cdlm_available,
    emoji="🧠",
)

registry.register(
    name="cdlm_propagate",
    toolset="cdlm",
    schema=CDLM_PROPAGATE_SCHEMA,
    handler=lambda args, **kw: cdlm_propagate(**kw),
    check_fn=check_cdlm_available,
    emoji="🔗",
)

registry.register(
    name="cdlm_conflict_check",
    toolset="cdlm",
    schema=CDLM_CONFLICT_CHECK_SCHEMA,
    handler=lambda args, **kw: cdlm_conflict_check(**kw),
    check_fn=check_cdlm_available,
    emoji="⚡",
)

registry.register(
    name="cdlm_decide",
    toolset="cdlm",
    schema=CDLM_DECIDE_SCHEMA,
    handler=lambda args, **kw: cdlm_decide(**kw),
    check_fn=check_cdlm_available,
    emoji="🎯",
)

registry.register(
    name="cdlm_solution_check",
    toolset="cdlm",
    schema=CDLM_SOLUTION_CHECK_SCHEMA,
    handler=lambda args, **kw: cdlm_solution_check(**kw),
    check_fn=check_cdlm_available,
    emoji="✅",
)

registry.register(
    name="cdlm_backtrack",
    toolset="cdlm",
    schema=CDLM_BACKTRACK_SCHEMA,
    handler=lambda args, **kw: cdlm_backtrack(**kw),
    check_fn=check_cdlm_available,
    emoji="↩️",
)

registry.register(
    name="cdlm_status",
    toolset="cdlm",
    schema=CDLM_STATUS_SCHEMA,
    handler=lambda args, **kw: cdlm_status(**kw),
    check_fn=check_cdlm_available,
    emoji="📊",
)
