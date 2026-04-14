import asyncio
import os
from pathlib import Path

from backend.copywriter import generate_script
from backend.voice_engine import generate_dialogue_voiceover
from backend.video_renderer import render_reel

product_data = {
    "title": "AirPods Gen 3",
    "price": "$179",
    "features": ["Personalized Spatial Audio", "Sweat and water resistant", "Force sensor control"],
    "images": []
}

async def main():
    print("0. Pulling AI Product Image (if not already downloaded)...")
    try:
        from backend.ai_images import generate_ai_images
        ai_out = Path("output/ai_imgs")
        ai_out.mkdir(parents=True, exist_ok=True)
        imgs = await generate_ai_images(product_data, ai_out, max_images=1)
        if imgs:
            product_data["images"] = imgs
    except Exception as e:
        print("Skipping AI Images, proceeding without product pop-up.", e)

    print("\n1. Generating Script...")
    copy = generate_script(product_data)
    dialogue = copy["dialogue"]
    for line in dialogue:
        print(f"[{line['speaker'].upper()}]: {line['text']}")
    
    print("\n2. Generating Voices (RVC)...")
    out_audio = Path("output/test_airpods.mp3")
    out_subs = Path("output/test_airpods.json")
    out_audio.parent.mkdir(parents=True, exist_ok=True)
    await generate_dialogue_voiceover(dialogue, out_audio, out_subs)
    
    print("\n3. Rendering Reel...")
    out_video = Path("output/test_airpods_final.mp4")
    p_img = product_data["images"][0] if product_data["images"] else None
    
    render_reel(
        voiceover_path=out_audio,
        subtitles_path=out_subs,
        output_path=out_video,
        product_image_path=p_img
    )
    print(f"\nDone! Video saved to {out_video.absolute()}")

if __name__ == "__main__":
    asyncio.run(main())
