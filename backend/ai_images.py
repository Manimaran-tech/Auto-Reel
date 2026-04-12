"""AI Image Generator — uses LLM to craft dynamic prompts, then FLUX to generate images."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import requests

from .config import settings


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BLUEPRINT SYSTEM
# Format: [Object] + [Material & Detail] + [Setting & Context]
#          + [Lighting] + [Camera/Angle/Focus] + [Post-processing/Vibe]
# ══════════════════════════════════════════════════════════════════════════════

def _build_image_prompt_request(product: dict) -> str:
    """Ask the LLM to generate 6 professional photography prompts in JSON."""
    title = product.get("title", "Product")
    features = ", ".join(product.get("features", [])[:5])
    price = product.get("price", "N/A")

    return f"""You are an elite commercial photographer and art director creating ad campaigns.
Craft 6 WILDLY DIFFERENT image generation prompts for this product.

PRODUCT DATA:
- Name: {title}
- Price: {price}
- Key Features: {features}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROMPT STRUCTURE (MANDATORY for each prompt):
[Object] + [Material & Detail] + [Setting & Context] + [Lighting] + [Camera/Angle/Focus] + [Post-processing/Vibe]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MANDATORY POWER KEYWORDS to inject naturally:
- Surface: "matte", "glossy", "brushed metal", "satin finish"
- Camera: "50mm DSLR shot", "35mm lens", "wide angle lens", "overhead drone view"
- Focus: "shallow depth of field", "crispy sharp detail", "creamy background blur"
- Light: "soft lighting from left", "golden hour sunlight", "studio ring light", "natural window light"
- Composition: "symmetrical composition", "product branding visible", "rule of thirds"
- Mood: "early morning sun", "shot on vintage film", "editorial magazine feel"

6 SHOT STYLES (one per prompt):
1. "Hero Product Shot" — {title} centered on clean matte gradient backdrop, soft diffused studio lighting from both sides, 50mm DSLR shot, shallow depth of field, glossy surface reflections, commercial product photography
2. "Lifestyle In-Use" — {title} being used naturally in an aspirational real-world setting, add brand-adjacent objects that reinforce the lifestyle, natural window light, 35mm lens, warm tones, slight vintage film grain
3. "Premium Flat Lay" — overhead bird's-eye drone view of {title} on marble surface with complementary lifestyle objects (coffee, leather notebook, green plant), early morning sun, symmetrical composition, matte textures
4. "Close-Up Detail" — extreme macro of {title} showing material quality and surface texture, satin finish details, studio ring light, crisp sharp detail, shallow depth of field, creamy background blur
5. "Aspirational Environment" — {title} placed in luxury modern interior (penthouse loft with floor-to-ceiling windows), golden hour sunlight streaming in, cinematic wide angle lens, editorial magazine style, product branding visible
6. "Bold Marketing Ad" — {title} floating on bold solid color background, dramatic directional shadow from left, high contrast, clean modern advertising aesthetic, glossy reflections on surface, 50mm lens

CRITICAL RULES:
- Each prompt MUST be 40-75 words (sweet spot for FLUX)
- Use 5-10 descriptive chunks per prompt max
- NEVER use vague adjectives: "beautiful", "nice", "amazing", "stunning"
- ALWAYS include the EXACT product name "{title}" in every prompt
- Describe materials and surfaces precisely (matte, glossy, brushed, satin)
- Control light direction explicitly (from left, from right, overhead, behind)
- Add time-of-day context where relevant (golden hour, early morning, twilight)

