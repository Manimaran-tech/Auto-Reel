"""Video Renderer — composites Family Guy avatars over Minecraft gameplay with subtitles."""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    VideoFileClip,
    ImageClip,
    vfx
)

TARGET_SIZE = (720, 1280)

def _create_gradient_overlay(target_size: tuple[int, int] = TARGET_SIZE, height_pct: float = 0.6) -> np.ndarray:
    w, h = target_size
    gradient_h = int(h * height_pct)
    gradient = np.zeros((gradient_h, w, 4), dtype=np.uint8)
    for y in range(gradient_h):
        alpha = int(180 * (y / gradient_h))
        gradient[y, :] = [0, 0, 0, alpha]
    return gradient

def _render_text_pil(
    text: str,
    font_path: str | None = None,
    font_size: int = 52,
    color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 4,
) -> np.ndarray:
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    display_text = text.upper()
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), display_text, font=font, stroke_width=stroke_width)
    text_w = bbox[2] - bbox[0] + stroke_width * 2 + 10
    text_h = bbox[3] - bbox[1] + stroke_width * 2 + 10
    img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = (text_w - (bbox[2] - bbox[0])) // 2
    y = (text_h - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), display_text, font=font, fill=color, stroke_fill=stroke_color, stroke_width=stroke_width)
    return np.array(img)

def _text_clip(text: str, start: float, end: float, font_path: str | None = None, color: str = "yellow", target_size: tuple[int, int] = TARGET_SIZE) -> ImageClip:
    text_img = _render_text_pil(text, font_path=font_path, font_size=60, color=color, stroke_color="black", stroke_width=5)
    clip = ImageClip(text_img).with_duration(end - start)
    y_pos = int(target_size[1] * 0.70)
    return clip.with_start(start).with_end(end).with_position(("center", y_pos))

def _pick_background_music(music_dir: Path) -> Path | None:
    if not music_dir.exists(): return None
    for c in music_dir.iterdir():
        if c.suffix.lower() in {".mp3", ".wav", ".m4a"}: return c
    return None

def _find_font(fonts_dir: Path) -> str | None:
    if not fonts_dir.exists(): return None
    for c in fonts_dir.iterdir():
        if c.suffix.lower() in {".ttf", ".otf"}: return str(c)
    return None

def get_bouncing_avatar(image_path: str | Path, start: float, end: float, y_pos: int, target_size: tuple[int, int]) -> ImageClip:
    # Pre-resize with PIL — normalize to consistent HEIGHT so all characters look the same size
    img = Image.open(str(image_path)).convert("RGBA")
    w, h = img.size
    target_h = 450  # consistent character height
    scale = target_h / h
    new_size = (int(w * scale), int(h * scale))
    img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    clip = ImageClip(np.array(img)).with_duration(end - start).with_start(start)
    
    def pop_in(t):
        """Single entrance bounce — drops in and settles."""
        if t < 0.3:
            # Drop from above: lerp from -200 to y_pos with overshoot
            progress = t / 0.3
            ease = 1 - (1 - progress) ** 3  # cubic ease-out
            y = -200 + (y_pos + 20) * ease  # overshoot by 20px
        elif t < 0.45:
            # Settle: bounce back from overshoot
            progress = (t - 0.3) / 0.15
            y = (y_pos + 20) - 20 * progress  # settle to final y_pos
        else:
            y = y_pos
        return ("center", y)

    return clip.with_position(pop_in)

def _pick_random_png(directory: str | Path) -> Path:
    """Pick a random PNG from a directory. Falls back to the path itself if it's a file."""
    p = Path(directory)
    if p.is_file():
        return p
    pngs = list(p.glob("*.png"))
    if not pngs:
        raise FileNotFoundError(f"No .png files found in {p}")
    return random.choice(pngs)

