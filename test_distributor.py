"""Test the distributor directly with an existing local video — no API keys needed."""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.distributor import push_to_instagram_draft, check_session

# ── Config ────────────────────────────────────────────────────
USERNAME = "product.trend_tester"
PASSWORD = ""  # Not needed — we use the saved session
VIDEO_PATH = r"D:\Hackathon\output\jobs\49f0a0ed61\final_reel.mp4"
CAPTION = "Experience the future of audio with Apple AirPods Pro 3! Active Noise Cancellation, Spatial Audio, and heart rate sensing. Get yours for $300.00. #AppleAirPodsPro3 #ActiveNoiseCancellation #SpatialAudio #FitnessEarbuds"
PRODUCT_URL = "https://amzn.to/4233hny"


async def main():
    print(f"Username: {USERNAME}")
    print(f"Video: {VIDEO_PATH}")

    # 1. Check session first
    session = await check_session(USERNAME)
    print(f"Session: {session}")
    if not session["valid"]:
        print("❌ No session! Run the login browser first.")
        return

    # 2. Push to draft/post
    print("\n🚀 Pushing to Instagram...")
    result = await push_to_instagram_draft(
        video_path=VIDEO_PATH,
        caption=CAPTION,
        username=USERNAME,
        password=PASSWORD,
        headless=False,  # Keep visible so you can see what happens
        product_url=PRODUCT_URL,
    )
    print(f"\n📋 Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
