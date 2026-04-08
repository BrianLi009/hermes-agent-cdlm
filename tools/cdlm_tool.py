#!/usr/bin/env python3
"""
CDLM Tool — Conflict-Driven Learning for Mathematical Reasoning

Exposes the CDLM solver as a set of Hermes tools with state-machine-enforced
transitions. The *calling* LLM is the reasoning engine: it produces the
deductions, conflict findings, decisions, and solutions itself, and passes
them in as tool arguments. The tools handle:

  * State machine validation (so the loop is run in a valid order)
  * Reasoning-tree bookkeeping (parent tracking, decision levels, lemmas)
  * Pure-Python conflict analysis (1-UIP / learned clause / backjump level)

NO external LLM API key is required. Earlier versions of this tool delegated
each phase to ``gpt-4.1`` via ``pydantic-ai``; that made no sense for an agent
skill, where the host LLM is already the agent.

State machine:
    INIT            → can: propagate
    PROPAGATED      → can: propagate, conflict_check
    NO_CONFLICT     → can: propagate, solution_check, decide
    CONFLICT        → must: backtrack
    DECIDED         → can: propagate
    SOLVED          → done (session is finished)

Tools registered:
    cdlm_init           — create a session with a problem statement
    cdlm_propagate      — add caller-supplied implications to the tree
    cdlm_conflict_check — record whether the caller found a contradiction
    cdlm_decide         — add a caller-chosen assumption to the tree
    cdlm_solution_check — record whether the caller has a complete solution
    cdlm_backtrack      — run conflict analysis, backjump, store lemma
    cdlm_status         — show current session state (tree, state, problem)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
#
# We only need ``problem_structure`` (Tree / Problem / pydantic models for the
# node payloads) and ``conflict_analysis`` (pure-Python 1-UIP). We deliberately
# do NOT import ``agents`` — that module pulls in pydantic-ai/OpenAI and is
# only needed by the standalone research script (CDLM/solve.py).
# ---------------------------------------------------------------------------

_CDLM_DIR = Path(__file__).resolve().parent.parent / "CDLM"


def _ensure_cdlm_path():
    cdlm_str = str(_CDLM_DIR)
    if cdlm_str not in sys.path:
        sys.path.insert(0, cdlm_str)


def _get_cdlm_modules():
    """Lazy-import the pure-Python CDLM modules."""
    _ensure_cdlm_path()
    from problem_structure import (
        Tree,
        Problem,
        Deduction,
        Decision,
        Conflict,
        Solution,
    )
    from conflict_analysis import ConflictAnalyzer
    return {
        "Tree": Tree,
        "Problem": Problem,
        "Deduction": Deduction,
        "Decision": Decision,
        "Conflict": Conflict,
        "Solution": Solution,
        "ConflictAnalyzer": ConflictAnalyzer,
    }


# ---------------------------------------------------------------------------
# Session storage
# ---------------------------------------------------------------------------

_sessions: Dict[str, Dict[str, Any]] = {}


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


def _allowed_actions(session: Dict[str, Any]) -> List[str]:
    return sorted(VALID_TRANSITIONS.get(session["state"], set()))


def _tree_summary(session: Dict[str, Any]) -> str:
    tree = session["tree"]
    return (
        f"State: {session['state']} | Nodes: {len(tree.nodes)} | "
        f"Decision level: {tree.curr_decision_level}"
    )


def _err(message: str, session: Optional[Dict[str, Any]] = None) -> str:
    payload: Dict[str, Any] = {"error": message}
    if session is not None:
        payload["status"] = _tree_summary(session)
        payload["allowed_actions"] = _allowed_actions(session)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def cdlm_init(problem_text: str, problem_type: str = "general", **kwargs) -> str:
    """Initialize a CDLM session with a problem statement."""
    task_id = kwargs.get("task_id", "default")

    if not problem_text or not problem_text.strip():
        return _err("problem_text is required and cannot be empty.")

    m = _get_cdlm_modules()
    problem = m["Problem"](problem_text)
    tree = m["Tree"]()
    # The default Tree uses curr_decision_level=1, which causes the very first
    # propagation batch (i.e. the level-0 "givens") to be filed at level 1.
    # Override to 0 so initial deductions land at level 0; the first call to
    # cdlm_decide will then bump curr_decision_level to 1 as expected.
    tree.curr_decision_level = 0

    session = {
        "problem": problem,
        "tree": tree,
        "problem_type": problem_type,
        "state": "INIT",
        "iteration": 0,
        "modules": m,
    }
    _sessions[task_id] = session

    return json.dumps({
        "success": True,
        "message": f"CDLM session initialized for problem type '{problem_type}'.",
        "problem": str(problem),
        "status": _tree_summary(session),
        "allowed_actions": _allowed_actions(session),
    })


def cdlm_propagate(deductions: List[Dict[str, Any]], **kwargs) -> str:
    """Add caller-supplied implications to the reasoning tree.

    Each deduction is a dict with:
      - text   (str): the actual statement, e.g. "Cell(0,1) = 2"
      - reasoning (str): why this follows from its parents
      - parents (list[int]): IDs of existing nodes that imply this one
                              (empty list for level-0 givens with no antecedents)
    """
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return _err("No active CDLM session. Call cdlm_init first.")

    err = _validate_transition(session, "propagate")
    if err:
        return _err(err, session)

    if deductions is None:
        deductions = []
    if not isinstance(deductions, list):
        return _err("deductions must be a list of {text, reasoning, parents} dicts.", session)

    m = session["modules"]
    tree = session["tree"]

    Deduction = m["Deduction"]
    parsed: List[Any] = []
    for i, d in enumerate(deductions):
        if not isinstance(d, dict):
            return _err(f"deductions[{i}] must be a dict, got {type(d).__name__}.", session)
        text = d.get("text")
        if not text:
            return _err(f"deductions[{i}].text is required.", session)
        reasoning = d.get("reasoning", "")
        parents = d.get("parents", []) or []
        if not isinstance(parents, list) or not all(isinstance(p, int) for p in parents):
            return _err(f"deductions[{i}].parents must be a list of integers.", session)
        try:
            parsed.append(Deduction(text=text, reasoning=reasoning, parents=parents))
        except Exception as exc:
            return _err(f"deductions[{i}] failed validation: {exc}", session)

    nodes_before = set(tree.nodes.keys())
    tree.append_deductions(parsed)
    nodes_after = set(tree.nodes.keys())
    new_ids = sorted(nodes_after - nodes_before)

    session["state"] = "PROPAGATED"

    return json.dumps({
        "success": True,
        "deductions_submitted": len(parsed),
        "deductions_added": len(new_ids),
        "new_node_ids": new_ids,
        "status": _tree_summary(session),
        "allowed_actions": _allowed_actions(session),
        "tree": str(tree),
    })


def cdlm_conflict_check(
    is_conflict: bool,
    reasoning: str = "",
    parents: Optional[List[int]] = None,
    **kwargs,
) -> str:
    """Record whether the caller found a contradiction in the current tree.

    Args:
      is_conflict: True if the caller has identified a contradiction.
      reasoning:   The caller's explanation (always recommended).
      parents:     Required when is_conflict=True — node IDs whose joint
                   assignments produce the contradiction. These become the
                   parents of the CONFLICT node and seed conflict analysis.
    """
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return _err("No active CDLM session. Call cdlm_init first.")

    err = _validate_transition(session, "conflict_check")
    if err:
        return _err(err, session)

    if not isinstance(is_conflict, bool):
        return _err("is_conflict must be a boolean.", session)

    m = session["modules"]
    tree = session["tree"]
    Conflict = m["Conflict"]

    if is_conflict:
        if not parents:
            return _err(
                "is_conflict=True requires a non-empty 'parents' list "
                "containing the node IDs that jointly cause the conflict.",
                session,
            )
        if not isinstance(parents, list) or not all(isinstance(p, int) for p in parents):
            return _err("parents must be a list of integers.", session)
        missing = [p for p in parents if p not in tree.nodes]
        if missing:
            return _err(
                f"parents reference unknown node IDs: {missing}. "
                f"Existing IDs: {sorted(tree.nodes.keys())}",
                session,
            )

        conflict = Conflict(
            reasoning=reasoning or "",
            is_conflict=True,
            parents=list(parents),
        )
        tree.append_deductions(conflict)
        session["state"] = "CONFLICT"
        return json.dumps({
            "success": True,
            "is_conflict": True,
            "reasoning": reasoning or "",
            "conflict_node_id": tree.conflict_id,
            "message": "Conflict recorded. You MUST call cdlm_backtrack next.",
            "status": _tree_summary(session),
            "allowed_actions": _allowed_actions(session),
            "tree": str(tree),
        })

    session["state"] = "NO_CONFLICT"
    return json.dumps({
        "success": True,
        "is_conflict": False,
        "reasoning": reasoning or "",
        "message": "No conflict. You can propagate more, check for a solution, or make a decision.",
        "status": _tree_summary(session),
        "allowed_actions": _allowed_actions(session),
    })


def cdlm_decide(text: str, reasoning: str = "", **kwargs) -> str:
    """Add a caller-chosen assumption (decision) to the tree.

    A decision opens a new decision level. Use the most-constrained-variable
    heuristic to pick what to decide on.
    """
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return _err("No active CDLM session. Call cdlm_init first.")

    err = _validate_transition(session, "decide")
    if err:
        return _err(err, session)

    if not text or not text.strip():
        return _err("decision 'text' is required and cannot be empty.", session)

    m = session["modules"]
    tree = session["tree"]
    Decision = m["Decision"]

    decision = Decision(reasoning=reasoning or "", text=text)
    nodes_before = set(tree.nodes.keys())
    tree.append_deductions(decision)
    nodes_after = set(tree.nodes.keys())
    new_ids = sorted(nodes_after - nodes_before)

    if not new_ids:
        return json.dumps({
            "success": False,
            "message": "Decision was not added (likely a duplicate of an existing node). Try a different decision.",
            "status": _tree_summary(session),
            "allowed_actions": _allowed_actions(session),
        })

    session["state"] = "DECIDED"
    return json.dumps({
        "success": True,
        "decision_node_id": new_ids[-1],
        "decision_text": text,
        "reasoning": reasoning or "",
        "decision_level": tree.curr_decision_level,
        "status": _tree_summary(session),
        "allowed_actions": _allowed_actions(session),
        "tree": str(tree),
    })


def cdlm_solution_check(
    is_solution: bool,
    reasoning: str = "",
    solution_text: Optional[str] = None,
    **kwargs,
) -> str:
    """Record whether the caller believes the current tree is a complete solution."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return _err("No active CDLM session. Call cdlm_init first.")

    err = _validate_transition(session, "solution_check")
    if err:
        return _err(err, session)

    if not isinstance(is_solution, bool):
        return _err("is_solution must be a boolean.", session)

    if is_solution:
        if not solution_text or not solution_text.strip():
            return _err(
                "is_solution=True requires 'solution_text' (the final answer).",
                session,
            )
        session["state"] = "SOLVED"
        return json.dumps({
            "success": True,
            "is_solution": True,
            "solution": solution_text,
            "reasoning": reasoning or "",
            "message": "Problem solved. Session is terminal.",
            "status": _tree_summary(session),
            "allowed_actions": _allowed_actions(session),
        })

    # Stay in NO_CONFLICT — caller can still propagate, decide, or check again.
    return json.dumps({
        "success": True,
        "is_solution": False,
        "reasoning": reasoning or "",
        "message": "Not yet solved. Continue propagating or make a decision.",
        "status": _tree_summary(session),
        "allowed_actions": _allowed_actions(session),
    })


