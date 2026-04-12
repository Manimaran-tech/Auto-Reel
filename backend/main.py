from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analytics import analyze_and_update_strategy, get_analytics_summary, get_last_user, ingest_metric, init_db, save_user
from .config import ROOT_DIR, ensure_directories, get_instagram_creds, runtime_credentials, settings
from .distributor import check_session, open_login_browser
from .pipeline import PipelineManager

app = FastAPI(title="AutoReel AI")
pipeline_manager = PipelineManager()


class GenerateRequest(BaseModel):
    url: str = Field(..., description="Amazon/Shopify product URL")
    manual_data: dict[str, Any] | None = Field(default=None, description="Manual fallback product JSON")


class IngestRequest(BaseModel):
    product_title: str = ""
    hook_type: str = "unknown"
    video_path: str = ""
    views: int = 0
    watch_time_pct: float = 0.0
    link_clicks: int = 0
    conversions: int = 0


class SettingsRequest(BaseModel):
    instagram_username: str = ""
    instagram_password: str = ""


@app.on_event("startup")
async def startup_event() -> None:
    ensure_directories()
    init_db()

    # Load last persistent user on startup
    db_user, db_pass = get_last_user()
    if db_user:
        runtime_credentials["instagram_username"] = db_user
        runtime_credentials["instagram_password"] = db_pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = ROOT_DIR / "frontend"
frontend_dist_dir = frontend_dir / "dist"
output_dir = settings.output_dir
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")
if (frontend_dist_dir / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist_dir / "assets")), name="assets")


def _frontend_entrypoint() -> Response:
    index_file = frontend_dist_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        "<h2>Frontend build missing</h2>"
        "<p>Run <code>cd frontend && npm install && npm run build</code> "
        "or run Vite dev server with <code>npm run dev</code>.</p>",
        status_code=503,
    )


@app.get("/")
async def index() -> Response:
    return _frontend_entrypoint()


@app.get("/analytics")
async def analytics_page() -> Response:
    return _frontend_entrypoint()


import threading

def _run_pipeline_thread(job_id: str) -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(pipeline_manager.run_job(job_id))
    finally:
        loop.close()

@app.post("/api/generate")
async def generate_video(payload: GenerateRequest) -> dict[str, Any]:
    job_id = await pipeline_manager.create_job(payload.url, payload.manual_data)
    threading.Thread(target=_run_pipeline_thread, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str) -> dict[str, Any]:
    status = await pipeline_manager.get_status(job_id)
    if status.get("error") == "Job not found":
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@app.get("/api/video/{job_id}")
async def get_video(job_id: str) -> FileResponse:
    status = await pipeline_manager.get_status(job_id)
    video_path = status.get("artifacts", {}).get("video")
    if not video_path:
        raise HTTPException(status_code=404, detail="Video not found or not ready.")
    path = Path(video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing.")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.post("/api/distribute/{job_id}")
async def distribute(job_id: str) -> dict[str, Any]:
    """Run distribution in a separate thread since Playwright needs its own event loop on Windows."""
    import sys

    def _run_distribute():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(pipeline_manager.distribute(job_id))
        finally:
            loop.close()

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await asyncio.get_event_loop().run_in_executor(pool, _run_distribute)
    return result


def _run_login_browser(username: str):
    """Run the manual login browser in its own event loop thread."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(open_login_browser(username))
    finally:
        loop.close()


@app.post("/api/ig-session/login")
async def ig_session_login() -> dict[str, Any]:
    """Open a real browser for user to log in manually. Session is persisted."""
    username, _ = get_instagram_creds()
    if not username:
        raise HTTPException(status_code=400, detail="Set your Instagram username in Settings first.")

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await asyncio.get_event_loop().run_in_executor(pool, _run_login_browser, username)
    return result


@app.get("/api/ig-session/status")
async def ig_session_status() -> dict[str, Any]:
    """Check if a valid Instagram session exists."""
    username, _ = get_instagram_creds()
    if not username:
        return {"valid": False, "message": "No username configured."}

    import concurrent.futures

    def _check():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(check_session(username))
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await asyncio.get_event_loop().run_in_executor(pool, _check)
    return result


@app.get("/api/analytics")
async def analytics_summary() -> dict[str, Any]:
    return get_analytics_summary()


@app.post("/api/analytics/ingest")
async def analytics_ingest(payload: IngestRequest) -> dict[str, Any]:
    metric_id = ingest_metric(payload.model_dump())
    return {"status": "ok", "metric_id": metric_id}


@app.post("/api/analytics/refresh-strategy")
async def analytics_refresh_strategy() -> dict[str, Any]:
    return analyze_and_update_strategy()


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    username, _ = get_instagram_creds()
    return {
        "instagram_username": username,
        "instagram_connected": bool(username),
        "ollama_model": settings.ollama_model,
        "tts_voice": settings.tts_voice,
    }


@app.post("/api/settings")
async def update_settings(payload: SettingsRequest) -> dict[str, Any]:
    if payload.instagram_username:
        runtime_credentials["instagram_username"] = payload.instagram_username
    if payload.instagram_password:
        runtime_credentials["instagram_password"] = payload.instagram_password

    if payload.instagram_username and payload.instagram_password:
        save_user(payload.instagram_username, payload.instagram_password)

    return {"status": "ok", "message": "Credentials stored securely."}
