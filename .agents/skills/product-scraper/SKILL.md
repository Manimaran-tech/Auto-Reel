---
name: autoreel-scraper
description: Skill for building the product URL scraper. Use this when implementing the web scraping pipeline that extracts product data (title, price, features, images) from e-commerce URLs like Amazon and Shopify product pages.
---

# AutoReel Product Scraper Skill

## Overview
Extracts product data from any e-commerce URL using Playwright (headless browser) and BeautifulSoup (HTML parsing). Returns structured JSON with title, price, features, and downloaded images.

## Supported Platforms
- **Amazon** (.amazon.in, .amazon.com)
- **Shopify** (any Shopify-powered store)
- **Flipkart** (.flipkart.com)
- **Generic** (fallback using Open Graph meta tags)

## Amazon Selectors
```python
AMAZON_SELECTORS = {
    "title": "#productTitle",
    "price": ".a-price-whole",
    "features": "#feature-bullets ul li span.a-list-item",
    "images": "#imgTagWrapperId img, #altImages img",
    "rating": "#acrPopover span.a-size-base",
}
```

## Shopify Selectors
```python
# Shopify stores expose product data as JSON in a script tag
# The fastest, most reliable method:
SHOPIFY_JSON_URL = "{product_url}.json"
# This returns full product data including images, variants, price, description.
```

## Implementation Pattern
```python
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json, os, httpx

async def scrape_product(url: str) -> dict:
    """Scrape product data from a URL."""

    # Detect platform
    if "amazon" in url:
        return await scrape_amazon(url)
    elif is_shopify(url):
        return await scrape_shopify(url)
    else:
        return await scrape_generic(url)

async def scrape_shopify(url: str) -> dict:
    """Shopify stores expose a JSON API at {url}.json"""
    json_url = url.rstrip("/") + ".json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(json_url)
        data = resp.json()["product"]
    return {
        "title": data["title"],
        "price": data["variants"][0]["price"],
        "features": [data["body_html"]],  # Parse HTML to extract text
        "images": [img["src"] for img in data["images"][:5]],
        "source_url": url,
    }

async def scrape_amazon(url: str) -> dict:
    """Use Playwright to render the Amazon page, then parse with BeautifulSoup."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    # ... extract using AMAZON_SELECTORS
```

## Image Downloading
- Download images in parallel using `httpx.AsyncClient`.
- Save to `output/images/img_1.jpg`, `img_2.jpg`, etc.
- Prefer the highest resolution available.
- For Amazon, replace thumbnail URLs: change `._AC_SX38_` to `._AC_SL1500_` for full-res.

## Anti-Bot Mitigation
- Set a realistic User-Agent header.
- Add random delays between actions (1-3 seconds).
- If CAPTCHA is detected, fall back to manual input mode.
- For hackathon demo: pre-scrape 2-3 products as cached JSON fallbacks.

## Fallback: Manual Input
If scraping fails, the frontend should show a form where the user can manually enter:
- Product title
- Price
- Key features (comma-separated)
- Upload images from their computer

## Guidelines
- Always handle network errors and timeouts gracefully.
- Limit to 5 images maximum per product.
- Strip HTML tags from descriptions using BeautifulSoup's `.get_text()`.
- Normalize prices to include currency symbol.
