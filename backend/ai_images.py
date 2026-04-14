"""AI Image Generator — uses LLM to craft dynamic prompts, then NVIDIA SD3 (or FLUX fallback) to generate images."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
from pathlib import Path

import httpx
from PIL import Image

from .config import settings


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BLUEPRINT SYSTEM
# Format: [Object] + [Material & Detail] + [Setting & Context]
#          + [Lighting] + [Camera/Angle/Focus] + [Post-processing/Vibe]
# ══════════════════════════════════════════════════════════════════════════════

def _build_image_prompt_request(product: dict) -> str:
    """Ask the LLM to generate 15 cartoon-style product image prompts in JSON."""
    title = product.get("title", "Product")
    features = ", ".join(product.get("features", [])[:5])
    price = product.get("price", "N/A")

    return f"""You are an elite cartoon illustrator and ad creative director creating images for a Family Guy style marketing reel.
Craft 15 WILDLY DIFFERENT cartoon/animated-style image generation prompts for this product.

PRODUCT DATA:
- Name: {title}
- Price: {price}
- Key Features: {features}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STYLE RULES (MANDATORY for every prompt):
- The product MUST be the ONLY subject, filling the ENTIRE square frame
- Use bold cartoon/cel-shaded/vector art style (think Family Guy, thick outlines, flat vibrant colors)
- NO people, NO hands, NO lifestyle scenes — JUST the product
- Clean solid or simple gradient background (single color pop)
- 1:1 square composition, product centered and large
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

15 VARIATION IDEAS (one per prompt):
1. "Bold Cartoon Hero Shot" — product front-center, thick black outlines, pop-art burst background
2. "Neon Glow Toon" — glowing cartoon product on dark background
3. "Comic Book Panel" — halftone dots, speech bubble style
4. "Flat Vector Clean" — minimal flat design, pastel background
5. "Retro Cartoon Ad" — 60s cartoon commercial style
6. "Cel-Shaded 3D" — cel-shaded render, anime-inspired
7. "Graffiti Street Art" — bold spray-paint cartoon style
8. "Kawaii Cute" — chibi/kawaii cartoon style, sparkles
9. "Pixel Art" — retro pixel art style product
10. "Sticker Design" — die-cut sticker with white border
11. "Watercolor Cartoon" — loose watercolor cartoon illustration
12. "Pop Art Warhol" — Andy Warhol pop art repeated style
13. "Blueprint Toon" — technical blueprint with cartoon flair
14. "Explosion Reveal" — cartoon explosion with product emerging
15. "Holographic Shine" — iridescent holographic cartoon style