def cdlm_backtrack(lemma: str, **kwargs) -> str:
    """Run conflict analysis, backjump, and record the caller-supplied lemma.

    Conflict analysis (1-UIP, learned clause, backjump level) is computed
    deterministically from the implication graph. The caller is responsible
    for translating the learned clause into a human-readable ``lemma`` — a
    constraint that prevents this conflict from recurring.
    """
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return _err("No active CDLM session. Call cdlm_init first.")

    err = _validate_transition(session, "backtrack")
    if err:
        return _err(err, session)

    if not lemma or not lemma.strip():
        return _err(
            "lemma is required: provide a concise constraint that prevents "
            "this conflict from recurring (e.g., 'Cell(1,2) != 1').",
            session,
        )

    m = session["modules"]
    tree = session["tree"]
    problem = session["problem"]

    if tree.conflict_id is None:
        return _err("No conflict to analyze (tree.conflict_id is None).", session)

    try:
        analyzer = m["ConflictAnalyzer"](tree)
        learned_clause, uip_node_id, backjump_level = analyzer.analyze_conflict(
            tree.conflict_id
        )
    except Exception as exc:
        logger.exception("Conflict analysis failed: %s", exc)
        return _err(f"Conflict analysis failed: {type(exc).__name__}: {exc}", session)

    # Snapshot the learned-clause literals BEFORE we mutate the tree.
    learned_clause_literals = [
        {"id": nid, "text": tree.nodes[nid].text, "level": tree.nodes[nid].decision_level}
        for nid in sorted(learned_clause)
        if nid in tree.nodes
    ]
    uip_text = tree.nodes[uip_node_id].text if uip_node_id in tree.nodes else None

    # Backjump: drop everything above the backjump level. Tree.remove_nodes
    # has a quirk where backjump_level==0 leaves curr_decision_level at 1
    # (so the next propagation batch would file at level 1 instead of 0);
    # snap it back to the actual backjump level here so level-0 propagations
    # post-backjump are filed correctly.
    tree.remove_nodes(backjump_level)
    tree.curr_decision_level = backjump_level

    # Persist the lemma so future propagations are informed by it.
    problem.lemmas.append(lemma)

    # After backtrack, the caller can propagate again (or immediately
    # conflict-check if they want — PROPAGATED allows both).
    session["state"] = "PROPAGATED"

    return json.dumps({
        "success": True,
        "learned_lemma": lemma,
        "backjump_level": backjump_level,
        "uip_node_id": uip_node_id,
        "uip_text": uip_text,
        "learned_clause": learned_clause_literals,
        "message": (
            f"Backjumped to level {backjump_level}. "
            f"Lemma stored: {lemma}"
        ),
        "status": _tree_summary(session),
        "allowed_actions": _allowed_actions(session),
        "tree": str(tree),
    })


