"""AI Video Generation via HuggingFace Inference API — uses LTX Video to animate product images."""

from __future__ import annotations

import io
import time
from pathlib import Path

import httpx
from PIL import Image

from .config import settings

# LTX Video model on HuggingFace
LTX_VIDEO_MODEL = "Lightricks/LTX-Video"
# Fallback: Stable Video Diffusion  
SVD_MODEL = "stabilityai/stable-video-diffusion-img2vid-xt"

HF_API_URL = "https://api-inference.huggingface.co/models"


async def generate_ai_video_from_image(
    image_path: str | Path,
    output_path: str | Path,
    prompt: str = "smooth camera zoom into the product, professional lighting, commercial style",
    duration_hint: int = 4,
) -> str | None:
    """Generate a short AI video clip from a product image using HF Inference API."""
    api_token = settings.hf_api_token
    if not api_token:
        print("HF_API_TOKEN not set. Skipping AI video generation.")
        return None

    image_path = Path(image_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare image - resize to 512x512 for the model
    img = Image.open(image_path).convert("RGB")
    img = img.resize((512, 512), Image.Resampling.BILINEAR)
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="JPEG", quality=90)
    img_bytes.seek(0)

    headers = {"Authorization": f"Bearer {api_token}"}

    # Try LTX Video first (image-to-video)
    for model_id in [LTX_VIDEO_MODEL, SVD_MODEL]:
        print(f"Trying AI video generation with {model_id}...")
        api_url = f"{HF_API_URL}/{model_id}"

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Send image for image-to-video generation
                response = await client.post(
                    api_url,
                    headers=headers,
                    content=img_bytes.getvalue(),
                )

                if response.status_code == 503:
                    # Model is loading — wait and retry
                    estimated = response.json().get("estimated_time", 30)
                    print(f"Model loading... waiting {estimated}s")
                    await _async_sleep(min(estimated, 60))
                    img_bytes.seek(0)
                    response = await client.post(
                        api_url,
                        headers=headers,
                        content=img_bytes.getvalue(),
                    )

                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "video" in content_type or "octet" in content_type:
                        output_path.write_bytes(response.content)
                        print(f"AI video generated: {output_path} ({len(response.content)} bytes)")
                        return str(output_path)
                    else:
                        print(f"Unexpected response type: {content_type}")
                        print(f"Response: {response.text[:200]}")
                else:
                    print(f"API error {response.status_code}: {response.text[:200]}")

        except httpx.TimeoutException:
            print(f"Timeout with {model_id}, trying next...")
        except Exception as exc:
            print(f"Error with {model_id}: {exc}")

        img_bytes.seek(0)  # Reset for next attempt

    print("AI video generation failed with all models. Falling back to static.")
    return None


async def generate_ai_clips(
    image_paths: list[str],
    output_dir: Path,
    product_title: str = "",
    max_clips: int = 2,
) -> list[str]:
    """Generate AI video clips from product images."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clips = []

    for idx, img_path in enumerate(image_paths[:max_clips]):
        output = output_dir / f"ai_clip_{idx + 1}.mp4"
        prompt = f"smooth cinematic zoom, {product_title}, commercial advertisement, professional lighting"
        result = await generate_ai_video_from_image(img_path, output, prompt=prompt)
        if result:
            clips.append(result)

    return clips


async def _async_sleep(seconds: float) -> None:
    """Async-compatible sleep."""
    import asyncio
    await asyncio.sleep(seconds)
