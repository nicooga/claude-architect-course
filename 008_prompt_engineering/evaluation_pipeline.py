import ast
import asyncio
import inspect
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List
from anthropic import AsyncAnthropic
from anthropic.types import Message, TextBlock

from lib.ai_generation.ai_generation import MessageList

MAX_CONCURRENCY = 5


@dataclass
class TestCase:
    task: str
    format: str


@dataclass
class ModelGrade:
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    reasoning: str = ""
    score: float = 0.0


@dataclass
class EvaluationResult:
    task: str
    output: str
    model_grade: ModelGrade
    syntax_score: float
    score: float


def get_text(response: Message) -> str:
    """Extracts the text of the first content block, raising if it isn't text"""
    block = response.content[0]

    if not isinstance(block, TextBlock):
        raise TypeError(f"Expected a TextBlock, got {type(block).__name__}")

    return block.text


async def do_grade_by_model(
    task: str,
    solution: str,
    model: AsyncAnthropic
) -> ModelGrade:
    # Create evaluation prompt
    eval_prompt = inspect.cleandoc(f"""
    You are an expert code reviewer. Evaluate this AI-generated solution.

    Task: {task}
    Solution: {solution}

    Provide your evaluation as a structured JSON object with:
    - "strengths": An array of 1-3 key strengths
    - "weaknesses": An array of 1-3 key areas for improvement  
    - "reasoning": A concise explanation of your assessment
    - "score": A number between 1-10

    Respond with JSON. Keep your response consise and direct.
    Example response shape:
    {{
        "strengths": ["...", "....]
        "weaknesses":  ["...", "....],
        "reasoning": "..."
        "score": 3.4
    }}
    """)

    messages = MessageList()
    messages.add_user_message(eval_prompt)
    messages.add_assistant_message("```json")

    response = await model.messages.create(
        model="claude-sonnet-4-5-20250929",
        messages=messages,
        stop_sequences=["```"],
        max_tokens=5000
    )

    eval_text = get_text(response)

    return ModelGrade(**json.loads(eval_text))


async def grade_by_model(
    task: str,
    solution: str,
    model: AsyncAnthropic,
    retries = 3
) -> ModelGrade:
    try:
        return await do_grade_by_model(task, solution, model)
    except (json.decoder.JSONDecodeError, TypeError) as e:
        if (retries > 0):
            print("Retrying")
            return await grade_by_model(
                task,
                solution,
                model,
                retries-1
            )
        else:
            print("Retries exhausted. Giving up")
            return ModelGrade(score=0)


def grade_by_syntax(format: str, solution: str) -> float:
    """Validates that solution is syntactically valid for its format. Binary pass (1.0) / fail (0.0)."""
    try:
        if format == "json":
            json.loads(solution)
        elif format == "python":
            ast.parse(solution)
        elif format == "regex":
            re.compile(solution)
        else:
            return 0.0
    except (json.JSONDecodeError, SyntaxError, re.error):
        return 0.0

    return 1.0


async def run_prompt(task: str, client: AsyncAnthropic) -> str:
    """Merges the prompt and test case input, then returns the result"""

    prompt = inspect.cleandoc(
        f"""
        Please solve the following task:

        {task}
        """
    )

    messages = MessageList()
    messages.add_user_message(prompt)
    messages.add_assistant_message("```code")

    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1000,
        messages=messages,
        stop_sequences=["```"]
    )

    return get_text(response)

async def evaluate_test_case(
        task: str,
        format: str,
        client: AsyncAnthropic,
        semaphore: asyncio.Semaphore
) -> EvaluationResult:
    """Calls run_prompt, then grades the result by syntax and by model"""
    async with semaphore:
        output = await run_prompt(task, client)
        model_grade = await grade_by_model(task, output, client)

    syntax_score = grade_by_syntax(format, output)
    score = model_grade.score if syntax_score else 0.0

    return EvaluationResult(
        task=task,
        output=output,
        model_grade=model_grade,
        syntax_score=syntax_score,
        score=score
    )

async def main() -> None:
    dirname = os.path.dirname(__file__)
    dataset_path = Path(dirname) / "./dataset.data.json"
    output_path = Path(dirname) / "./evaluation_results.data.json"

    with open(dataset_path) as f:
        test_cases: List[TestCase] = [TestCase(**tc) for tc in json.load(f)]

    client = AsyncAnthropic()
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def run(i: int, test_case: TestCase) -> EvaluationResult:
        result = await evaluate_test_case(
            test_case.task, test_case.format, client, semaphore
        )
        print(f"Evaluated test case {i+1}")
        return result

    eval_results: List[EvaluationResult] = await asyncio.gather(
        *(run(i, test_case) for i, test_case in enumerate(test_cases))
    )

    avg_score = sum(result.score for result in eval_results) / len(eval_results)

    print(f"Avg. score: {avg_score}")

    output = {
        "avg_score": avg_score,
        "results": [asdict(result) for result in eval_results]
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=4)

if __name__ == "__main__":
    asyncio.run(main())