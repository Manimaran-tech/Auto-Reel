---
name: autoreel-voice-engine
description: Skill for generating AI voiceovers using edge-tts. Use this when implementing the text-to-speech pipeline that converts a marketing script into a human-sounding MP3 audio file with word-level subtitle timestamps.
---

# AutoReel Voice Engine Skill

## Overview
Uses `edge-tts`, a free Python library that leverages Microsoft Edge's built-in neural text-to-speech engine to generate high-quality voiceovers. No API key required. No paid subscription. Works offline after first use.

## Installation
```bash
pip install edge-tts
```

## Available Voices (Best for Marketing Content)
| Voice ID | Gender | Accent | Best For |
|----------|--------|--------|----------|
| `en-US-ChristopherNeural` | Male | American | Tech, gadgets |
| `en-US-GuyNeural` | Male | American | Authoritative, deep |
| `en-US-JennyNeural` | Female | American | Lifestyle, beauty |
| `en-US-AriaNeural` | Female | American | Energetic, youthful |
| `en-IN-NeerjaNeural` | Female | Indian | Indian market products |
| `en-IN-PrabhatNeural` | Male | Indian | Indian market products |

## Core Implementation
```python
import edge_tts
import asyncio

async def generate_voiceover(
    text: str,
    output_audio_path: str,
    output_subs_path: str,
    voice: str = "en-US-ChristopherNeural",
    rate: str = "+10%",    # Slightly faster for Reels pace
    pitch: str = "+0Hz",
) -> float:
    """
    Generate voiceover audio and word-level subtitles.

    Returns: duration of the audio in seconds.
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    submaker = edge_tts.SubMaker()

    with open(output_audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    # Generate WebVTT subtitle file with word-level timestamps
    subs_content = submaker.generate_subs()
    with open(output_subs_path, "w", encoding="utf-8") as subs_file:
        subs_file.write(subs_content)

    # Get audio duration
    from moviepy import AudioFileClip
    audio = AudioFileClip(output_audio_path)
    duration = audio.duration
    audio.close()

    return duration
```

## Parsing Word-Level Subtitles from VTT
The `.vtt` file from `edge-tts` contains timestamps per word. Parse these to create grouped subtitle chunks for the video:

```python
import re

def parse_vtt(vtt_path: str) -> list[dict]:
    """Parse VTT file into a list of {start, end, text} entries."""
    entries = []
    with open(vtt_path, "r") as f:
        content = f.read()

    # Pattern matches: 00:00:00.000 --> 00:00:01.000
    blocks = re.findall(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\n(.+)",
        content,
    )
    for start, end, text in blocks:
        entries.append({
            "start": vtt_timestamp_to_seconds(start),
            "end": vtt_timestamp_to_seconds(end),
            "text": text.strip(),
        })
    return entries

def vtt_timestamp_to_seconds(ts: str) -> float:
    """Convert 00:00:01.500 to 1.5"""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

def group_words(entries: list[dict], words_per_group: int = 4) -> list[dict]:
    """Group individual words into subtitle chunks of N words."""
    groups = []
    for i in range(0, len(entries), words_per_group):
        chunk = entries[i : i + words_per_group]
        groups.append({
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "text": " ".join(e["text"] for e in chunk),
        })
    return groups
```

## Guidelines
- Use `rate="+10%"` for a slightly faster, more energetic delivery (better for Reels).
- For dramatic products, use `rate="-5%"` for a slower, more authoritative tone.
- Always generate the `.vtt` subtitle file — it's critical for Stage 4 (video rendering).
- The `edge-tts` library is async — always use `asyncio.run()` or an async context when calling it.
- First run downloads voice data from Microsoft servers (~50MB). After that, it works offline.
