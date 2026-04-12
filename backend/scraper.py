from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

AMAZON_SELECTORS = {
    "title": "#productTitle, h1#title, span.product-title-word-break",
    "price": ".a-price-whole, #priceblock_ourprice, .a-price",
    "features": "#feature-bullets ul li span.a-list-item, #featurebullets_feature_div li span",
    "images": "#landingImage, #imgBlkFront, #main-image, .a-dynamic-image",
}

SHOPIFY_SELECTORS = {
    "title": "h1, .product-title, .product__title",
    "price": ".price, .product__price, [data-product-price]",
    "features": ".product__description li, .product__description p, .rte li",
    "images": ".product__media img, .product__image img, img.product-featured-media",
}

GENERIC_SELECTORS = {
    "title": "h1",
    "price": "[class*=price], [id*=price]",
    "features": "ul li, .features li, .description li",
    "images": "img",
}


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "amazon." in host or "amzn." in host:
        return "amazon"
    if "flipkart." in host:
        return "flipkart"
    if "shopify" in host:
        return "shopify"
    return "generic"


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _extract_price(text: str) -> str:
    match = re.search(r"([₹$€£]\s?\d[\d,]*(?:\.\d{1,2})?)", text)
    return match.group(1) if match else text.strip()


def _is_captcha_page(html: str) -> bool:
    text = html.lower()
    return "captcha" in text and ("robot" in text or "automated access" in text)


def _normalize_image_url(url: str) -> str:
    cleaned = url.split("?", 1)[0]
    cleaned = re.sub(r"\._AC_[A-Z0-9,_]+\.", "._AC_SL1500_.", cleaned)
    if cleaned.startswith("//"):
        cleaned = f"https:{cleaned}"
    return cleaned


async def _download_image(client: httpx.AsyncClient, url: str, path: Path) -> str | None:
    try:
        response = await client.get(url, timeout=20.0)
        response.raise_for_status()
        path.write_bytes(response.content)
        return str(path)
    except Exception:
        return None


