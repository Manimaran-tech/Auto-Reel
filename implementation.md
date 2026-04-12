# AutoReel AI — Full End-to-End Implementation Guide

> **Project:** AI Instagram Reel Ads from Product URL  
> **Hackathon:** ACM SIGKDD Atlantis Treasure Hackathon 2025  
> **Constraint:** ZERO paid APIs. ZERO paid resources. Everything free or open-source.  
> **Hardware:** i5 13th Gen H-series, 16GB DDR5 RAM, No GPU.  
> **Timeline:** 1 week.

---

## 1. What We Are Building

An **autonomous AI marketing agent** that takes any e-commerce product URL (Amazon, Shopify, Flipkart, etc.), and outputs a fully-edited, voice-acted, subtitled Instagram Reel video — ready to post.

### The End-to-End Pipeline

```
[Product URL] → [Scraper] → [Copywriter (Self-Taught)] → [Voice] → [Video] → [Instagram] → [Analytics/Learning Loop]
```

**Input:** A product URL (e.g., `https://amazon.in/dp/B0XXXXX`)  
**Output:** A 15-30 second `.mp4` video file with:
- High-res product visuals with cinematic zoom effects
- AI-generated voiceover narrating a viral marketing script
- TikTok/Reels-style animated subtitles burned into the video
- Auto-generated caption with hashtags
- Optionally pushed to Instagram Drafts via UI automation

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        AutoReel AI                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STAGE 1: SCRAPER                                                │
│  ├── Input: Product URL                                          │
│  ├── Tool: Playwright + BeautifulSoup                            │
│  ├── Output: product_data.json                                   │
│  │   ├── title (str)                                             │
│  │   ├── price (str)                                             │
│  │   ├── features (list[str])                                    │
│  │   ├── images (list[str] → downloaded to /tmp/images/)         │
│  │   └── source_url (str)                                        │
│  └── Fallback: If anti-bot blocks scraping, use a manual         │
│      JSON input mode where user pastes product details.          │
│                                                                  │
│  STAGE 2: AI COPYWRITER                                          │
│  ├── Input: product_data.json                                    │
│  ├── Tool: Ollama (local LLM — Llama 3.2 3B or Mistral 7B)      │
│  │   OR Groq API free tier (if internet available)               │
│  ├── Prompt: "Write a 15-second viral Instagram Reel script      │
│  │   for this product. Hook the viewer in 3 seconds.             │
│  │   Mention the price. Be energetic and persuasive."            │
│  ├── Output: script.txt (the narration text)                     │
│  └── Also generates: caption.txt (Instagram post caption         │
│      with emojis and hashtags)                                   │
│                                                                  │
│  STAGE 3: VOICE ENGINE                                           │
│  ├── Input: script.txt                                           │
│  ├── Tool: edge-tts (Python library)                             │
│  │   Uses Microsoft Edge's built-in neural TTS voices            │
│  │   NO API key. NO paid subscription. FREE.                     │
│  ├── Voice: en-US-ChristopherNeural (male) or                    │
│  │          en-US-JennyNeural (female) or                        │
│  │          en-IN-NeerjaNeural (Indian English)                  │
│  ├── Output: voiceover.mp3                                       │
│  └── Also outputs: subtitles.vtt (word-level timestamps          │
│      for subtitle synchronization)                               │
│                                                                  │
│  STAGE 4: VIDEO RENDERER                                         │
│  ├── Input: images[], voiceover.mp3, subtitles.vtt               │
│  ├── Tool: MoviePy (Python video editing library)                │
│  ├── Process:                                                    │
│  │   1. Load product images                                      │
│  │   2. Resize to 1080x1920 (Instagram Reel vertical format)     │
│  │   3. Apply Ken Burns effect (slow zoom in/out on each image)  │
│  │   4. Calculate duration per image = total_audio / num_images   │
│  │   5. Concatenate image clips sequentially                     │
│  │   6. Overlay voiceover.mp3 as audio track                     │
│  │   7. Burn subtitles (word-by-word or line-by-line) onto video │
│  │   8. Add background music (royalty-free, bundled with app)     │
│  │   9. Export as final_reel.mp4 (H.264, 30fps)                  │
│  ├── Output: final_reel.mp4                                      │
│  └── Estimated render time: 15-30 seconds on i5 CPU              │
│                                                                  │
│  STAGE 5: DISTRIBUTION (UI AUTOMATION)                           │
│  ├── Input: final_reel.mp4, caption.txt                          │
│  ├── Tool: Playwright (browser automation)                       │
│  ├── Process:                                                    │
│  │   1. Open Chrome → Navigate to instagram.com                  │
│  │   2. Log in (credentials from .env file)                      │
│  │   3. Click "+" (Create) button                                │
│  │   4. Upload final_reel.mp4                                    │
│  │   5. Paste caption from caption.txt                           │
│  │   6. Click "Save as Draft" (NOT "Post")                       │
│  ├── Output: Video saved in Instagram Drafts                     │
│  └── Why Drafts? Instagram's algorithm flags and shadowbans      │
│      content posted via automation/API. By saving to Drafts,     │
│      the human posts manually → organic reach preserved.         │
│                                                                  │
│  STAGE 6: ANALYTICS & LEARNING (THE FEEDBACK LOOP)               │
│  ├── Input: Reel metrics (Views, Watch Time, Clicks to Shopify)  │
│  ├── Tool: SQLite + Ollama (Analytics Agent)                     │
│  ├── Process:                                                    │
│  │   1. Monitor weekly growth metrics via dashboard              │
│  │   2. AI analyzes which "hooks" (e.g. Ragebait vs Story) worked│
│  │   3. Generates a "Trend Strategy Report"                      │
│  │   4. Feeds insights back into the AI Copywriter's system      │
│  │      prompt to permanently improve future video scripts       │
│  └── Output: Evolving, conversion-optimized marketing strategies │
│                                                                  │
│  FRONTEND (Web Dashboard)                                        │
│  ├── Tool: HTML + CSS + JavaScript (vanilla)                     │
│  ├── Served by: FastAPI (Python backend)                         │
│  ├── Features:                                                   │
│  │   ├── URL input field                                         │
│  │   ├── Real-time pipeline progress indicator                   │
│  │   ├── Video preview player (shows final_reel.mp4)             │
│  │   ├── Caption preview + copy button                           │
│  │   ├── "Push to Instagram Draft" button                        │
│  │   └── Download button for the .mp4                            │
│  └── Design: Premium dark theme, glassmorphism, smooth anims     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Project File Structure

