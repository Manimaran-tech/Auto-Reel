from __future__ import annotations

import json
import re
from typing import Any

import requests

from .config import settings


def extract_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return {"script": text, "caption": "Check this out! #viral #trending #musthave #product #deals"}


def detect_hook_type(script: str) -> str:
    lead = script.lower().split(".", 1)[0]
    if "?" in lead:
        return "question"
    if any(word in lead for word in ["only", "limited", "today", "before it sells out"]):
        return "urgency"
    if any(word in lead for word in ["stop", "wrong", "mistake", "don't buy"]):
        return "ragebait"
    return "bold-claim"


def build_prompt(product_data: dict[str, Any], strategy_rule: str) -> str:
    features = ", ".join(product_data.get("features", [])[:5])
    extra_rule = strategy_rule.strip() or "No additional strategy rule."
    return f"""You are an elite direct-response copywriter specializing in viral TikTok and Instagram Reels.

PRODUCT INFORMATION:
- Name: {product_data.get("title", "Unknown Product")}
- Price: {product_data.get("price", "N/A")}
- Key Features: {features}

CRITICAL STRATEGY TO APPLY FOR THIS VIDEO:
{extra_rule}

YOUR TASK:
Write a 30-second Instagram Reel voiceover script and an Instagram caption.

SCRIPT RULES:
1. First sentence MUST be a scroll-stopping hook (question, shock, or bold claim).
2. Keep it between 80-100 words (this fills exactly 30 seconds when spoken).
3. Mention the product name and price naturally.
4. Highlight 3-4 key features with energy.
5. End with a clear call-to-action.
6. Use short, punchy sentences.
7. Sound human, energetic, and persuasive.

CAPTION RULES:
1. ONLY talk about the product — its features, benefits, and price.
2. Max 100 words.
3. Include 2 relevant emojis.
4. End with exactly 5 product-relevant hashtags.
5. Do NOT include generic filler or motivational text — keep it 100% about the product.

OUTPUT FORMAT (respond ONLY with JSON):
{{
  "script": "voiceover text",
  "caption": "instagram caption with hashtags"
}}"""


def _generate_with_ollama(prompt: str) -> dict[str, Any]:
    response = requests.post(
        f"{settings.ollama_base_url}/api/generate",
        json={
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.8, "num_predict": 300},
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    return extract_json(payload.get("response", ""))


def _generate_with_groq(prompt: str) -> dict[str, Any]:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("groq package not installed.") from exc

    client = Groq(api_key=settings.groq_api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=300,
    )
    raw_text = completion.choices[0].message.content or ""
    return extract_json(raw_text)


def _template_fallback(product_data: dict[str, Any]) -> dict[str, str]:
    title = product_data.get("title", "this product")
    price = product_data.get("price", "today's deal price")
    feat = product_data.get("features", ["high quality", "great value", "must-have"])[:3]
    script = (
        f"Still using outdated gear? Meet {title}. "
        f"It gives you {feat[0]}, {feat[1]}, and {feat[2]} for just {price}. "
        "If you want smarter results without overpaying, grab it now. Link in bio."
    )
    caption = (
        f"Quick upgrade alert for your daily routine: {title} at {price}. "
        "Built for real results and ready to ship. 🚀🔥 "
        "#musthave #smartbuy #shoppingfinds #dealoftheday #reelshopping"
    )
    return {"script": script, "caption": caption}


def generate_script(product_data: dict[str, Any], strategy_rule: str = "") -> dict[str, Any]:
    prompt = build_prompt(product_data, strategy_rule)

    errors: list[str] = []
    for generator in (_generate_with_ollama, _generate_with_groq):
        try:
            result = generator(prompt)
            script = (result.get("script") or "").strip()
            caption = (result.get("caption") or "").strip()
            if script and caption:
                return {"script": script, "caption": caption, "hook_type": detect_hook_type(script)}
        except Exception as exc:
            errors.append(str(exc))

    fallback = _template_fallback(product_data)
    fallback["hook_type"] = detect_hook_type(fallback["script"])
    fallback["generator_errors"] = errors
    return fallback