async def download_images(image_urls: list[str], output_dir: Path, max_images: int = 3) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    unique_urls: list[str] = []
    for image_url in image_urls:
        normalized = _normalize_image_url(image_url)
        if normalized not in unique_urls:
            unique_urls.append(normalized)
    unique_urls = unique_urls[:max_images]

    if not unique_urls:
        return []

    async with httpx.AsyncClient(
        follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        tasks = []
        for idx, image_url in enumerate(unique_urls, start=1):
            ext = Path(urlparse(image_url).path).suffix or ".jpg"
            file_path = output_dir / f"img_{idx}{ext if len(ext) <= 5 else '.jpg'}"
            tasks.append(_download_image(client, image_url, file_path))
        results = await asyncio.gather(*tasks)
    return [path for path in results if path]


async def _get_html(url: str) -> str:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(user_agent=USER_AGENT, locale="en-US")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # CAPTCHA solving loop for local hackathon demo
            for _ in range(15):
                html = await page.content()
                if not _is_captcha_page(html):
                    break
                print("CAPTCHA detected... Please solve it in the browser! Waiting 3s...")
                await page.wait_for_timeout(3000)

            if _is_captcha_page(html):
                raise RuntimeError("Scraper blocked by anti-bot challenge (CAPTCHA detected).")
            
            # Scroll down to trigger lazy-loaded content
            await page.evaluate("window.scrollTo(0, 500)")
            await page.wait_for_timeout(1000)
            html = await page.content()
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("Timed out while loading product page.") from exc
        finally:
            await context.close()
            await browser.close()
    return html


async def _scrape_amazon_live(url: str) -> dict[str, Any]:
    """Scrape Amazon using live Playwright DOM queries for maximum reliability."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(user_agent=USER_AGENT, locale="en-US")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # CAPTCHA solving loop
            for _ in range(15):
                html = await page.content()
                if not _is_captcha_page(html):
                    break
                print("CAPTCHA detected... Please solve it in the browser! Waiting 3s...")
                await page.wait_for_timeout(3000)
            
            if _is_captcha_page(await page.content()):
                raise RuntimeError("Scraper blocked by anti-bot challenge (CAPTCHA detected).")

            # Scroll to trigger lazy loading
            await page.evaluate("window.scrollTo(0, 500)")
            await page.wait_for_timeout(1000)

            # Extract title
            title = await page.evaluate("""() => {
                const el = document.querySelector('#productTitle') || document.querySelector('h1#title');
                return el ? el.textContent.trim() : '';
            }""")

            # Extract price
            price = await page.evaluate("""() => {
                const el = document.querySelector('.a-price-whole');
                if (el) return '₹' + el.textContent.trim();
                const el2 = document.querySelector('#priceblock_ourprice');
                return el2 ? el2.textContent.trim() : 'Price unavailable';
            }""")

            # Extract features
            features = await page.evaluate("""() => {
                const items = document.querySelectorAll('#feature-bullets ul li span.a-list-item');
                return Array.from(items).map(x => x.textContent.trim()).filter(x => x.length > 5 && !x.includes('Click here'));
            }""")

            # Extract images - priority: data-a-dynamic-image > data-old-hires > src
            image_urls = await page.evaluate("""() => {
                const urls = [];
                // Primary: landing image with data-a-dynamic-image
                const landing = document.querySelector('#landingImage, #imgBlkFront, .a-dynamic-image');
                if (landing) {
                    const dynAttr = landing.getAttribute('data-a-dynamic-image');
                    if (dynAttr) {
                        try {
                            const dyn = JSON.parse(dynAttr);
                            const keys = Object.keys(dyn);
                            if (keys.length > 0) {
                                // Get highest-res image
                                const best = keys.reduce((a, b) => {
                                    const aSize = dyn[a] ? dyn[a][0] * dyn[a][1] : 0;
                                    const bSize = dyn[b] ? dyn[b][0] * dyn[b][1] : 0;
                                    return aSize > bSize ? a : b;
                                });
                                urls.push(best);
                            }
                        } catch(e) {}
                    }
                    const hires = landing.getAttribute('data-old-hires');
                    if (hires && hires.startsWith('http') && !urls.includes(hires)) urls.push(hires);
                    const src = landing.getAttribute('src');
                    if (src && src.startsWith('http') && src.includes('images/I') && !urls.includes(src)) urls.push(src);
                }
                // Secondary: alt image thumbnails
                const thumbs = document.querySelectorAll('#altImages img, .imageThumbnail img');
                thumbs.forEach(img => {
                    let src = img.getAttribute('src') || '';
                    if (src.includes('images/I') && (src.includes('.jpg') || src.includes('.png'))) {
                        // Upscale thumbnails to full size
                        src = src.replace(/\\._[A-Z0-9,_]+\\./, '._AC_SL1500_.');
                        if (!urls.includes(src)) urls.push(src);
                    }
                });
                return urls.slice(0, 6);
            }""")

        finally:
            await context.close()
            await browser.close()

    return {
        "title": _clean_text(title) or "Untitled Product",
        "price": price or "Price unavailable",
        "features": (features or ["No feature bullets extracted."])[:8],
        "image_urls": image_urls,
        "source_url": url,
    }


def _extract_with_selectors(
    soup: BeautifulSoup, selectors: dict[str, str], source_url: str
) -> dict[str, Any]:
    title_node = soup.select_one(selectors["title"])
    title = _clean_text(title_node.get_text()) if title_node else ""
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title:
            title = _clean_text(og_title.get("content"))

    price_nodes = soup.select(selectors["price"])
    price_text = ""
    for node in price_nodes:
        candidate = _clean_text(node.get_text())
        if re.search(r"[₹$€£]|\d", candidate):
            price_text = _extract_price(candidate)
            break

    features: list[str] = []
    for node in soup.select(selectors["features"]):
        text = _clean_text(node.get_text())
        if text and len(text) > 5:
            features.append(text)
    features = features[:8]

    image_urls: list[str] = []
    for img in soup.select(selectors["images"]):
        src = img.get("data-old-hires") or img.get("src") or img.get("data-src") 
        if img.get("data-a-dynamic-image"):
            import json
            try:
                dyn = json.loads(img.get("data-a-dynamic-image", "{}"))
                if dyn:
                    src = max(dyn.items(), key=lambda x: x[1][0] if isinstance(x[1], list) else 0)[0]
            except Exception:
                pass
        
        if src and src.startswith("http"):
            image_urls.append(src)
        elif src and src.startswith("//"):
            image_urls.append(f"https:{src}")

    # Aggressive fallback for Amazon
    if not image_urls:
        for img in soup.find_all("img"):
            src = img.get("data-old-hires") or img.get("src") or img.get("data-src")
            if img.get("data-a-dynamic-image"):
                import json
                try:
                    dyn = json.loads(img.get("data-a-dynamic-image", "{}"))
                    if dyn:
                        src = max(dyn.items(), key=lambda x: x[1][0] if isinstance(x[1], list) else 0)[0]
                except Exception:
                    pass
            if src and ("images/I" in src) and (".jpg" in src or ".png" in src):
                if "_AC_" in src or "_SX" in src or "_SY" in src or "_SL" in src:
                    image_urls.append(src)

    # Dedup and limit
    unique_urls = []
    for u in image_urls:
        if u not in unique_urls:
            unique_urls.append(u)
    image_urls = unique_urls[:6]

    return {
        "title": title or "Untitled Product",
        "price": price_text or "Price unavailable",
        "features": features or ["No feature bullets extracted."],
        "image_urls": image_urls,
        "source_url": source_url,
    }


async def _scrape_shopify(url: str) -> dict[str, Any]:
    json_url = f"{url.rstrip('/')}.json"
    async with httpx.AsyncClient(
        follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        response = await client.get(json_url, timeout=20.0)
        response.raise_for_status()
        payload = response.json().get("product", {})

    title = _clean_text(payload.get("title"))
    price_raw = payload.get("variants", [{}])[0].get("price", "")
    price = _extract_price(f"${price_raw}" if price_raw and "$" not in str(price_raw) else str(price_raw))

    desc_html = payload.get("body_html", "")
    desc_soup = BeautifulSoup(desc_html, "html.parser")
    features = [
        _clean_text(line)
        for line in desc_soup.get_text("\n").splitlines()
        if _clean_text(line)
    ][:8]

    image_urls = [img.get("src") for img in payload.get("images", []) if img.get("src")][:6]
    return {
        "title": title or "Untitled Product",
        "price": price or "Price unavailable",
        "features": features or ["No feature bullets extracted."],
        "image_urls": image_urls,
        "source_url": url,
    }


def _parse_manual_data(url: str, manual_data: dict[str, Any]) -> dict[str, Any]:
    raw_features = manual_data.get("features") or []
    if isinstance(raw_features, str):
        features = [_clean_text(item) for item in raw_features.split(",") if _clean_text(item)]
    else:
        features = [_clean_text(item) for item in raw_features if _clean_text(str(item))]
    features = features[:8] or ["No feature bullets provided."]

    image_urls = [str(item) for item in manual_data.get("images", []) if str(item).startswith("http")]
    return {
        "title": _clean_text(manual_data.get("title")) or "Manual Product",
        "price": _clean_text(manual_data.get("price")) or "Price unavailable",
        "features": features,
        "image_urls": image_urls[:6],
        "source_url": url,
    }


async def scrape_product(url: str, image_output_dir: Path, manual_data: dict[str, Any] | None = None) -> dict[str, Any]:
    if manual_data:
        product = _parse_manual_data(url, manual_data)
    else:
        platform = detect_platform(url)
        if platform == "shopify":
            try:
                product = await _scrape_shopify(url)
            except Exception:
                html = await _get_html(url)
                product = _extract_with_selectors(BeautifulSoup(html, "html.parser"), SHOPIFY_SELECTORS, url)
        elif platform == "amazon":
            product = await _scrape_amazon_live(url)
        else:
            html = await _get_html(url)
            product = _extract_with_selectors(BeautifulSoup(html, "html.parser"), GENERIC_SELECTORS, url)

    product["images"] = await download_images(product.get("image_urls", []), image_output_dir, max_images=6)
    if not product["images"]:
        raise RuntimeError("No product images could be downloaded. Use manual input fallback.")
    product.pop("image_urls", None)
    return product