```
d:\Hackathon\
├── implementation.md          ← This file
├── AutoReel_PPT_Content.txt   ← Presentation content
├── .agents/
│   └── workflows/
│       └── autoreel-build.md  ← Build workflow
├── backend/
│   ├── main.py                ← FastAPI application entry point
│   ├── requirements.txt       ← Python dependencies
│   ├── config.py              ← Configuration (voices, models, paths)
│   ├── scraper.py             ← Stage 1: Product URL scraper
│   ├── copywriter.py          ← Stage 2: LLM script generator
│   ├── voice_engine.py        ← Stage 3: edge-tts voiceover
│   ├── video_renderer.py      ← Stage 4: MoviePy video assembly
│   ├── distributor.py         ← Stage 5: Playwright Instagram automation
│   ├── analytics.py           ← Stage 6: Learning & trend analysis engine
│   └── pipeline.py            ← Orchestrator (chains all stages)
├── data/
│   └── analytics.db           ← SQLite database storing reel metrics
├── frontend/
│   ├── index.html             ← Main dashboard page
│   ├── analytics.html         ← Analytics & Growth dashboard
│   ├── styles.css             ← Premium dark theme styling
│   └── app.js                 ← Frontend logic (API calls, progress)
├── assets/
│   ├── fonts/                 ← Bundled fonts for subtitles (e.g., Montserrat Bold)
│   └── music/                 ← Royalty-free background music clips
└── output/                    ← Generated videos land here
    └── .gitkeep
```

