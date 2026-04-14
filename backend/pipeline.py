from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import analytics
from .config import get_instagram_creds, settings
from .copywriter import generate_script
from .distributor import push_to_instagram_draft
from .scraper import scrape_product
from .video_renderer import render_reel
from .voice_engine import generate_dialogue_voiceover



class PipelineManager:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    async def create_job(self, url: str, manual_data: dict[str, Any] | None = None) -> str:
        # Clean up all previous job folders before starting a new one
        self._cleanup_old_jobs()
        job_id = uuid4().hex[:10]
        self.jobs[job_id] = {
                "job_id": job_id,
                "url": url,
                "manual_data": manual_data or {},
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "error": None,
                "artifacts": {},
            }
        return job_id

    def _cleanup_old_jobs(self) -> None:
        """Delete all previous job directories from output/jobs/."""
        import shutil
        jobs_dir = settings.jobs_dir
        if jobs_dir.exists():
            for child in jobs_dir.iterdir():
                if child.is_dir():
                    try:
                        shutil.rmtree(child)
                    except Exception as e:
                        print(f"⚠️ Failed to clean up {child}: {e}")

    async def update_status(self, job_id: str, **updates: Any) -> None:
        if job_id in self.jobs:
            self.jobs[job_id].update(updates)

    def _job_dir(self, job_id: str) -> Path:
        folder = settings.jobs_dir / job_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    async def run_job(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return

        url = job["url"]
        manual_data = job.get("manual_data")
        benchmarks: list[tuple[str, float]] = []
        pipeline_start = time.perf_counter()
        try:
            job_dir = self._job_dir(job_id)
            images_dir = job_dir / "images"

            # ── Step 1: Scraper ──
            t0 = time.perf_counter()
            await self.update_status(job_id, status="running", stage="scraper", progress=10)
            product = await scrape_product(url=url, image_output_dir=images_dir, manual_data=manual_data)
            product["url"] = url
            benchmarks.append(("🔍 Scraper", time.perf_counter() - t0))
            
            # ── Step 2: AI Images (SKIPPED — using scraped product image) ──
            t0 = time.perf_counter()
            # We use the original scraped product image from the e-commerce site
            # instead of LLM-generated images for better product accuracy
            benchmarks.append(("🎨 AI Images", time.perf_counter() - t0))

            (job_dir / "product_data.json").write_text(json.dumps(product, indent=2), encoding="utf-8")

            # ── Step 3: Copywriter ──
            t0 = time.perf_counter()
            await self.update_status(
                job_id,
                stage="copywriter",
                progress=30,
                artifacts={"product_data": str(job_dir / "product_data.json")},
            )
            strategy_rule = analytics.get_current_strategy_rule()
            copy = generate_script(product, strategy_rule=strategy_rule)
            dialogue = copy["dialogue"]
            caption = copy["caption"]
            hook_type = copy.get("hook_type", "unknown")
            (job_dir / "script.json").write_text(json.dumps(dialogue), encoding="utf-8")
            (job_dir / "caption.txt").write_text(caption, encoding="utf-8")
            benchmarks.append(("✍️ Copywriter", time.perf_counter() - t0))
            
            # ── Step 4: Voice Engine ──
            t0 = time.perf_counter()
            await self.update_status(
                job_id,
                stage="voice_engine",
                progress=50,
                artifacts={
                    **self.jobs[job_id]["artifacts"],
                    "dialogue": str(job_dir / "script.json"),
                    "caption": str(job_dir / "caption.txt"),
                },
            )
            audio_path = job_dir / "voiceover.mp3"
            subs_path = job_dir / "subtitles.json"
            await generate_dialogue_voiceover(dialogue, audio_path, subs_path)
            benchmarks.append(("🎙️ Voice Engine", time.perf_counter() - t0))

            # ── Step 5: Video Renderer ──
            t0 = time.perf_counter()
            await self.update_status(
                job_id,
                stage="video_renderer",
                progress=70,
                artifacts={
                    **self.jobs[job_id]["artifacts"],
                    "audio": str(audio_path),
                    "subtitles": str(subs_path),
                },
            )
            product_images = product.get("images", [])
            p_img = product_images[0] if product_images else None

            output_video = job_dir / "final_reel.mp4"
            render_reel(
                voiceover_path=audio_path,
                subtitles_path=subs_path,
                output_path=output_video,
                product_image_path=p_img,
                music_dir=settings.music_dir,
                fonts_dir=settings.fonts_dir,
            )
            benchmarks.append(("🎬 Video Renderer", time.perf_counter() - t0))

            analytics.ingest_metric(
                {
                    "product_title": product["title"],
                    "hook_type": hook_type,
                    "video_path": str(output_video),
                    "views": 0,
                    "watch_time_pct": 0.0,
                    "link_clicks": 0,
                    "conversions": 0,
                }
            )
            total_time = time.perf_counter() - pipeline_start
            benchmarks.append(("⏱️ TOTAL", total_time))

            # ── Print Benchmark Summary ──
            print("\n" + "═" * 50)
            print("  📊 PIPELINE BENCHMARK RESULTS")
            print("═" * 50)
            for label, elapsed in benchmarks:
                mins, secs = divmod(elapsed, 60)
                if mins >= 1:
                    print(f"  {label:<22s}  {int(mins)}m {secs:05.2f}s")
                else:
                    print(f"  {label:<22s}  {secs:05.2f}s")
            print("═" * 50 + "\n")

            # Save benchmark to job dir
            benchmark_data = {label: round(elapsed, 2) for label, elapsed in benchmarks}
            (job_dir / "benchmark.json").write_text(json.dumps(benchmark_data, indent=2), encoding="utf-8")

            await self.update_status(
                job_id,
                stage="completed",
                status="completed",
                progress=100,
                artifacts={
                    **self.jobs[job_id]["artifacts"],
                    "video": str(output_video),
                    "caption_text": caption,
                    "benchmark": str(job_dir / "benchmark.json"),
                },
            )
        except Exception as exc:
            import traceback
            err_str = traceback.format_exc()
            print("PIPELINE ERROR:", err_str)
            await self.update_status(
                job_id,
                stage="failed",
                status="failed",
                error=err_str,
            )

    async def get_status(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "Job not found"}
        return job

    async def distribute(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "message": "Job not found."}
        video_path = job.get("artifacts", {}).get("video")
        caption = job.get("artifacts", {}).get("caption_text", "")
        product_url = job.get("url", "")

        if not video_path:
            return {"success": False, "message": "Video not ready yet."}

        username, password = get_instagram_creds()
        return await push_to_instagram_draft(
            video_path=video_path,
            caption=caption,
            username=username,
            password=password,
            product_url=product_url,
            headless=False,
        )

