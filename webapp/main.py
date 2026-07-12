"""FastAPI webapp — the triggering point for the supply-chain agent.

Run with: uv run uvicorn webapp.main:app --reload
Requires GOOGLE_API_KEY in .env — actual Gemini calls happen when you hit
"Run" on a scenario.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from webapp import runner_service

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Supply Chain Agent")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.exception_handler(FileNotFoundError)
async def scenario_not_found(request: Request, exc: FileNotFoundError):
    return templates.TemplateResponse(
        request, "not_found.html", {"detail": str(exc)}, status_code=404
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    scenarios = runner_service.list_scenario_summaries()
    action_log = runner_service.load_action_log()[:5]
    eval_log = runner_service.load_eval_log()[:5]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "scenarios": scenarios,
            "recent_action_log": action_log,
            "recent_eval_log": eval_log,
        },
    )


@app.get("/scenarios/{scenario_id}", response_class=HTMLResponse)
async def scenario_detail(request: Request, scenario_id: str):
    detail = runner_service.get_scenario_detail(scenario_id)
    return templates.TemplateResponse(request, "scenario.html", detail)


@app.post("/scenarios/{scenario_id}/run", response_class=HTMLResponse)
async def scenario_run(request: Request, scenario_id: str):
    try:
        result = await runner_service.run_scenario(scenario_id)
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "run_error.html",
            {"scenario_id": scenario_id, "error": str(exc)},
            status_code=502,
        )
    return templates.TemplateResponse(request, "result.html", result)


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "action_log": runner_service.load_action_log(),
            "eval_log": runner_service.load_eval_log(),
        },
    )