CRITICAL OUTPUT FORMAT (respond ONLY with JSON, nothing else):
{{
  "prompts": [
    "prompt 1...", "prompt 2...", "prompt 3...", "...", "prompt 15..."
  ]
}}"""


def _extract_prompts_json(raw_text: str) -> list[str]:
    text = raw_text.strip()
    try: data = json.loads(text); return data.get("prompts", [])[:15]
    except: pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try: return json.loads(match.group(1)).get("prompts", [])[:15]
        except: pass
    start, end = text.find("{"), text.rfind("}") + 1
    if start != -1 and end > start:
        try: return json.loads(text[start:end]).get("prompts", [])[:15]
        except: pass
    return []


def _generate_prompts_with_groq(product: dict) -> list[str]:
    if not settings.groq_api_key: return []
    try: from groq import Groq
    except ImportError: return []
    
    client = Groq(api_key=settings.groq_api_key)
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a cartoon illustrator. Respond ONLY with valid JSON. No markdown, no explanation."},
                {"role": "user", "content": _build_image_prompt_request(product)},
            ],
            temperature=0.85,
            max_tokens=2500,
        )
        return _extract_prompts_json(completion.choices[0].message.content or "")
    except:
        return []


def _fallback_prompts(product: dict) -> list[str]:
    title = product.get("title", "Product")
    feat = product.get("features", ["premium quality"])[0]
    return [
        f"{title} centered on solid bright yellow background, bold black cartoon outlines, cel-shaded flat color, 1:1 square composition, pop-art style",
        f"{title} glowing with neon cyan and magenta aura on dark navy background, cartoon illustration, thick outlines, centered product",
        f"{title} in comic book panel style with halftone dots and bold colors, centered large, 1:1 square, no people",
        f"{title} flat vector illustration, pastel mint green background, clean minimal cartoon, centered and large",
        f"{title} retro 1960s cartoon advertisement style, vintage colors, product centered on striped background",
        f"{title} cel-shaded 3D render, anime-inspired, bold outlines, gradient background, centered",
        f"{title} graffiti street art style, spray paint texture, bold cartoon product on brick wall background",
        f"{title} kawaii chibi cartoon style, sparkles and stars, cute pastel background, centered product",
        f"{title} pixel art retro game style, 8-bit aesthetic, solid color background, {feat}",
        f"{title} as a die-cut sticker design with white border, cartoon style, clean background",
        f"{title} watercolor cartoon illustration, loose brush strokes, warm tones, centered",
        f"{title} Andy Warhol pop art style, repeated 4x grid, bold contrasting colors",
        f"{title} cartoon blueprint technical drawing with fun annotations, blue tint background",
        f"{title} bursting out of cartoon explosion, action lines, {feat}, dynamic energy",
        f"{title} with holographic iridescent rainbow shine, cartoon style, dark background, centered",
    ]


async def _generate_nvidia_sd3(prompt: str, output_path: Path, client: httpx.AsyncClient) -> bool:
    """Generate image using NVIDIA SD3-Medium API."""
    if not settings.nvidia_api_key: return False
    
    url = "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-3-medium"
    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "seed": 0,
        "cfg_scale": 5.0,
        "steps": 28,
        # SD3 NIM often accepts aspect_ratio instead of strict w/h to guarantee composition
        "aspect_ratio": "1:1" 
    }
    
    try:
        resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
        if resp.status_code == 200:
            data = resp.json()
            b64_data = data.get("image") or (data.get("artifacts", [{}])[0].get("base64") if "artifacts" in data else None)
            if b64_data:
                img = Image.open(io.BytesIO(base64.b64decode(b64_data))).convert("RGB")
                # Upscale strictly to 4K 16:9 (3840x2160)
                img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
                img.save(str(output_path), "JPEG", quality=95)
                return True
        elif resp.status_code == 422:
            # If aspect_ratio causes 422, fallback without it
            payload.pop("aspect_ratio")
            resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                b64_data = data.get("image") or (data.get("artifacts", [{}])[0].get("base64") if "artifacts" in data else None)
                if b64_data:
                    img = Image.open(io.BytesIO(base64.b64decode(b64_data))).convert("RGB")
                    img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
                    img.save(str(output_path), "JPEG", quality=95)
                    return True
    except Exception as e:
        print(f"  ❌ NVIDIA API Exception: {e}")
    return False


async def _generate_hf_flux(prompt: str, output_path: Path, client: httpx.AsyncClient) -> bool:
    """Generate image using HuggingFace FLUX fallback."""
    if not settings.hf_api_token: return False
    
    url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {settings.hf_api_token}"}
    payload = {
        "inputs": prompt,
        "parameters": {"width": 1024, "height": 1024}
    }
    
    try:
        resp = await client.post(url, headers=headers, json=payload, timeout=60.0)
        if resp.status_code == 200:
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            # Upscale strictly to 4K 16:9 (3840x2160)
            img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
            img.save(str(output_path), "JPEG", quality=95)
            return True
    except Exception as e:
        print(f"  ❌ HF FLUX Exception: {e}")
    return False



async def generate_ai_images(product: dict, output_dir: Path, max_images: int = 15) -> list[str]:
    """Primary entry point to generate AI Sequence Images."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🧠 Asking LLM to craft {max_images} dynamic image prompts...")
    prompts = _generate_prompts_with_groq(product)
    
    if not prompts or len(prompts) < 5:
        print("⚠️ LLM prompt generation failed or was insufficient, using expert fallback prompts.")
        prompts = _fallback_prompts(product)

    generated_paths = []
    
    async with httpx.AsyncClient() as client:
        for i, prompt in enumerate(prompts[:max_images]):
            print(f"  🎨 [{i+1}/{min(len(prompts), max_images)}] {prompt[:70]}...")
            out_file = output_dir / f"ai_product_{i}.jpg"
            
            # ATTEMPT 1: NVIDIA SD3 (Fast, high-quality)
            success = await _generate_nvidia_sd3(prompt, out_file, client)
            
            # ATTEMPT 2: HF FLUX Fallback
            if not success:
                print("  ⚠️ NVIDIA API failed. Falling back to HF FLUX API...")
                success = await _generate_hf_flux(prompt, out_file, client)
                
            if success:
                generated_paths.append(str(out_file))
                print(f"  ✅ Generated frame {i+1} (1024x1024 cartoon style)")
            else:
                print(f"  ❌ Failed to generate frame {i+1}")
                
            await asyncio.sleep(0.3)

    print(f"🎬 Total AI frames generated: {len(generated_paths)}")
    return generated_paths
