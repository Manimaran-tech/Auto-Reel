---
name: autoreel-analytics
description: Skill for the AI Feedback & Learning Loop. Use this to build the analytics agent that analyzes past video performance (views, watch time, conversions) and dynamically updates the copywriter system prompt with optimized hooking strategies (like storytelling, urgency, or ragebait).
---

# AutoReel Analytics & Learning Loop Skill

## Overview
A static video generation pipeline fails quickly because platforms change and audiences get bored. This skill implements a **Self-Learning Feedback Loop**. 
It tracks the performance of generated videos and uses an AI agent to analyze *why* a video failed or succeeded, feeding those insights back into the prompt that writes the scripts.

## Database Schema (SQLite)
Use `sqlite3` to store lightweight metric data for every generated Reel.

```sql
CREATE TABLE IF NOT EXISTS reel_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_title TEXT,
    hook_type TEXT,            -- e.g., 'question', 'ragebait', 'urgency'
    video_path TEXT,
    views INTEGER DEFAULT 0,
    watch_time_pct REAL DEFAULT 0.0, -- e.g., 85.5 = 85.5% average retention
    link_clicks INTEGER DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_strategy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    current_rule TEXT,         -- The dynamic instruction given to the copywriter
    rationale TEXT,            -- Why the AI decided this rule applies right now
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## The Analytics Agent Logic
Run this pipeline weekly or whenever a batch of N videos finishes.

### Step 1: Metric Ingestion
- Retrieve the past 7 days of data from `reel_metrics`.
- Calculate aggregates: Average retention, average CTR (Clicks/Views), average Conversion Rate (Conversions/Clicks).

### Step 2: The LLM Evaluation Prompt
Feed the raw stats into a reasoning LLM (Ollama / Groq):

```python
def analyze_performance(metrics_data: list[dict]):
    prompt = f"""You are a master digital marketer and algorithm growth expert.
Analyze the performance of these recent Instagram Reels:

{json.dumps(metrics_data, indent=2)}

DIAGNOSIS RULES:
- High Views but Low Watch Time = The video is boring. We need faster pacing or ragebait hooks.
- High Watch Time but Low Clicks = The Call to Action (CTA) is weak. The audience was entertained but didn't buy. We need Urgency hooks.
- Low Views = The visual or text hook in the first 2 seconds failed. We need controversial or highly visual hooks.

YOUR TASK:
Determine what went wrong and produce a single NEW copywriting rule that MUST be followed for the next batch of videos. 
Examples of rules:
- "Ragebait Rule: Start the video by aggressively mocking people who don't own this type of product."
- "Urgency Rule: Emphasize that there are only 5 units left at the current price."
- "Negative Hook Rule: List 3 problems the target audience faces right at the start."

Return ONLY JSON:
{{
   "rationale": "Explanation of why the previous videos failed or succeeded.",
   "new_copywriting_rule": "The exact instruction to append to the Copywriter's prompt."
}}"""
    # Call LLM & extract JSON...
```

### Step 3: Closing the Feedback Loop
1. Save the new strategy rule to the `ai_strategy` table.
2. Update the `copywriter.py` module. When it builds its system prompt, it should query the `ai_strategy` table and append the latest rule:

```python
# In copywriter.py
def build_prompt(product_data, current_strategy_rule):
    return f"""You are an elite direct-response copywriter.
... [Standard instructions] ...

CRITICAL STRATEGY TO APPLY FOR THIS SPECIFIC VIDEO:
{current_strategy_rule}

PRODUCT INFO: ..."""
```

## Frontend Integration
The frontend should feature an `analytics.html` dashboard showing:
1. **Performance Graph:** A Chart.js curve showing Views vs Clicks.
2. **Current AI Brain State:** A card displaying "Currently Optimizing For: [Rationale]".
3. **The Current Strategy:** A display of the `current_rule` so the human operator knows how the AI is thinking right now.

## Benefit Statement for Hackathon Demo
"Most AI tools are blind — they push content into the void and hope it works. AutoReel AI is a closed-loop system. It monitors its own success. If a video gets low watch time, the AI realizes the hook was weak, and automatically shifts its strategy to use high-retention tactics like 'Ragebait' for the next batch. It is a marketer that literally learns from its mistakes."