def cdlm_status(**kwargs) -> str:
    """Show the current CDLM session state."""
    task_id = kwargs.get("task_id", "default")
    session = _get_session(task_id)
    if not session:
        return _err("No active CDLM session. Call cdlm_init first.")

    return json.dumps({
        "state": session["state"],
        "allowed_actions": _allowed_actions(session),
        "problem": str(session["problem"]),
        "tree": str(session["tree"]),
        "status": _tree_summary(session),
    })


# ---------------------------------------------------------------------------
# Availability gate (toggled by /cdlm slash command)
# ---------------------------------------------------------------------------

_cdlm_active = False


def activate_cdlm():
    global _cdlm_active
    _cdlm_active = True


def deactivate_cdlm():
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
        "The reasoning tree starts empty; you (the caller) drive each phase by "
        "calling cdlm_propagate / cdlm_conflict_check / cdlm_decide / "
        "cdlm_solution_check / cdlm_backtrack."
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
                "description": "Optional label for the problem type (e.g. 'sudoku', 'general').",
                "default": "general",
            },
        },
        "required": ["problem_text"],
    },
}

CDLM_PROPAGATE_SCHEMA = {
    "name": "cdlm_propagate",
    "description": (
        "Add implications you have derived from the current reasoning tree. "
        "Pass a list of {text, reasoning, parents} objects. Each deduction must "
        "be atomic (one fact per item) and must cite the IDs of the existing "
        "nodes that imply it (use [] for the initial level-0 givens that come "
        "directly from the problem statement). Can be called multiple times "
        "before checking for conflicts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "deductions": {
                "type": "array",
                "description": "List of implications to add to the tree.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The atomic implication, e.g. 'Cell(0,1) = 2'.",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this follows from the parents.",
                        },
                        "parents": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "Node IDs that jointly imply this deduction. "
                                "Use [] for level-0 givens with no antecedents."
                            ),
                        },
                    },
                    "required": ["text", "parents"],
                },
            },
        },
        "required": ["deductions"],
    },
}

