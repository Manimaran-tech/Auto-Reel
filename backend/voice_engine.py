from __future__ import annotations

import re
from pathlib import Path

import edge_tts
from moviepy import AudioFileClip

from .config import settings


async def generate_voiceover(
    text: str,
    output_audio_path: Path,
    output_subs_path: Path,
    voice: str | None = None,
    rate: str = "+10%",
    pitch: str = "+0Hz",
) -> float:
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    output_subs_path.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(text, voice or settings.tts_voice, rate=rate, pitch=pitch)
    submaker = edge_tts.SubMaker()

    with output_audio_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)

    subs_content = submaker.get_srt()
    output_subs_path.write_text(subs_content, encoding="utf-8")

    clip = AudioFileClip(str(output_audio_path))
    duration = float(clip.duration)
    clip.close()
    return duration


def vtt_timestamp_to_seconds(ts: str) -> float:
    ts = ts.replace(",", ".")
    hours, minutes, seconds = ts.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_vtt(vtt_path: Path) -> list[dict]:
    content = vtt_path.read_text(encoding="utf-8")
    blocks = []
    
    # Parse SRT blocks robustly
    for chunk in content.strip().split("\n\n"):
        lines = chunk.split("\n", 2)  # index, timestamps, text
        if len(lines) >= 3 and "-->" in lines[1]:
            start, end = lines[1].split("-->")
            text = lines[2].replace("\n", " ").strip()
            blocks.append((start.strip(), end.strip(), text))

    entries = []
    for start, end, text in blocks:
        try:
            start_sec = vtt_timestamp_to_seconds(start)
            end_sec = vtt_timestamp_to_seconds(end)
            words = text.split()
            if not words:
                continue
            
            # Linearly interpolate timestamps to restore Word-by-Word kinetic typography
            time_per_word = (end_sec - start_sec) / len(words)
            for i, word in enumerate(words):
                entries.append(
                    {
                        "start": start_sec + (i * time_per_word),
                        "end": start_sec + ((i + 1) * time_per_word),
                        "text": word.strip(",."),
                    }
                )
        except Exception as exc:
            print(f"Error parsing subtitle block: {exc}")
            
    return entries


def group_words(entries: list[dict], words_per_group: int = 4) -> list[dict]:
    if not entries:
        return []
    groups = []
    for index in range(0, len(entries), words_per_group):
        chunk = entries[index : index + words_per_group]
        groups.append(
            {
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "text": " ".join(item["text"] for item in chunk),
            }
        )
    return groups