def render_reel(
    voiceover_path: str | Path,
    subtitles_path: str | Path,
    output_path: str | Path,
    product_image_path: str | Path | None = None,
    background_video_path: str | Path = "assets/background.mp4",
    peter_img_dir: str | Path = "assets/peter",
    stewie_img_dir: str | Path = "assets/stewie",
    music_dir: str | Path | None = None,
    fonts_dir: str | Path | None = None,
) -> str:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    voiceover = AudioFileClip(str(voiceover_path))
    total_duration = float(voiceover.duration)

    # 1. Background Video — random segment (avoid last 30s)
    bg_video = VideoFileClip(str(background_video_path)).without_audio()
    margin = 30.0  # never start in the last 30 seconds
    max_start = bg_video.duration - total_duration - margin
    if max_start > 0:
        start_offset = random.uniform(0, max_start)
        bg_video = bg_video.subclipped(start_offset, start_offset + total_duration)
    elif bg_video.duration > total_duration:
        bg_video = bg_video.subclipped(0, total_duration)
    else:
        bg_video = bg_video.with_effects([vfx.Loop(duration=total_duration)])

    # Resize then crop — two separate steps to use correct post-resize width
    bg_video = bg_video.resized(height=TARGET_SIZE[1])
    bg_video = bg_video.cropped(x_center=bg_video.w / 2, width=TARGET_SIZE[0])
    
    # 2. Gradient
    gradient = _create_gradient_overlay()
    gradient_clip = ImageClip(gradient).with_duration(total_duration).with_position(("center", TARGET_SIZE[1] - gradient.shape[0]))

    # 3. Load Subtitles & Find speaking intervals
    with open(subtitles_path, "r", encoding="utf-8") as f:
        subs = json.load(f)

    subtitle_clips = []
    font_path = _find_font(Path(fonts_dir)) if fonts_dir else None
    
    intervals = []
    current_speaker = None
    cur_start = 0.0
    
    for i, w in enumerate(subs):
        color = "yellow" if i % 2 == 0 else "white"
        subtitle_clips.append(_text_clip(w["text"], w["start"], w["end"], font_path, color))
        
        spk = w.get("speaker", "peter")
        if current_speaker != spk:
            if current_speaker is not None:
                intervals.append({"speaker": current_speaker, "start": cur_start, "end": w["start"]})
            current_speaker = spk
            cur_start = w["start"]
            
    if current_speaker is not None and subs:
        intervals.append({"speaker": current_speaker, "start": cur_start, "end": total_duration})

    # 4. Avatar Clips — random PNG per speaking interval
    avatar_clips = []
    for intv in intervals:
        img_dir = peter_img_dir if intv["speaker"] == "peter" else stewie_img_dir
        img_path = _pick_random_png(img_dir)
        y_pos = int(TARGET_SIZE[1] * 0.45)
        aclip = get_bouncing_avatar(img_path, intv["start"], intv["end"], y_pos, TARGET_SIZE)
        avatar_clips.append(aclip)

    # 4.5 Product Pop-Up Image — show during ALL of Stewie's speaking time
    product_clip = None
    if product_image_path and Path(product_image_path).exists():
        # Find Stewie's full speaking range (first start to last end)
        stewie_intervals = [iv for iv in intervals if iv["speaker"] == "stewie"]
        if stewie_intervals:
            prod_start = stewie_intervals[0]["start"]
            prod_end = stewie_intervals[-1]["end"]
            prod_dur = prod_end - prod_start
            
            p_img = Image.open(str(product_image_path)).convert("RGBA")
            # Scale to fit nicely at top — 300px wide, preserve ratio
            pw, ph = p_img.size
            scale = 300 / pw
            p_img = p_img.resize((int(pw * scale), int(ph * scale)), Image.Resampling.LANCZOS)
            
            product_clip = (ImageClip(np.array(p_img))
                .with_duration(prod_dur)
                .with_start(prod_start)
                .with_position(("center", 120)))

    # Combine visuals
    all_layers = [bg_video, gradient_clip, *avatar_clips, *subtitle_clips]
    if product_clip is not None:
        all_layers.append(product_clip)
        
    final_video = CompositeVideoClip(all_layers, size=TARGET_SIZE)

    # 5. Audio
    audio_tracks = [voiceover]
    if music_dir:
        mpath = _pick_background_music(Path(music_dir))
        if mpath:
            bgm = AudioFileClip(str(mpath)).with_duration(total_duration)
            if hasattr(bgm, "with_volume_scaled"): bgm = bgm.with_volume_scaled(0.15)
            audio_tracks.append(bgm)
            
    final_video = final_video.with_audio(CompositeAudioClip(audio_tracks))

    final_video.write_videofile(
        str(output),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=8,
    )

    final_video.close()
    voiceover.close()
    return str(output)