---

## 4. Technology Stack (ALL FREE)

| # | Component | Library/Tool | Cost | Install Command |
|---|-----------|-------------|------|-----------------|
| 1 | Web Scraping | `playwright`, `beautifulsoup4` | Free | `pip install playwright beautifulsoup4` then `playwright install chromium` |
| 2 | LLM (Script Writer) | `ollama` (local) | Free | Install from ollama.com, then `ollama pull llama3.2:3b` |
| 3 | LLM (Fallback) | `groq` API (free tier) | Free | `pip install groq` (optional, needs free API key from groq.com) |
| 4 | Text-to-Speech | `edge-tts` | Free | `pip install edge-tts` |
| 5 | Video Rendering | `moviepy` | Free | `pip install moviepy` |
| 6 | Image Processing | `Pillow` | Free | `pip install Pillow` |
| 7 | Subtitle Timing | `edge-tts` built-in word boundaries | Free | (included with edge-tts) |
| 8 | Backend Server | `fastapi`, `uvicorn` | Free | `pip install fastapi uvicorn[standard]` |
| 9 | Browser Automation | `playwright` | Free | (same as #1) |
| 10 | Video Codec | `FFmpeg` | Free | Must be installed system-wide: `winget install ffmpeg` |

---

## 5. Stage-by-Stage Implementation Details

### Stage 1: Scraper (`backend/scraper.py`)

**Purpose:** Accept any e-commerce URL and extract product data.

**Approach:**
- Use `playwright` to load the page in a headless browser (handles JavaScript-rendered pages).
- Extract:
  - `title`: The product name from the page `<title>` or `<h1>`.
  - `price`: Look for price patterns (₹, $, etc.) in common CSS selectors.
  - `features`: Extract bullet points from the product description section.
  - `images`: Download the top 3-5 high-resolution product images.
- For Amazon: Target selectors like `#productTitle`, `.a-price-whole`, `#feature-bullets li`, `#imgTagWrapperId img`.
- For Shopify: Target selectors like `.product-title`, `.product__price`, `.product__description`, `.product__media img`.
- **Fallback:** If scraping fails (anti-bot), accept manual JSON input from the user via the dashboard.

**Output:** A Python dict / JSON:
```json
{
  "title": "Sony WH-1000XM5 Headphones",
  "price": "₹24,990",
  "features": ["Industry-leading noise cancellation", "30-hour battery", "Speak-to-chat"],
  "images": ["output/images/img_1.jpg", "output/images/img_2.jpg", "output/images/img_3.jpg"],
  "source_url": "https://amazon.in/dp/..."
}
```

---

### Stage 2: AI Copywriter (`backend/copywriter.py`)

**Purpose:** Generate a viral, high-retention 15-second Reel script from product data.

**Approach:**
- Connect to Ollama's local REST API at `http://localhost:11434/api/generate`.
- Model: `llama3.2:3b` (fast on CPU, ~2.5GB RAM).
- System prompt establishes the "viral content creator" persona.
- User prompt passes in the product title, price, and features.
- Request both a `script` (voiceover text) and a `caption` (Instagram post text with hashtags).

**Prompt Template:**
```
You are a world-class direct-response marketing copywriter who specializes in viral TikTok and Instagram Reel scripts.

Product: {title}
Price: {price}
Features: {features}

Write a 15-second Instagram Reel script for this product.
Rules:
- The first sentence MUST be a bold hook that stops the scroll (question or shocking statement).
- Mention the price.
- End with a clear call-to-action.
- Keep it between 40-60 words total (15 seconds of speech).
- Use short, punchy sentences.

Also write an Instagram caption (max 150 words) with 5 relevant hashtags.

Output as JSON:
{"script": "...", "caption": "..."}
```

**Fallback:** If Ollama is not running, try Groq API (free tier, needs `GROQ_API_KEY` in `.env`).

---

### Stage 3: Voice Engine (`backend/voice_engine.py`)

**Purpose:** Convert the script text into a high-quality, human-sounding voiceover audio file.

**Approach:**
- Use `edge-tts` Python library.
- This library accesses the same neural TTS engine built into Microsoft Edge browser.
- It produces incredibly natural-sounding speech — far superior to typical robotic TTS.
- **Key feature:** `edge-tts` can output **word-level timestamps** (SubMaker), which we will use in Stage 4 for subtitle synchronization.

**Implementation:**
```python
import edge_tts
import asyncio

async def generate_voice(text: str, output_path: str, voice: str = "en-US-ChristopherNeural"):
    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
    # Save word-level subtitle timestamps
    subs = submaker.generate_subs()
    with open(output_path.replace(".mp3", ".vtt"), "w") as f:
        f.write(subs)
    return output_path
```

**Available voices (all free):**
- `en-US-ChristopherNeural` — Deep male (great for tech products)
- `en-US-JennyNeural` — Female (great for lifestyle products)
- `en-IN-NeerjaNeural` — Indian English female
- `en-IN-PrabhatNeural` — Indian English male

---

### Stage 4: Video Renderer (`backend/video_renderer.py`)

**Purpose:** Combine images + voiceover + subtitles into a polished Instagram Reel `.mp4`.

**This is the hardest and most technically impressive stage.**

**Approach:**
1. **Canvas:** Create a 1080x1920 (9:16) vertical video canvas (Instagram Reel format).
2. **Image Processing (Pillow):**
   - Load each product image.
   - Resize/crop to fill the 1080x1920 frame (center-crop or fit with blur background).
   - Apply a slight color grading (warm filter or cool filter) for aesthetic consistency.
3. **Ken Burns Effect (MoviePy):**
   - For each image, create a video clip that slowly zooms in (1.0x → 1.15x scale over N seconds).
   - This transforms a static image into what looks like cinematic footage.
   - Alternate between zoom-in and zoom-out for visual variety.
4. **Duration Sync:**
   - Get the total duration of `voiceover.mp3` using MoviePy.
   - Divide total duration equally among the product images.
   - Example: 15-second audio / 3 images = 5 seconds per image.
5. **Audio Overlay:**
   - Set the voiceover as the primary audio track.
   - Optionally mix in a royalty-free background music track at 15% volume.
6. **Subtitle Rendering:**
   - Parse the `.vtt` file from Stage 3 to get word timestamps.
   - For each group of 3-5 words, create a TextClip positioned center-bottom.
   - Style: Bold white text, black outline, large font (48-64px).
   - This creates the recognizable "TikTok subtitle" look.
7. **Transitions:**
   - Add a brief crossfade (0.3s) between image clips for smooth transitions.
8. **Export:**
   - Render to `output/final_reel.mp4` using H.264 codec, 30fps.
   - Target file size: < 50MB (Instagram limit for Reels).

**Performance:** On an i5 13th Gen CPU, rendering a 15-second 1080x1920 video with MoviePy takes approximately 20-40 seconds. This is acceptable for a demo.

---

### Stage 5: Distribution (`backend/distributor.py`)

**Purpose:** Automate uploading the finished video to Instagram Drafts.

**Approach:**
- Use `playwright` to control a Chromium browser.
- Navigate to `https://www.instagram.com/`.
- Log in using credentials stored in a `.env` file.
- Click the "Create" (+) button.
- Select "Reel" upload option.
- Upload the `final_reel.mp4` file.
- Paste the auto-generated caption from Stage 2.
- Save as **Draft** (NOT post directly — to avoid algorithm penalties).

**Important Notes:**
- Instagram's web interface supports Reel uploads as of 2024.
- The automation mimics human behavior (click delays, natural scrolling).
- We do NOT post automatically. The human reviews the draft and posts manually.
- This keeps the content's organic reach intact.

**Security:**
- Instagram credentials are stored in `.env` (never committed to git).
- The `.env` file is loaded using `python-dotenv`.

---

### Stage 6: Analytics & Learning Loop (`backend/analytics.py`)

**Purpose:** Ensure the AI doesn't just make generic videos, but learns from what actually drives sales (Watch time, Clicks, Conversions) and adjusts its hook strategies (e.g., employing specific tropes like ragebait or urgency).

**Approach:**
1. **Data Collection:** Store metrics for every generated reel in `data/analytics.db` (SQLite). 
2. **Analysis Agent:** A secondary LLM agent reads the weekly metrics table. 
3. **Evaluation Logic:**
   - If a video had high views but low clicks: "The hook worked, but the Call-to-Action failed."
   - If a video had low watch time: "The hook was weak. Try a controversial/ragebait hook next."
4. **The Feedback Loop:** The Analytics Agent generates a "Strategy String" (e.g., *Rule: Start every script by insulting the viewer's current product*). This string is dynamically prepended to the Stage 2 Copywriter's system prompt for the next batch of videos.

---

## 6. Frontend Dashboard (`frontend/`)

**Design:** Premium dark theme with glassmorphism effects, inspired by modern SaaS dashboards.

**Features:**
1. **URL Input Bar** — Paste any product link, click "Generate Reel".
2. **Pipeline Progress** — Shows real-time progress through the stages.
3. **Video Preview** — Embedded HTML5 video player.
4. **Action Buttons** — Download MP4, Push to Drafts.
5. **Growth Dashboard (`analytics.html`)**:
   - Chart/Graph showing last 7 days of Reel engagement vs Sales.
   - "Current AI Strategy" card (showing what the AI is currently experimenting with, e.g. "Testing Urgency hooks").

---

## 7. API Endpoints (FastAPI)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/generate` | Accepts URL, triggers full pipeline, returns video path |
| `GET` | `/api/status/{job_id}` | Returns current pipeline stage and progress |
| `GET` | `/api/video/{job_id}` | Serves the final video file for preview/download |
| `POST` | `/api/distribute/{job_id}` | Triggers Instagram Draft upload |
| `GET` | `/api/analytics` | Returns weekly performance trends and current AI hook strategy |
| `POST` | `/api/analytics/ingest`| Accept manual or automated metric inputs (views, clicks) |
| `GET` | `/` | Serves the frontend main dashboard |

---

## 8. Environment Variables (`.env`)

```env
# LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# Groq Fallback (optional)
GROQ_API_KEY=gsk_xxxxx

# Voice Configuration
TTS_VOICE=en-US-ChristopherNeural

# Instagram (for distribution stage only)
INSTAGRAM_USERNAME=your_username
INSTAGRAM_PASSWORD=your_password

# Paths
OUTPUT_DIR=./output
ASSETS_DIR=./assets
```

---

## 9. Execution Order (How to Run)

```bash
# 1. Install system dependencies
winget install ffmpeg

# 2. Install Ollama and pull the model
# Download from ollama.com, then:
ollama pull llama3.2:3b

# 3. Set up Python environment
cd d:\Hackathon
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
playwright install chromium

# 4. Create .env file with your configuration

# 5. Start the backend server
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 6. Open browser to http://localhost:8000
# 7. Paste a product URL and click "Generate Reel"
```

---

## 10. Demo Flow (During Hackathon Presentation)

1. Open the AutoReel AI dashboard in browser.
2. Paste a live Amazon/Shopify product URL on screen.
3. Click "Generate Reel" — audience watches the pipeline progress in real-time.
4. ~30-45 seconds later, the finished video plays in the browser.
5. Click "Push to Instagram Drafts" — audience sees the browser automation happen live.
6. Switch to Instagram app on phone — show the video sitting in Drafts.
7. Optionally show a Shopify store page as proof of concept for sales attribution.

---

## 11. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Amazon blocks scraping | Support Shopify URLs as primary; manual JSON input as fallback |
| Ollama too slow on CPU | Pre-generate scripts for demo products; cache results |
| MoviePy rendering slow | Pre-render 2-3 demo videos before presentation; live-generate only 1 |
| Instagram UI changes | Keep Playwright selectors updated; have manual upload as fallback |
| WiFi unavailable | Ollama + edge-tts both work offline; only Instagram upload needs WiFi |
