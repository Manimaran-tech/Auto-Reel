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
    title = product_data.get("title", "Unknown Product")
    features = ", ".join(product_data.get("features", [])[:5])
    raw_price = str(product_data.get("price", "N/A"))
    
    # Simple conversion: detect INR and convert to USD
    price = raw_price
    if any(sym in raw_price for sym in ["₹", "Rs", "INR"]):
        try:
            # Extract numeric value
            nums = re.findall(r"[\d,.]+", raw_price)
            if nums:
                val = float(nums[0].replace(",", ""))
                usd_val = round(val / 83.0, 2)
                price = f"${usd_val}"
        except Exception:
            pass
            
    extra_rule = strategy_rule.strip() or "No additional strategy rule."
    return f"""You are an elite comedy writer for Family Guy and a viral marketing genius.

PRODUCT INFORMATION:
- Name: {title}
- Price: {price}
- Key Features: {features}

CRITICAL STRATEGY TO APPLY:
{extra_rule}

YOUR TASK:
Write a 30-second viral Instagram Reel script using a dialogue format between Peter Griffin and Stewie Griffin.

SCRIPT RULES:
1. Peter MUST start by loudly complaining about a SPECIFIC relatable problem that THIS EXACT PRODUCT solves. DO NOT use generic complaints. The complaint MUST be directly related to "{title}".
2. Stewie jumps in, roasts Peter hilariously, and pitches the product in a FUNNY and NATURAL way — like a cocky salesman, NOT a boring spec sheet reader.
3. Peter reacts with skepticism or shock ("Wait, seriously?", "No way that's real").
4. Stewie aggressively closes with price (ensure to explicitly say 'dollars' if giving a number) and WHY the product is amazing (NOT a feature list — sell the FEELING and BENEFIT). Must end with "Get the product link in the bio or below this reel!"
5. CRITICAL: Stewie should NEVER just list specifications or read a product description. He should SELL with attitude, humor, and personality.
6. Keep the entire dialogue between 80-100 words total.
7. The dialogue must be written as a JSON list of objects with "speaker" (either "peter" or "stewie") and "text".
8. NEVER put hashtags (#) in the dialogue text. Hashtags are ONLY for the caption.

BAD EXAMPLE (DO NOT DO THIS):
"It has lumbar support, adjustable armrests, breathable mesh fabric, and 360-degree swivel."
GOOD EXAMPLE (DO THIS):
"This bad boy hugs your spine like it actually cares about you. Your back pain? Gone. Your excuses? Also gone."

CAPTION RULES:
1. Talk directly about the product (Max 50 words).
2. End with exactly 5 product-relevant hashtags.

OUTPUT FORMAT (respond ONLY with valid JSON):
{{
  "dialogue": [
    {{"speaker": "peter", "text": "example complaint about THIS specific product category"}},
    {{"speaker": "stewie", "text": "example roast + pitch for {title}"}}
  ],
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


def _template_fallback(product_data: dict[str, Any], price: Any) -> dict[str, Any]:
    title = product_data.get("title", "this product")
    feat = product_data.get("features", ["high quality", "great value", "must-have"])[:2]
    
    dialogue = [
        {"speaker": "peter", "text": f"Aw geez Lois, I'm so done with this! I need a proper {title.split()[0].lower()} situation before I lose my mind!"},
        {"speaker": "stewie", "text": f"Stop whining, fat man. The {title} exists and it's about to change your miserable life."},
        {"speaker": "peter", "text": "Wait, seriously? Is it actually good or are you messing with me again?"},
        {"speaker": "stewie", "text": f"It's only {price} and honestly, it feels like it costs way more. Your life upgrades TODAY. Get the product link in the bio or below this reel!"}
    ]
    caption = (
        f"Quick upgrade alert! {title} at {price}. "
        "#musthave #familyguy #shoppingfinds #dealoftheday #reelshopping"
    )
    return {"dialogue": dialogue, "caption": caption}


def generate_script(product_data: dict[str, Any], strategy_rule: str = "") -> dict[str, Any]:
    prompt = build_prompt(product_data, strategy_rule)
    
    # Extract the converted price for use in fallback if needed
    price = product_data.get("price", "N/A")
    raw_price = str(price)
    if any(sym in raw_price for sym in ["₹", "Rs", "INR"]):
        try:
            nums = re.findall(r"[\d,.]+", raw_price)
            if nums:
                price = f"${round(float(nums[0].replace(',', '')) / 83.0, 2)}"
        except: pass

    errors: list[str] = []
    for generator in (_generate_with_ollama, _generate_with_groq):
        try:
            result = generator(prompt)
            dialogue = result.get("dialogue")
            caption = (result.get("caption") or "").strip()
            if dialogue and isinstance(dialogue, list) and caption:
                first_text = dialogue[0].get("text", "")
                return {"dialogue": dialogue, "caption": caption, "hook_type": detect_hook_type(first_text)}
        except Exception as exc:
            errors.append(str(exc))

    fallback = _template_fallback(product_data, price)
    first_text = fallback["dialogue"][0]["text"]
    fallback["hook_type"] = detect_hook_type(first_text)
    fallback["generator_errors"] = errors
    return fallback
