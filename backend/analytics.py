from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .config import settings


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or settings.db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reel_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_title TEXT,
                hook_type TEXT,
                video_path TEXT,
                views INTEGER DEFAULT 0,
                watch_time_pct REAL DEFAULT 0.0,
                link_clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ai_strategy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                current_rule TEXT,
                rationale TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_b64 TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        current_rule = get_current_strategy_rule(conn=conn)
        if not current_rule:
            conn.execute(
                "INSERT INTO ai_strategy (current_rule, rationale) VALUES (?, ?)",
                (
                    "Hook with a bold question in the first sentence and keep pacing fast.",
                    "Default bootstrap strategy before enough analytics data is collected.",
                ),
            )
            conn.commit()


def ingest_metric(metric: dict[str, Any], db_path: Path | None = None) -> int:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO reel_metrics
            (product_title, hook_type, video_path, views, watch_time_pct, link_clicks, conversions)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric.get("product_title", ""),
                metric.get("hook_type", "unknown"),
                metric.get("video_path", ""),
                int(metric.get("views", 0)),
                float(metric.get("watch_time_pct", 0.0)),
                int(metric.get("link_clicks", 0)),
                int(metric.get("conversions", 0)),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_weekly_metrics(days: int = 7, db_path: Path | None = None) -> list[dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM reel_metrics
            WHERE datetime(created_at) >= datetime(?)
            ORDER BY datetime(created_at) DESC
            """,
            (since.strftime("%Y-%m-%d %H:%M:%S"),),
        ).fetchall()
    return [dict(row) for row in rows]


def get_current_strategy_rule(conn: sqlite3.Connection | None = None, db_path: Path | None = None) -> str:
    owns_conn = conn is None
    if conn is None:
        conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT current_rule FROM ai_strategy ORDER BY datetime(updated_at) DESC, id DESC LIMIT 1"
        ).fetchone()
        return row["current_rule"] if row else ""
    finally:
        if owns_conn:
            conn.close()


def get_current_strategy(db_path: Path | None = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT current_rule, rationale, updated_at
            FROM ai_strategy
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else {"current_rule": "", "rationale": "", "updated_at": None}


def _extract_json(raw_text: str) -> dict[str, str]:
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return {
        "rationale": "Fallback strategy chosen because model output could not be parsed.",
        "new_copywriting_rule": "Start with a bold question and add urgency in the CTA.",
    }


def _build_analysis_prompt(metrics_data: list[dict[str, Any]]) -> str:
    return f"""You are a master digital marketer and growth expert.
Analyze this reel performance data:

{json.dumps(metrics_data, indent=2)}

DIAGNOSIS RULES:
- High Views but Low Watch Time = weaker pacing or boring hook.
- High Watch Time but Low Clicks = weak CTA.
- Low Views = first 2 seconds failed.

Return ONLY JSON:
{{
  "rationale": "why the current strategy is underperforming or succeeding",
  "new_copywriting_rule": "single instruction for the next batch"
}}"""


def _analysis_fallback(metrics_data: list[dict[str, Any]]) -> dict[str, str]:
    if not metrics_data:
        return {
            "rationale": "Not enough recent data. Keep broad-performing strategy.",
            "new_copywriting_rule": "Open with a surprising question, mention price in first half, end with urgent CTA.",
        }

    avg_watch = sum(float(m.get("watch_time_pct", 0.0)) for m in metrics_data) / len(metrics_data)
    total_views = sum(int(m.get("views", 0)) for m in metrics_data)
    total_clicks = sum(int(m.get("link_clicks", 0)) for m in metrics_data)
    ctr = (total_clicks / total_views) if total_views else 0.0

    if avg_watch < 35:
        return {
            "rationale": f"Average watch time is low ({avg_watch:.1f}%). Hook strength needs improvement.",
            "new_copywriting_rule": "Ragebait Rule: Start by calling out a common buying mistake before revealing the product.",
        }
    if ctr < 0.02:
        return {
            "rationale": f"CTR is low ({ctr:.2%}) despite views. CTA needs urgency.",
            "new_copywriting_rule": "Urgency Rule: Mention limited stock and ask viewers to act now.",
        }
    return {
        "rationale": "Recent performance is stable. Keep strategy but increase novelty in opening line.",
        "new_copywriting_rule": "Story Rule: Open with a one-line relatable pain point, then pivot to product solution.",
    }


def _analyze_with_ollama(metrics_data: list[dict[str, Any]]) -> dict[str, str]:
    response = requests.post(
        f"{settings.ollama_base_url}/api/generate",
        json={
            "model": settings.ollama_model,
            "prompt": _build_analysis_prompt(metrics_data),
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 280},
        },
        timeout=90,
    )
    response.raise_for_status()
    parsed = _extract_json(response.json().get("response", ""))
    if "new_copywriting_rule" not in parsed:
        raise RuntimeError("Invalid analytics JSON from Ollama.")
    return parsed


def analyze_and_update_strategy(db_path: Path | None = None) -> dict[str, Any]:
    metrics = get_weekly_metrics(days=7, db_path=db_path)
    try:
        analysis = _analyze_with_ollama(metrics)
    except Exception:
        analysis = _analysis_fallback(metrics)

    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ai_strategy (current_rule, rationale) VALUES (?, ?)",
            (analysis["new_copywriting_rule"], analysis["rationale"]),
        )
        conn.commit()

    return {
        "current_rule": analysis["new_copywriting_rule"],
        "rationale": analysis["rationale"],
        "sample_size": len(metrics),
    }


def get_analytics_summary(db_path: Path | None = None) -> dict[str, Any]:
    metrics = get_weekly_metrics(days=7, db_path=db_path)
    strategy = get_current_strategy(db_path=db_path)

    daily: dict[str, dict[str, int]] = {}
    for row in metrics:
        day = str(row.get("created_at", ""))[:10]
        if day not in daily:
            daily[day] = {"views": 0, "clicks": 0, "conversions": 0}
        daily[day]["views"] += int(row.get("views", 0))
        daily[day]["clicks"] += int(row.get("link_clicks", 0))
        daily[day]["conversions"] += int(row.get("conversions", 0))

    timeseries = [
        {"date": key, **value}
        for key, value in sorted(daily.items(), key=lambda item: item[0])
    ]

    total_views = sum(int(row.get("views", 0)) for row in metrics)
    total_clicks = sum(int(row.get("link_clicks", 0)) for row in metrics)
    avg_watch_time = (
        sum(float(row.get("watch_time_pct", 0.0)) for row in metrics) / len(metrics)
        if metrics
        else 0.0
    )

    return {
        "totals": {
            "videos": len(metrics),
            "views": total_views,
            "clicks": total_clicks,
            "avg_watch_time_pct": round(avg_watch_time, 2),
            "ctr": round((total_clicks / total_views) * 100, 2) if total_views else 0.0,
        },
        "timeseries": timeseries,
        "strategy": strategy,
    }


def save_user(username: str, password: str, db_path: Path | None = None) -> None:
    """Save user credentials, encoding password in base64 as a basic hackathon security layer."""
    pass_b64 = base64.b64encode(password.encode("utf-8")).decode("utf-8")
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (username, password_b64) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET password_b64=excluded.password_b64
            """,
            (username, pass_b64),
        )
        conn.commit()


def get_last_user(db_path: Path | None = None) -> tuple[str, str]:
    """Return the (username, password) of the last logged-in user, or empty tuple."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT username, password_b64 FROM users ORDER BY created_at DESC LIMIT 1").fetchone()
    if not row:
        return "", ""
    return row["username"], base64.b64decode(row["password_b64"].encode("utf-8")).decode("utf-8")