CDLM_CONFLICT_CHECK_SCHEMA = {
    "name": "cdlm_conflict_check",
    "description": (
        "Record whether you have identified a contradiction in the reasoning "
        "tree. If is_conflict=True, you MUST supply 'parents' — the node IDs "
        "whose joint assignments produce the contradiction (these seed the "
        "conflict analysis). After a conflict, the only legal next action is "
        "cdlm_backtrack."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "is_conflict": {
                "type": "boolean",
                "description": "True if a contradiction has been identified.",
            },
            "reasoning": {
                "type": "string",
                "description": "Explanation of the contradiction (or why none exists).",
            },
            "parents": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Required when is_conflict=True. Node IDs that jointly "
                    "cause the contradiction."
                ),
            },
        },
        "required": ["is_conflict"],
    },
}

CDLM_DECIDE_SCHEMA = {
    "name": "cdlm_decide",
    "description": (
        "Add a caller-chosen assumption to the tree to explore the search "
        "space. A decision opens a new decision level. Only available after "
        "cdlm_conflict_check finds no conflict. Prefer the most-constrained "
        "variable (fewest remaining options) for the next decision."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The assumption, e.g. 'Cell(1,2) = 1'.",
            },
            "reasoning": {
                "type": "string",
                "description": "Why this is a good decision to try.",
            },
        },
        "required": ["text"],
    },
}

