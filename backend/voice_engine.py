from __future__ import annotations

import json
from pathlib import Path

import edge_tts
from moviepy import AudioFileClip, concatenate_audioclips

from .config import settings

SPEAKER_CONFIGS = {
    "peter": {
        "tts_voice": "en-US-GuyNeural",
        "pitch": "-5Hz",
        "model_dir": "models/voices/peter"
    },
    "stewie": {
        "tts_voice": "en-GB-RyanNeural",
        "pitch": "+10Hz",
        "model_dir": "models/voices/stewie"
    }
}

async def generate_single_voiceover(
    text: str,
    output_audio_path: Path,
    output_subs_path: Path,
    voice: str = "en-US-GuyNeural",
    rate: str = "+10%",
    pitch: str = "+0Hz",
) -> float:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    submaker = edge_tts.SubMaker()
    with output_audio_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)
    output_subs_path.write_text(submaker.get_srt(), encoding="utf-8")
    try:
        clip = AudioFileClip(str(output_audio_path))
        duration = float(clip.duration)
        clip.close()
        return duration
    except Exception:
        return 0.0

async def generate_dialogue_voiceover(
    dialogue: list[dict],
    output_audio_path: Path,
    output_subs_path: Path,
) -> float:
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    output_subs_path.parent.mkdir(parents=True, exist_ok=True)

    # Try loading RVC with the real API
    rvc = None
    try:
        from rvc_python.infer import RVCInference
        models_dir = str(Path.cwd() / "models" / "voices")
        rvc = RVCInference(models_dir=models_dir, device="cuda:0")
        print(f"✅ RVC loaded! Available voice models: {rvc.list_models()}")
    except Exception as e:
        print(f"⚠️ RVC not available ({e}). Falling back to base edge-tts.")
        rvc = None

    master_words = []
    audio_clips = []
    current_time = 0.0
    last_loaded_model = None

    # Clean .temp to prevent stale file conflicts
    import shutil
    temp_dir = Path(".temp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for i, line in enumerate(dialogue):
        speaker = line.get("speaker", "peter")
        text = line.get("text", "")
        cfg = SPEAKER_CONFIGS.get(speaker, SPEAKER_CONFIGS["peter"])

        temp_audio = Path(f".temp/turn_{i}.mp3")
        temp_subs = Path(f".temp/turn_{i}.srt")

        # Retry edge-tts up to 3 times if it produces corrupt/empty audio
        for attempt in range(3):
            dur = await generate_single_voiceover(
                text, temp_audio, temp_subs, voice=cfg["tts_voice"], pitch=cfg["pitch"]
            )
            if temp_audio.exists() and temp_audio.stat().st_size > 1000:
                break
            print(f"  ⚠️ edge-tts attempt {attempt+1} produced invalid audio for turn {i}, retrying...")
            await asyncio.sleep(0.5)

        if not temp_audio.exists() or temp_audio.stat().st_size < 1000:
            print(f"  ❌ Skipping turn {i} — could not generate valid audio")
            continue

        # Apply RVC voice conversion if available
        if rvc and speaker in rvc.list_models():
            if last_loaded_model != speaker:
                rvc.load_model(speaker)
                rvc.set_params(f0method="rmvpe", protect=0.33)
                last_loaded_model = speaker
            # Convert mp3 to wav first (RVC needs wav input)
            wav_input = Path(f".temp/turn_{i}_input.wav")
            try:
                from pydub import AudioSegment
                sound = AudioSegment.from_mp3(str(temp_audio))
                sound = sound.set_frame_rate(16000).set_channels(1)
                sound.export(str(wav_input), format="wav")
            except ImportError:
                # fallback: use moviepy to convert
                tmp_clip = AudioFileClip(str(temp_audio))
                tmp_clip.write_audiofile(str(wav_input), fps=16000, nbytes=2, codec="pcm_s16le", logger=None)
                tmp_clip.close()
            
            rvc_output = Path(f".temp/rvc_{i}.wav")
            try:
                rvc.infer_file(str(wav_input), str(rvc_output))
                if rvc_output.exists() and rvc_output.stat().st_size > 1000:
                    print(f"  🎤 RVC converted turn {i} ({speaker})")
                    temp_audio.unlink(missing_ok=True)
                    wav_input.unlink(missing_ok=True)
                    temp_audio = rvc_output
                else:
                    print(f"  ⚠️ RVC output too small for turn {i}, using base edge-tts")
            except Exception as e:
                print(f"  ⚠️ RVC conversion failed for turn {i}: {e}")

        try:
            aclip = AudioFileClip(str(temp_audio))
        except Exception as e:
            print(f"  ❌ Could not load audio for turn {i}: {e}, skipping")
            continue
        audio_clips.append(aclip)

        words = parse_vtt(temp_subs)
        for w in words:
            w["start"] += current_time
            w["end"] += current_time
            w["speaker"] = speaker
        
        master_words.extend(words)
        current_time += aclip.duration

    if not audio_clips:
        raise ValueError("No audio was generated from the dialogue!")

    final_audio = concatenate_audioclips(audio_clips)
    final_audio.write_audiofile(str(output_audio_path), fps=44100, logger=None)
    final_audio.close()
    for ac in audio_clips:
        ac.close()

    output_subs_path.write_text(json.dumps(master_words, indent=2), encoding="utf-8")
    
    return current_time

def vtt_timestamp_to_seconds(ts: str) -> float:
    ts = ts.replace(",", ".")
    hours, minutes, seconds = ts.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

def parse_vtt(vtt_path: Path) -> list[dict]:
    content = vtt_path.read_text(encoding="utf-8")
    blocks = []
    for chunk in content.strip().split("\n\n"):
        lines = chunk.split("\n", 2)
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
            time_per_word = (end_sec - start_sec) / len(words)
            for i, word in enumerate(words):
                entries.append({
                    "start": start_sec + (i * time_per_word),
                    "end": start_sec + ((i + 1) * time_per_word),
                    "text": word.strip(",."),
                })
        except Exception:
            pass
    return entries

def group_words(entries: list[dict], words_per_group: int = 4) -> list[dict]:
    if not entries:
        return []
    groups = []
    for index in range(0, len(entries), words_per_group):
        chunk = entries[index : index + words_per_group]
        groups.append({
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "text": " ".join(item["text"] for item in chunk),
        })
    return groups

