import os
from dotenv import load_dotenv
load_dotenv()

from pydantic_ai import Agent, Tool
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from problem_structure import Deduction, Conflict, Decision, Solution
from typing import List
from pathlib import Path
import io
import contextlib

prop_system_prompt = Path("system_prompt.md").read_text()
prop_user_prompt = Path("prop_user_prompt.md").read_text()

conflict_detection_system_prompt = Path("system_prompt.md").read_text()
conflict_detection_user_prompt = Path("conflict_detection_user_prompt.md").read_text()

decision_system_prompt = Path("system_prompt.md").read_text()
decision_user_prompt = Path("decision_user_prompt.md").read_text()

solution_checker_system_prompt = Path("system_prompt.md").read_text()
solution_checker_user_prompt = Path("solution_checker_user_prompt.md").read_text()

lemma_deducer_system_prompt = Path("system_prompt.md").read_text()
lemma_deducer_user_prompt = Path("lemma_deducer_user_prompt.md").read_text()

llm_name = "openai/gpt-4.1"
# provider = OpenAIProvider(
#     api_key=os.getenv('OPENAI_API_KEY'),
#     base_url="https://api.openai.com/v1"  # Override OPENAI_BASE_URL env var
# )
# model = OpenAIChatModel(llm_name, provider=provider)
model = OpenAIChatModel(llm_name)

def execute_python(code: str) -> str:
    """
    args:
        code: Python code to execute. This code must be short and concise.
    returns:
        str: Printed output of the code. This output is what the code generates through print() statements only - any output required through the code must hence be generated through print() statements.
    """
    print(f"\n  [TOOL] execute_python called with code:")
    print(f"  ---")
    for line in code.split('\n'):
        print(f"  | {line}")
    print(f"  ---")
    
    stdout_capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_capture):
            namespace = {"__builtins__": __builtins__}
            exec(code, namespace)
        output = stdout_capture.getvalue()
        result = output if output else None
    except Exception as e:
        result = f"Error: {type(e).__name__}: {e}"
    print(f"  [TOOL] Result: {result}")
    if result is None:
        return f"No print() output in provided code. Only print() output is captured."
    return result

def create_agents(use_code_prop: bool = False, use_code_decision: bool = False, use_code_solution: bool = False, use_code_conflict: bool = False):
    # Propagation Agent
    prop_agent = Agent(
        model = model,
        system_prompt = prop_system_prompt,
        output_type = List[Deduction],
        output_retries = 3,
        tools = [Tool(execute_python, takes_ctx = False)] if use_code_prop else []
        )

    # Conflict Detection Agent
    conflict_detection_agent = Agent(
        model,
        system_prompt = conflict_detection_system_prompt,
        output_type = Conflict,
        output_retries = 3,
        tools = [Tool(execute_python, takes_ctx = False)] if use_code_conflict else []
        )

    # Decision Agent
    decision_agent = Agent(
        model,
        system_prompt = decision_system_prompt,
        output_type = Decision,
        output_retries = 3,
        tools = [Tool(execute_python, takes_ctx = False)] if use_code_decision else []
    )

    # Solution checker Agent
    solution_checker_agent = Agent(
        model,
        system_prompt = solution_checker_system_prompt,
        output_type = Solution,
        output_retries = 3,
        tools = [Tool(execute_python, takes_ctx = False)] if use_code_solution else []
    )

    # Lemma deducer Agent
    lemma_deducer_agent = Agent(
        model,
        system_prompt = lemma_deducer_system_prompt,
        output_type = str,
        output_retries = 3
    )
    
    return prop_agent, conflict_detection_agent, decision_agent, solution_checker_agent, lemma_deducer_agent