CDLM_SOLUTION_CHECK_SCHEMA = {
    "name": "cdlm_solution_check",
    "description": (
        "Record whether the current reasoning tree constitutes a complete "
        "solution. Only available after cdlm_conflict_check finds no conflict. "
        "If is_solution=True, supply solution_text with the final answer."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "is_solution": {
                "type": "boolean",
                "description": "True if the problem is solved.",
            },
            "reasoning": {
                "type": "string",
                "description": "Explanation of why the tree is (not) a complete solution.",
            },
            "solution_text": {
                "type": "string",
                "description": "Required when is_solution=True. The final answer.",
            },
        },
        "required": ["is_solution"],
    },
}

CDLM_BACKTRACK_SCHEMA = {
    "name": "cdlm_backtrack",
    "description": (
        "After a conflict, run conflict analysis (1-UIP / learned clause / "
        "backjump level is computed deterministically from the tree), drop "
        "every node above the backjump level, and store the caller-supplied "
        "lemma so future propagations are informed by it. The lemma should be "
        "a concise constraint that prevents this conflict from recurring "
        "(e.g. 'Cell(1,2) != 1')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "lemma": {
                "type": "string",
                "description": "Concise human-readable constraint learned from the conflict.",
            },
        },
        "required": ["lemma"],
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
    handler=lambda args, **kw: cdlm_propagate(
        deductions=args.get("deductions", []),
        **kw,
    ),
    check_fn=check_cdlm_available,
    emoji="🔗",
)

registry.register(
    name="cdlm_conflict_check",
    toolset="cdlm",
    schema=CDLM_CONFLICT_CHECK_SCHEMA,
    handler=lambda args, **kw: cdlm_conflict_check(
        is_conflict=args.get("is_conflict", False),
        reasoning=args.get("reasoning", ""),
        parents=args.get("parents"),
        **kw,
    ),
    check_fn=check_cdlm_available,
    emoji="⚡",
)

registry.register(
    name="cdlm_decide",
    toolset="cdlm",
    schema=CDLM_DECIDE_SCHEMA,
    handler=lambda args, **kw: cdlm_decide(
        text=args.get("text", ""),
        reasoning=args.get("reasoning", ""),
        **kw,
    ),
    check_fn=check_cdlm_available,
    emoji="🎯",
)

registry.register(
    name="cdlm_solution_check",
    toolset="cdlm",
    schema=CDLM_SOLUTION_CHECK_SCHEMA,
    handler=lambda args, **kw: cdlm_solution_check(
        is_solution=args.get("is_solution", False),
        reasoning=args.get("reasoning", ""),
        solution_text=args.get("solution_text"),
        **kw,
    ),
    check_fn=check_cdlm_available,
    emoji="✅",
)

registry.register(
    name="cdlm_backtrack",
    toolset="cdlm",
    schema=CDLM_BACKTRACK_SCHEMA,
    handler=lambda args, **kw: cdlm_backtrack(
        lemma=args.get("lemma", ""),
        **kw,
    ),
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
