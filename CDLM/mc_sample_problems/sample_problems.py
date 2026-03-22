"""
Sample 10 random problems from the mathconstruct project,
generate valid problem instances, and write them to individual .txt files.
Also produces a problem_links.txt metadata file.

This script parses the mathconstruct source files directly using AST,
so it does NOT require the mathconstruct package or its dependencies
to be installed.
"""

import ast
import glob
import os
import random
import re
import traceback

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MATHCONSTRUCT_ROOT = os.path.join(
    os.path.expanduser("~"), "Documents", "mathconstruct", "src"
)
PROBLEMS_DIR = os.path.join(
    MATHCONSTRUCT_ROOT, "math_construct", "problems"
)
TEMPLATES_FILE = os.path.join(PROBLEMS_DIR, "templates.py")

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
NUM_PROBLEMS = 10

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_templates() -> dict[str, str]:
    """Execute templates.py and return the TEMPLATES dict."""
    with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
        src = f.read()
    ns: dict = {}
    exec(compile(src, TEMPLATES_FILE, "exec"), ns)
    return ns["TEMPLATES"]


def _literal_or_none(node: ast.expr):
    """Try to evaluate an AST node as a Python literal. Return None on failure."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def extract_metadata(filepath: str) -> dict | None:
    """
    Parse a problem .py file and extract:
      - template_key : str          (key into TEMPLATES dict)
      - original_parameters : dict  (parameter values from original_parameters=...)
      - problem_url : str | None
      - solution_url : str | None
      - source : str | None
      - name_arg : str | None       (the name string passed to ProblemConfig, if literal)
    Returns None if the file cannot be parsed or lacks needed data.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        src = f.read()

    # --- template key ---------------------------------------------------
    # Pattern: TEMPLATES["some/key.py"]
    m = re.search(r'TEMPLATES\["([^"]+)"\]', src)
    if not m:
        m = re.search(r"TEMPLATES\['([^']+)'\]", src)
    if not m:
        return None
    template_key = m.group(1)

    # --- AST-based extraction of ProblemConfig kwargs --------------------
    try:
        tree = ast.parse(src, filename=filepath)
    except SyntaxError:
        return None

    original_parameters = None
    problem_url = None
    solution_url = None
    source = None
    name_arg = None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Look for ProblemConfig(...)
        func = node.func
        func_name = None
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr
        if func_name != "ProblemConfig":
            continue

        for kw in node.keywords:
            val = _literal_or_none(kw.value)
            if kw.arg == "original_parameters" and isinstance(val, dict):
                original_parameters = val
            elif kw.arg == "problem_url" and isinstance(val, str):
                problem_url = val
            elif kw.arg == "solution_url" and isinstance(val, str):
                solution_url = val
            elif kw.arg == "source" and isinstance(val, str):
                source = val
            elif kw.arg == "name" and isinstance(val, str):
                name_arg = val
        break  # only first ProblemConfig matters

    if original_parameters is None:
        return None

    return {
        "template_key": template_key,
        "original_parameters": original_parameters,
        "problem_url": problem_url,
        "solution_url": solution_url,
        "source": source,
        "name": name_arg,
        "filepath": filepath,
    }


def discover_problems() -> list[dict]:
    """Walk subdirectories of PROBLEMS_DIR and collect metadata for every problem."""
    results = []
    for subdir in sorted(glob.glob(os.path.join(PROBLEMS_DIR, "*"))):
        if not os.path.isdir(subdir):
            continue
        dirname = os.path.basename(subdir)
        if dirname.startswith("_") or dirname == "backups":
            continue
        for pyfile in sorted(glob.glob(os.path.join(subdir, "*.py"))):
            meta = extract_metadata(pyfile)
            if meta is not None:
                # Build a human-readable name from the relative path
                rel = os.path.relpath(pyfile, PROBLEMS_DIR).replace("\\", "/")
                if meta["name"] is None:
                    meta["name"] = rel
                meta["rel_path"] = rel
                results.append(meta)
    return results


def instantiate(template: str, params: dict) -> str:
    """Format a template string with the given params dict.

    Handles the fact that mathconstruct templates use double-braces for
    literal braces (standard Python str.format behaviour).
    """
    return template.format(**params)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading TEMPLATES dict ...")
    templates = load_templates()
    print(f"  {len(templates)} templates loaded.\n")

    print("Discovering problem files ...")
    all_problems = discover_problems()
    print(f"  {len(all_problems)} problem files found (excluding backups).\n")

    # Only keep problems whose template_key exists in TEMPLATES
    valid = [p for p in all_problems if p["template_key"] in templates]
    print(f"  {len(valid)} problems have matching templates.\n")

    random.shuffle(valid)

    sampled: list[tuple[dict, str]] = []  # (metadata, formatted_text)

    for meta in valid:
        if len(sampled) >= NUM_PROBLEMS:
            break
        tpl = templates[meta["template_key"]]
        params = meta["original_parameters"]
        try:
            text = instantiate(tpl, params)
            if not text.strip():
                raise ValueError("Empty result")
            sampled.append((meta, text))
            print(f"  [{len(sampled):>2}/{NUM_PROBLEMS}] {meta['rel_path']}")
        except Exception as e:
            print(f"  SKIP  {meta['rel_path']}: {e}")

    if len(sampled) < NUM_PROBLEMS:
        print(f"\nWARNING: Only sampled {len(sampled)}/{NUM_PROBLEMS} problems.")

    # ------------------------------------------------------------------
    # Write output files
    # ------------------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    links_lines: list[str] = []
    links_lines.append(
        f"{'#':<4}  {'Problem Name':<55}  {'Source':<40}  "
        f"{'Problem URL':<90}  {'Solution URL'}"
    )
    links_lines.append("-" * 260)

    for idx, (meta, text) in enumerate(sampled, start=1):
        fname = f"problem_{idx:03d}.txt"
        fpath = os.path.join(OUTPUT_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  Wrote {fname}")

        links_lines.append(
            f"{idx:<4}  {meta['name'] or meta['rel_path']:<55}  "
            f"{(meta['source'] or ''):<40}  "
            f"{(meta['problem_url'] or '(n/a)'):<90}  "
            f"{meta['solution_url'] or '(n/a)'}"
        )

    links_path = os.path.join(OUTPUT_DIR, "problem_links.txt")
    with open(links_path, "w", encoding="utf-8") as f:
        f.write("\n".join(links_lines) + "\n")
    print(f"\n  Wrote problem_links.txt  ({len(sampled)} entries)")
    print("Done.")


if __name__ == "__main__":
    main()