OUTPUT FORMAT (respond ONLY with this JSON, nothing else):
{{
  "prompts": [
    "prompt 1 text here",
    "prompt 2 text here",
    "prompt 3 text here",
    "prompt 4 text here",
    "prompt 5 text here",
    "prompt 6 text here"
  ]
}}"""


def _extract_prompts_json(raw_text: str) -> list[str]:
    """Robustly extract the prompts array from LLM output."""
    text = raw_text.strip()

    # Try direct JSON parse
    try:
        data = json.loads(text)
        if "prompts" in data:
            return data["prompts"][:6]
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if "prompts" in data:
                return data["prompts"][:6]
        except json.JSONDecodeError:
            pass

    # Try finding any JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end])
            if "prompts" in data:
                return data["prompts"][:6]
        except json.JSONDecodeError:
            pass

    return []


def _generate_prompts_with_groq(product: dict) -> list[str]:
    """Use Groq LLM to dynamically generate 6 prompts based on product data."""
    if not settings.groq_api_key:
        return []

    try:
        from groq import Groq
    except ImportError:
        return []

    prompt = _build_image_prompt_request(product)
    client = Groq(api_key=settings.groq_api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a professional commercial photographer. Respond ONLY with valid JSON. No markdown, no explanation."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.85,
        max_tokens=1200,
    )
    raw_text = completion.choices[0].message.content or ""
    return _extract_prompts_json(raw_text)


def _fallback_prompts(product: dict) -> list[str]:
    """Static fallback using the photography prompt blueprint."""
    title = product.get("title", "Product")
    features = product.get("features", [])
    feat = features[0] if features else "premium build quality"

    return [
        f"{title} centered on clean matte white-to-grey gradient studio backdrop, glossy surface reflections visible, soft diffused lighting from both sides, 50mm DSLR shot, shallow depth of field, commercial product photography, high-end advertising aesthetic",
        f"Person naturally using {title} in modern home office with large window, {feat}, natural window light from left creating soft shadows, 35mm lens, warm tones, slight vintage film grain, aspirational lifestyle advertisement",
        f"Overhead bird's-eye view of {title} on white marble surface beside ceramic coffee cup, leather notebook, and small green plant, early morning sun from right, symmetrical composition, matte textures, premium flat lay photography",
        f"Extreme macro close-up of {title} showing {feat}, brushed metal and satin finish surface details, studio ring light reflection on glossy elements, crisp sharp detail, shallow depth of field with creamy background blur",
        f"{title} placed in luxury modern penthouse loft with floor-to-ceiling windows, golden hour sunlight streaming in from behind, cinematic wide angle lens, product branding visible, editorial magazine style photography",
        f"{title} floating on bold solid deep navy background, dramatic directional shadow cast from left side, high contrast studio lighting, glossy surface reflections, clean modern advertising aesthetic, 50mm lens, {feat}",
    ]


async def generate_ai_images(product: dict, output_dir: Path, max_images: int = 6) -> list[str]:
    """Generate images using LLM-crafted prompts + HuggingFace FLUX API."""
    if not settings.hf_api_token:
        print("No HF token found, skipping AI image generation.")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Use LLM to dynamically generate prompts!
    print("🧠 Asking LLM to craft 6 dynamic image prompts...")
    prompts = _generate_prompts_with_groq(product)
    if not prompts or len(prompts) < 3:
        print("⚠️ LLM prompt generation failed, using expert fallback prompts.")
        prompts = _fallback_prompts(product)

    print(f"📸 Got {len(prompts)} prompts, generating images via FLUX...")

    # Step 2: Generate images via HuggingFace FLUX
    API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {settings.hf_api_token}"}
    generated_paths = []

    # Request max resolution from FLUX (1024x1024), we upscale to 2K after
    payload_base = {
        "parameters": {
            "width": 1024,
            "height": 1024,
        }
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        for i, prompt in enumerate(prompts[:max_images]):
            print(f"  🎨 [{i+1}/{min(len(prompts), max_images)}] {prompt[:70]}...")
            try:
                payload = {**payload_base, "inputs": prompt}
                response = await client.post(API_URL, headers=headers, json=payload)
                if response.status_code == 200:
                    # Upscale to 2K using high-quality LANCZOS resampling
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(response.content)).convert("RGB")
                    img = img.resize((2048, 2048), Image.Resampling.LANCZOS)
                    img_path = output_dir / f"ai_product_{i}.jpg"
                    img.save(str(img_path), "JPEG", quality=95)
                    generated_paths.append(str(img_path))
                    print(f"  ✅ Generated {img_path.name} (upscaled to 2048×2048)")
                else:
                    print(f"  ❌ HF API error {response.status_code}: {response.text[:100]}")
            except Exception as e:
                print(f"  ❌ Exception generating image {i+1}: {e}")

            # Brief pause between requests
            await asyncio.sleep(1.5)

    print(f"🎬 Total AI images generated: {len(generated_paths)}")
    return generated_paths
