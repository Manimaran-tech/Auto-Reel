---
name: autoreel-copywriter
description: Skill for building the AI copywriter module that generates viral Instagram Reel scripts and captions from product data. Use this when implementing the LLM integration with Ollama (local) or Groq (free API) for marketing script generation.
---

# AutoReel AI Copywriter Skill

## Overview
Takes structured product data (title, price, features) and uses a local LLM (Ollama) to generate a viral 15-second Instagram Reel script plus an Instagram post caption with hashtags.

## LLM Priority
1. **Primary:** Ollama (local, `http://localhost:11434`) — Model: `llama3.2:3b`
2. **Fallback:** Groq API (free tier) — Model: `llama-3.3-70b-versatile`

## Ollama Integration
```python
import requests
import json

def generate_script_ollama(product_data: dict, model: str = "llama3.2:3b") -> dict:
    """Generate a Reel script using local Ollama."""
    prompt = build_prompt(product_data)

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.8,
                "num_predict": 300,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    raw_text = response.json()["response"]

    # Parse the JSON from the LLM response
    return extract_json(raw_text)
```

## The Prompt (Critical for Quality)
```python
def build_prompt(product_data: dict) -> str:
    return f"""You are an elite direct-response copywriter specializing in viral TikTok and Instagram Reels.

PRODUCT INFORMATION:
- Name: {product_data['title']}
- Price: {product_data['price']}
- Key Features: {', '.join(product_data['features'][:5])}

YOUR TASK:
Write a 15-second Instagram Reel voiceover script and an Instagram caption.

SCRIPT RULES:
1. First sentence MUST be a scroll-stopping hook (question, shock, or bold claim).
2. Keep it between 40-60 words MAXIMUM (this is 15 seconds of speech).
3. Mention the price naturally.
4. End with a clear call-to-action ("Link in bio", "Comment WANT", etc.).
5. Use SHORT, punchy sentences. No long paragraphs.
6. Sound like a real person, not a robot. Be energetic and genuine.

CAPTION RULES:
1. Max 150 words.
2. Include 2 relevant emojis.
3. End with exactly 5 hashtags.

OUTPUT FORMAT (respond ONLY with this JSON, nothing else):
{{
  "script": "Your voiceover script here...",
  "caption": "Your Instagram caption here... #hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5"
}}"""
```

## JSON Extraction (Robust Parsing)
LLMs sometimes wrap JSON in markdown code blocks or add extra text. Use this to extract cleanly:

```python
import re
import json

def extract_json(raw_text: str) -> dict:
    """Extract JSON from potentially messy LLM output."""
    # Try direct parse first
    try:
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Try finding first { to last }
    start = raw_text.find("{")
    end = raw_text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(raw_text[start:end])

    # Ultimate fallback: return raw text as script
    return {
        "script": raw_text.strip(),
        "caption": f"Check this out! #viral #trending #musthave #product #deals"
    }
```

## Groq Fallback
```python
from groq import Groq
import os

def generate_script_groq(product_data: dict) -> dict:
    """Fallback: Use Groq's free API if Ollama is not running."""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    prompt = build_prompt(product_data)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=300,
    )
    raw_text = response.choices[0].message.content
    return extract_json(raw_text)
```

## Guidelines
- Always try Ollama first (`try/except` on connection error), fall back to Groq.
- Set `temperature=0.8` for creative marketing copy (not too random, not too safe).
- Limit `num_predict` / `max_tokens` to 300 — scripts should be SHORT.
- Cache generated scripts in memory so re-generating the same product is instant.
- If both LLMs fail, return a generic template script as ultimate fallback.
