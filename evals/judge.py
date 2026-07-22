"""Layer B — LLM-as-judge (docs/feature.prd §10). Directional, not
authoritative: Layer A assertions gate pass/fail; this only informs.
"""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from agents.model_config import resilient_client

_PROMPT_TEMPLATE = """
You are grading a supply-chain supervisor agent's rationale for an action plan.

Situation: {situation}
World snapshot (JSON): {world}
Specialist recommendations (JSON): {recommendations}
Final action plan (JSON): {action_plan}
Supervisor rationale: {rationale}

Score the rationale 1-5 (integers) on each of:
- faithfulness: does it match the data and the specialists' recommendations?
- constraint_adherence: does it respect budget_per_cycle and never use an
  unavailable supplier?
- relevance: does it actually address the situation ("{situation}")?

Respond with ONLY a JSON object matching this shape:
{{"faithfulness": <int 1-5>, "constraint_adherence": <int 1-5>, "relevance": <int 1-5>, "comment": "<one sentence>"}}
""".strip()


class JudgeScores(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    constraint_adherence: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    comment: str


def judge_rationale(
    situation: str,
    world: dict,
    recommendations: dict,
    action_plan: dict,
    rationale: str,
) -> JudgeScores:
    """Scores a supervisor rationale with an LLM judge. Directional, not authoritative."""
    model = os.environ.get("JUDGE_MODEL", "gemini-flash-latest")
    client = resilient_client(os.environ["GOOGLE_API_KEY"])
    prompt = _PROMPT_TEMPLATE.format(
        situation=situation,
        world=json.dumps(world),
        recommendations=json.dumps(recommendations),
        action_plan=json.dumps(action_plan),
        rationale=rationale,
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    data = json.loads(response.text)
    return JudgeScores(**data)
