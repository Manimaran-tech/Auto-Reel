"""Pexels Stock Video Integration — fetch contextual lifestyle clips for Reels."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from .config import settings

PEXELS_API_URL = "https://api.pexels.com/videos/search"


def _extract_search_query(product_data: dict[str, Any]) -> str:
    """Convert product title into a short, effective Pexels search query."""
    title = product_data.get("title", "")
    # Remove brand names, dimensions, special chars
    cleaned = re.sub(r"[®™©|]", "", title)
    # Take the important nouns (skip generic words)
    skip_words = {
        "with", "and", "for", "the", "a", "an", "in", "of", "to", "by",
        "heavy", "duty", "adjustable", "premium", "quality", "best",
        "new", "latest", "pack", "set", "pcs", "piece", "year", "warranty",
        "metal", "base", "diy", "grey", "black", "white", "blue", "red",
    }
    words = [w for w in cleaned.lower().split() if w not in skip_words and len(w) > 2]
    # Take the first 2-3 meaningful words for a targeted search
    query = " ".join(words[:3])
    return query or "product lifestyle"


async def search_pexels_videos(
    product_data: dict[str, Any],
    orientation: str = "portrait",
    per_page: int = 3,
    min_duration: int = 5,
    max_duration: int = 15,
) -> list[dict[str, Any]]:
    """Search Pexels for vertical stock videos matching the product."""
    api_key = settings.pexels_api_key
    if not api_key:
        print("PEXELS_API_KEY not set. Skipping stock video search.")
        return []

    query = _extract_search_query(product_data)
    print(f"Pexels search query: '{query}'")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            PEXELS_API_URL,
            params={
                "query": query,
                "orientation": orientation,
                "per_page": per_page,
                "size": "medium",
            },
            headers={"Authorization": api_key},
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()

    results = []
    for video in data.get("videos", []):
        duration = video.get("duration", 0)
        if duration < min_duration or duration > max_duration:
            continue

        # Pick the best quality file (HD, not 4K to keep fast)
        video_files = video.get("video_files", [])
        best_file = None
        for vf in video_files:
            if vf.get("quality") == "hd" and vf.get("width", 0) <= 1080:
                best_file = vf
                break
        if not best_file and video_files:
            best_file = video_files[0]

        if best_file:
            results.append({
                "id": video["id"],
                "url": best_file["link"],
                "width": best_file.get("width", 720),
                "height": best_file.get("height", 1280),
                "duration": duration,
            })

    # If no results with the query, try a broader "person using product" search
    if not results:
        print(f"No results for '{query}', trying broader search...")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                PEXELS_API_URL,
                params={
                    "query": f"person using {query}",
                    "orientation": orientation,
                    "per_page": 5,
                    "size": "medium",
                },
                headers={"Authorization": api_key},
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()

        for video in data.get("videos", []):
            duration = video.get("duration", 0)
            if duration < 3 or duration > 20:
                continue
            video_files = video.get("video_files", [])
            best_file = None
            for vf in video_files:
                if vf.get("quality") == "hd" and vf.get("width", 0) <= 1080:
                    best_file = vf
                    break
            if not best_file and video_files:
                best_file = video_files[0]
            if best_file:
                results.append({
                    "id": video["id"],
                    "url": best_file["link"],
                    "width": best_file.get("width", 720),
                    "height": best_file.get("height", 1280),
                    "duration": duration,
                })
                if len(results) >= 2:
                    break

    return results[:3]


async def download_stock_video(url: str, output_path: Path) -> str | None:
    """Download a stock video clip to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            output_path.write_bytes(response.content)
            return str(output_path)
    except Exception as exc:
        print(f"Failed to download stock video: {exc}")
        return None


async def fetch_stock_clips(
    product_data: dict[str, Any],
    output_dir: Path,
) -> list[str]:
    """Search and download stock video clips for a product."""
    videos = await search_pexels_videos(product_data)
    if not videos:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for idx, video in enumerate(videos, start=1):
        path = output_dir / f"stock_{idx}.mp4"
        result = await download_stock_video(video["url"], path)
        if result:
            downloaded.append(result)
            print(f"Downloaded stock clip {idx}: {video['duration']}s")

    return downloaded
