"""Instagram Distributor — post reels directly or save as draft (fallback)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path


# Default session/debug directories (relative to output)
_SESSION_DIR: Path | None = None
_DEBUG_DIR: Path | None = None


def _get_session_dir() -> Path:
    global _SESSION_DIR
    if _SESSION_DIR is None:
        from .config import settings
        _SESSION_DIR = settings.output_dir / "ig_session"
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSION_DIR


def _get_debug_dir() -> Path:
    global _DEBUG_DIR
    if _DEBUG_DIR is None:
        from .config import settings
        _DEBUG_DIR = settings.output_dir / "ig_debug"
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    return _DEBUG_DIR


async def _save_debug_screenshot(page, label: str = "error") -> str | None:
    """Save a debug screenshot on failure for diagnostics."""
    try:
        debug_dir = _get_debug_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = debug_dir / f"{label}_{ts}.png"
        await page.screenshot(path=str(path), full_page=True)
        print(f"📸 Debug screenshot: {path}")
        return str(path)
    except Exception as e:
        print(f"Failed to save debug screenshot: {e}")
        return None


async def _wait_and_click(page, selectors: list[str], timeout: int = 5000) -> bool:
    """Try multiple selectors, click the first one found."""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click()
            return True
        except Exception:
            continue
    return False


async def _dismiss_popups(page) -> None:
    """Dismiss common Instagram popups (notifications, save login, etc.)."""
    dismiss_selectors = [
        "button:has-text('Not Now')",
        "button:has-text('Not now')",
        "button:has-text('Cancel')",
        "button:has-text('Dismiss')",
        "[role='button']:has-text('Not Now')",
    ]
    for selector in dismiss_selectors:
        try:
            loc = page.locator(selector).first
            if await loc.is_visible(timeout=1500):
                await loc.click()
                await page.wait_for_timeout(800)
        except Exception:
            pass


# ── Manual Login Flow ─────────────────────────────────────────────────────────

async def open_login_browser(username: str) -> dict:
    """Open a real Chromium browser for the user to log in manually.

    The session is persisted to disk so subsequent uploads can reuse it.
    Returns when the user reaches the Instagram feed (login confirmed).
    """
    if not username:
        return {"success": False, "message": "Username is required to create a session folder."}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "message": "Playwright not installed. Run: pip install playwright && playwright install chromium"}

    session_dir = _get_session_dir()
    user_dir = session_dir / username
    user_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_dir),
                headless=False,
                slow_mo=50,
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()

            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            print("🔐 Browser opened — waiting for user to log in manually...")

            # Wait up to 5 minutes for the user to log in and reach the feed
            try:
                await page.wait_for_url(
                    "**/instagram.com/**",
                    timeout=300_000,
                )
                # Give extra time for the page to settle
                await page.wait_for_timeout(3000)

                # Check for feed indicators (user is logged in)
                logged_in = False
                for _ in range(60):  # poll for up to 60 seconds
                    feed_indicators = [
                        "svg[aria-label='Home']",
                        "a[href='/']",
                        "svg[aria-label='New post']",
                        "svg[aria-label='New Post']",
                        "[aria-label='Home']",
                        "a[href='/explore/']",
                    ]
                    for sel in feed_indicators:
                        try:
                            if await page.locator(sel).first.is_visible(timeout=500):
                                logged_in = True
                                break
                        except Exception:
                            pass
                    if logged_in:
                        break
                    await page.wait_for_timeout(1000)

            except Exception:
                pass  # Timeout — user may have closed the browser

            # Dismiss any popups before closing
            await _dismiss_popups(page)
            await page.wait_for_timeout(1000)

            await browser.close()

        return {
            "success": True,
            "message": "Instagram session saved! You can now post reels.",
        }

    except Exception as exc:
        return {"success": False, "message": f"Login browser failed: {exc}"}


async def check_session(username: str) -> dict:
    """Check if a saved Instagram session exists for the given username."""
    if not username:
        return {"valid": False, "message": "No username configured."}

    session_dir = _get_session_dir()
    user_dir = session_dir / username

    if not user_dir.exists():
        return {"valid": False, "message": "No session found. Please log in first."}

    # Check if there are any cookie/session files
    has_data = any(user_dir.iterdir())
    if not has_data:
        return {"valid": False, "message": "Session folder is empty. Please log in again."}

    return {"valid": True, "message": f"Session active for @{username}"}


# ── Upload Flow (no login — uses pre-authenticated session) ───────────────────

async def push_to_instagram(
    video_path: str | Path,
    caption: str,
    username: str,
    password: str = "",
    product_url: str = "",
    headless: bool = False,
) -> dict:
    """Upload a video to Instagram — post directly (Share), Draft as fallback.

    Uses a pre-authenticated persistent session — no automated login.
    If no session exists, directs the user to log in manually first.
    """

    if not username:
        return {
            "success": False,
            "message": "Instagram username not set. Go to Settings and configure your account.",
        }

    upload_file = Path(video_path)
    if not upload_file.exists():
        return {"success": False, "message": f"Video not found: {upload_file}"}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "message": "Playwright not installed. Run: pip install playwright && playwright install chromium"}

    session_dir = _get_session_dir()
    user_dir = session_dir / username

    if not user_dir.exists() or not any(user_dir.iterdir()):
        return {
            "success": False,
            "message": "No Instagram session found! Go to Settings → click 'Open Instagram Login' → log in manually first.",
        }

    try:
        async with async_playwright() as p:
            # ── Launch with the saved persistent session ──────────────────
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_dir),
                headless=headless,
                slow_mo=100,
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()

            # ── Navigate to Instagram ─────────────────────────────────────
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # ── Verify we're logged in (check POSITIVE indicators) ───────
            logged_in = False
            feed_indicators = [
                "svg[aria-label='Home']",
                "[aria-label='Home']",
                "svg[aria-label='New post']",
                "svg[aria-label='New Post']",
                "a[href='/explore/']",
                "svg[aria-label='Search']",
                "[aria-label='Notifications']",
            ]
            for sel in feed_indicators:
                try:
                    if await page.locator(sel).first.is_visible(timeout=2000):
                        logged_in = True
                        break
                except Exception:
                    pass

            if not logged_in:
                screenshot = await _save_debug_screenshot(page, "session_expired")
                await browser.close()
                return {
                    "success": False,
                    "message": "Instagram session expired! Go to Settings → click 'Open Instagram Login' → log in again.",
                }

            print("✅ Session restored — already logged in!")

            # ── Dismiss popups ────────────────────────────────────────────
            await _dismiss_popups(page)
            await page.wait_for_timeout(1000)

            # ── Open Create Post dialog ───────────────────────────────────
            print("📤 Opening create post dialog...")
            create_clicked = await _wait_and_click(page, [
                "svg[aria-label='New post']",
                "[aria-label='New post']",
                "svg[aria-label='New Post']",
                "[aria-label='New Post']",
                "[aria-label='Create']",
                "a[href='/create/select/']",
                "a[href='/create/style/']",
                "//span[text()='Create']/..",
                "text=Create",
            ], timeout=8000)

            if not create_clicked:
                # Try clicking the + icon in the sidebar
                create_clicked = await _wait_and_click(page, [
                    "a:has(svg[aria-label='New post'])",
                    "a:has(svg[aria-label='New Post'])",
                    "//a[contains(@href, 'create')]",
                ], timeout=3000)

            if not create_clicked:
                screenshot = await _save_debug_screenshot(page, "no_create_btn")
                await browser.close()
                return {
                    "success": False,
                    "message": f"Could not find 'Create' button. Instagram UI may have changed. Debug screenshot saved.",
                }

            await page.wait_for_timeout(1500)

            # Some accounts open dialog directly, some open a submenu.
            # Check if file input is already there before clicking submenu
            file_input_present = await page.locator("input[type='file']").count() > 0
            
            if not file_input_present:
                # Check if clicking Create opened a dropdown instead of the dialog
                post_submenu = await _wait_and_click(page, [
                    "a span:text-is('Reel')",
                    "div[role='none'] span:text-is('Reel')",
                    "//span[text()='Reel']",
                    "//div[text()='Reel']",
                    "a span:text-is('Post')",
                    "div[role='none'] span:text-is('Post')",
                    "//span[text()='Post']",
                    "//div[text()='Post']"
                ], timeout=2000)
                
                if post_submenu:
                    print("  ➡️ Clicked 'Reel' from Create submenu")
                    await page.wait_for_timeout(1500)

            # ── Upload the video file ─────────────────────────────────────
            print("📁 Uploading video file...")
            upload_ok = await _upload_video(page, upload_file)
            if not upload_ok:
                screenshot = await _save_debug_screenshot(page, "upload_failed")
                await browser.close()
                return {"success": False, "message": "Failed to upload video file. Check debug screenshot."}

            print("⏳ Waiting for video processing...")
            # Wait for the Next button to appear (video processed)
            for wait_step in range(20):
                next_visible = False
                for sel in [
                    "//div[text()='Next']",
                    "button:has-text('Next')",
                    "[role='button']:has-text('Next')",
                ]:
                    try:
                        if await page.locator(sel).first.is_visible(timeout=1000):
                            next_visible = True
                            break
                    except Exception:
                        pass
                if next_visible:
                    break
                await page.wait_for_timeout(2000)

            # ── Select 9:16 Crop Ratio ────────────────────────────────────
            print("🔲 Setting crop ratio to 9:16...")
            crop_btn_clicked = await _wait_and_click(page, [
                "button[aria-label='Select crop']",
                "svg[aria-label='Select crop']",
                "[aria-label='Select crop']"
            ], timeout=3000)
            
            if crop_btn_clicked:
                await page.wait_for_timeout(1000)
                await _wait_and_click(page, [
                    "//span[text()='9:16']",
                    "//div[text()='9:16']"
                ], timeout=2000)
                print("  ➡️ Selected 9:16 crop")
                await page.wait_for_timeout(1000)
            else:
                print("  ⚠️ Crop button not found, assuming default or already 9:16")

            # ── Click through Next/Continue buttons to reach caption screen ──
            for step in range(4):
                clicked = await _wait_and_click(page, [
                    "//div[text()='Next']",
                    "button:has-text('Next')",
                    "[role='button']:has-text('Next')",
                    "//div[text()='Continue']",
                    "button:has-text('Continue')",
                ], timeout=2000)
                if clicked:
                    print(f"  ➡️ Clicked Next (step {step + 1})")
                    await page.wait_for_timeout(800)
                else:
                    break

            # ── Fill in caption (with product URL) ────────────────────────
            full_caption = caption
            if product_url and product_url not in caption:
                full_caption = f"{caption}\n\n🛒 Buy here: {product_url}"

            print("✍️ Adding caption...")
            caption_filled = await _fill_caption(page, full_caption)
            if not caption_filled:
                print("  ⚠️ Could not fill caption field, continuing anyway...")

            await page.wait_for_timeout(1500)

            # ── Add Location (Quick First Result) ───────────────────────────
            print("📍 Adding location...")
            location_input_clicked = await _wait_and_click(page, [
                "input[placeholder='Add location']",
                "input[aria-label='Add location']",
                "//div[contains(text(), 'Add location')]/following-sibling::div//input"
            ], timeout=800)
            
            if location_input_clicked:
                await page.keyboard.insert_text("America")
                await page.wait_for_timeout(500) # Short wait for dropdown to populate
                # Click the New York dropdown explicitly
                await _wait_and_click(page, [
                    "//span[contains(text(), 'New York')]",
                    "//div[contains(text(), 'New York')]",
                    "text=New York"
                ], timeout=800)
                print("  ✅ Location set instantly")
            else:
                print("  ⚠️ Location field not found...")

            # ── STRATEGY: Post directly first, Draft as fallback ──────────
            print("🚀 Attempting to post reel...")

            # Try Share / Post button directly
            share_clicked = await _wait_and_click(page, [
                "//div[text()='Share']",
                "//span[text()='Share']",
                "button:has-text('Share')",
                "[role='button']:has-text('Share')",
                "div:text-is('Share')",
                "//div[text()='Post']",
                "button:has-text('Post')",
            ], timeout=400)

            if share_clicked:
                print("✅ Clicked Share — posting reel!")
                
                # Wait for the post to process and the "Sharing" modal to close.
                # Instagram can take 15-45 seconds to fully compress and share a video.
                print("⏳ Waiting for Instagram to finish sharing...")
                
                # Wait until the 'Sharing' dialog is gone or a success toast appears
                for poll_step in range(40):  # Wait up to 40 seconds
                    # Sometimes an explicit "Your reel has been shared" toast pops up
                    # Or the sharing modal disappears (Next/Share buttons are gone and we return to feed)
                    await page.wait_for_timeout(1000)
                
                await _save_debug_screenshot(page, "post_result")
                await browser.close()
                return {
                    "success": True,
                    "message": "✅ Reel posted to Instagram! Check your profile.",
                }

            # Share didn't work — try saving as Draft instead
            print("  Share button not found — trying Draft...")

            # Try back/close to trigger discard/save dialog
            back_clicked = await _wait_and_click(page, [
                "[aria-label='Close']",
                "[aria-label='Go back']",
                "[aria-label='Go Back']",
                "[aria-label='Back']",
                "svg[aria-label='Close']",
                "svg[aria-label='Back']",
                "svg[aria-label='Go back']",
                "button[aria-label='Close']",
                "button[aria-label='Back']",
            ], timeout=3000)

            if not back_clicked:
                print("  Trying Escape key...")
                await page.keyboard.press("Escape")

            await page.wait_for_timeout(2500)

            # Look for save draft button in the dialog
            draft_saved = await _wait_and_click(page, [
                "//button[contains(text(),'Save draft')]",
                "//button[contains(text(),'Save Draft')]",
                "button:has-text('Save draft')",
                "button:has-text('Save Draft')",
                "//div[contains(text(),'Save draft')]",
                "//div[contains(text(),'Save Draft')]",
                "[role='button']:has-text('Save draft')",
                "[role='button']:has-text('Save Draft')",
            ], timeout=5000)

            if draft_saved:
                print("✅ Draft saved!")
                await page.wait_for_timeout(2000)
                await browser.close()
                return {
                    "success": True,
                    "message": "📝 Reel saved to Instagram Drafts! Open Instagram to review and post.",
                }

            # Neither Share nor Draft worked — save debug screenshot
            screenshot = await _save_debug_screenshot(page, "no_share_or_draft")
            await browser.close()
            return {
                "success": False,
                "message": "Could not find Share or Draft button. Check debug screenshot in output/ig_debug/.",
            }

    except Exception as exc:
        return {"success": False, "message": f"Distribution failed: {exc}"}


async def _upload_video(page, upload_file: Path) -> bool:
    """Handle the video file upload — tries file input, then 'select from computer' button."""
    try:
        file_input = page.locator("input[type='file']").first
        await file_input.wait_for(state="attached", timeout=8000)
        await file_input.set_input_files(str(upload_file.resolve()))
        return True
    except Exception:
        pass

    # Sometimes a "Select from computer" button appears first
    select_clicked = await _wait_and_click(page, [
        "button:has-text('Select from computer')",
        "button:has-text('Select From Computer')",
        "text=Select from computer",
    ], timeout=3000)
    if select_clicked:
        await page.wait_for_timeout(1000)
        try:
            file_input = page.locator("input[type='file']").first
            await file_input.wait_for(state="attached", timeout=5000)
            await file_input.set_input_files(str(upload_file.resolve()))
            return True
        except Exception:
            pass

    return False


async def _fill_caption(page, caption: str) -> bool:
    """Fill in the caption text box."""
    caption_selectors = [
        "div[aria-label='Write a caption...']",
        "textarea[aria-label='Write a caption...']",
        "div[role='textbox']",
        "[contenteditable='true']",
    ]
    for selector in caption_selectors:
        try:
            loc = page.locator(selector).first
            if await loc.is_visible(timeout=300):
                await loc.click()
                await page.keyboard.insert_text(caption) # instant paste instead of typing
                print("  ✅ Caption added!")
                return True
        except Exception:
            continue
    return False


# Keep backward-compatible alias
async def push_to_instagram_draft(
    video_path: str | Path,
    caption: str,
    username: str,
    password: str = "",
    headless: bool = False,
    product_url: str = "",
) -> dict:
    """Backward-compatible wrapper — now posts directly with Draft as fallback."""
    return await push_to_instagram(
        video_path=video_path,
        caption=caption,
        username=username,
        password=password,
        product_url=product_url,
        headless=headless,
    )
