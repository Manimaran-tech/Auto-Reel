"""Video Renderer — composites product images into a dynamic slideshow Instagram Reel."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)

from .voice_engine import group_words, parse_vtt

TARGET_SIZE = (720, 1280)


def _fit_image_to_canvas(image_path: Path, target_size: tuple[int, int] = TARGET_SIZE) -> np.ndarray:
    """Resize/pad an image to perfectly fit the vertical canvas with blurred background."""
    target_w, target_h = target_size
    image = Image.open(image_path).convert("RGB")
    img_w, img_h = image.size

    image_ratio = img_w / img_h
    target_ratio = target_w / target_h

    if image_ratio > target_ratio:
        bg = image.resize((target_w, target_h), Image.Resampling.BILINEAR).filter(
            ImageFilter.GaussianBlur(radius=30)
        )
        fg_h = target_h
        fg_w = int(fg_h * image_ratio)
        fg = image.resize((fg_w, fg_h), Image.Resampling.BILINEAR)
        left = max((fg_w - target_w) // 2, 0)
        fg = fg.crop((left, 0, left + target_w, target_h))
        bg.paste(fg, (0, 0))
        frame = bg
    else:
        scale = max(target_w / img_w, target_h / img_h)
        resized = image.resize((int(img_w * scale), int(img_h * scale)), Image.Resampling.BILINEAR)
        left = max((resized.width - target_w) // 2, 0)
        top = max((resized.height - target_h) // 2, 0)
        frame = resized.crop((left, top, left + target_w, top + target_h))

    return np.array(frame)


def make_ken_burns_clip(
    image_path: Path,
    duration: float,
    zoom_in: bool = True,
    target_size: tuple[int, int] = TARGET_SIZE,
) -> ImageClip:
    """Create a Ken Burns (slow zoom) effect clip from a static image."""
    base_frame = _fit_image_to_canvas(image_path, target_size=target_size)
    clip = ImageClip(base_frame).with_duration(duration)
    width, height = target_size

    def zoom_effect(get_frame, t):
        if zoom_in:
            zoom = 1.0 + (0.15 * t / max(duration, 0.1))
        else:
            zoom = 1.15 - (0.15 * t / max(duration, 0.1))
        zoom = max(1.0, min(1.15, zoom))
        frame = get_frame(t)
        new_w, new_h = int(width / zoom), int(height / zoom)
        x = (width - new_w) // 2
        y = (height - new_h) // 2
        cropped = frame[y : y + new_h, x : x + new_w]
        resized = np.array(Image.fromarray(cropped).resize((width, height), Image.Resampling.BILINEAR))
        return resized

    return clip.transform(zoom_effect)


def _create_gradient_overlay(target_size: tuple[int, int] = TARGET_SIZE, height_pct: float = 0.6) -> np.ndarray:
    """Create a bottom gradient overlay for subtitle readability."""
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
    """Render text to an RGBA numpy array using PIL (bypasses buggy ImageMagick)."""
    # Load font
    try:
        if font_path:
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        font = ImageFont.load_default()

    display_text = text.upper()

    # Measure text bounding box with stroke
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox(
        (0, 0), display_text, font=font, stroke_width=stroke_width
    )
    text_w = bbox[2] - bbox[0] + stroke_width * 2 + 10
    text_h = bbox[3] - bbox[1] + stroke_width * 2 + 10

    # Create transparent canvas and draw text centered
    img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = (text_w - (bbox[2] - bbox[0])) // 2
    y = (text_h - (bbox[3] - bbox[1])) // 2
    draw.text(
        (x, y),
        display_text,
        font=font,
        fill=color,
        stroke_fill=stroke_color,
        stroke_width=stroke_width,
    )
    return np.array(img)


def _text_clip(
    text: str,
    start: float,
    end: float,
    font_path: str | None = None,
    color: str = "white",
    target_size: tuple[int, int] = TARGET_SIZE,
) -> ImageClip:
    """Create a subtitle text clip using PIL rendering (no ImageMagick)."""
    text_img = _render_text_pil(
        text, font_path=font_path, font_size=52, color=color,
        stroke_color="black", stroke_width=4,
    )
    clip = ImageClip(text_img).with_duration(end - start)
    y_pos = int(target_size[1] * 0.78)
    return clip.with_start(start).with_end(end).with_position(("center", y_pos))


def _pick_background_music(music_dir: Path) -> Path | None:
    if not music_dir.exists():
        return None
    for candidate in music_dir.iterdir():
        if candidate.suffix.lower() in {".mp3", ".wav", ".m4a"}:
            return candidate
    return None


def _find_font(fonts_dir: Path) -> str | None:
    if not fonts_dir.exists():
        return None
    for candidate in fonts_dir.iterdir():
        if candidate.suffix.lower() in {".ttf", ".otf"}:
            return str(candidate)
    return None


def render_reel(
    image_paths: Iterable[str],
    voiceover_path: str | Path,
    subtitles_path: str | Path,
    output_path: str | Path,
    music_dir: str | Path | None = None,
    fonts_dir: str | Path | None = None,
) -> str:
    """Build the final Reel using a dynamic product slideshow + voiceover + subtitles."""
    image_list = [Path(path) for path in image_paths]
    if not image_list:
        raise ValueError("No images provided for video rendering.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    voiceover = AudioFileClip(str(voiceover_path))
    total_duration = float(voiceover.duration)

    # ══════════════════════════════════════════════════════════════════════════
    # SLIDESHOW (Ken Burns)
    # ══════════════════════════════════════════════════════════════════════════
    crossfade = 0.3
    n_images = len(image_list)
    # Compensate for crossfade overlap: total lost = crossfade * (N-1)
    total_slide_time = total_duration + crossfade * max(n_images - 1, 0)
    per_image = max(total_slide_time / n_images, 1.0)
    visual_clips = [
        make_ken_burns_clip(img, per_image, zoom_in=(idx % 2 == 0))
        for idx, img in enumerate(image_list)
    ]
    
    # Concatenate with a slight crossfade padding to smooth transitions
    base_video = concatenate_videoclips(visual_clips, method="compose", padding=-crossfade).with_duration(total_duration)

    # ══════════════════════════════════════════════════════════════════════════
    # OVERLAYS & TEXT
    # ══════════════════════════════════════════════════════════════════════════
    gradient = _create_gradient_overlay()
    gradient_clip = (
        ImageClip(gradient)
        .with_duration(total_duration)
        .with_position(("center", TARGET_SIZE[1] - gradient.shape[0]))
    )

    subtitle_entries = parse_vtt(Path(subtitles_path))
    # 1 word per group makes the text "flow" super fast
    grouped = group_words(subtitle_entries, words_per_group=1)
    font_path = _find_font(Path(fonts_dir)) if fonts_dir else None
    
    subtitle_clips = []
    for i, entry in enumerate(grouped):
        # Alternate colors to make it visually pop
        color = "yellow" if i % 2 == 0 else "white"
        clip = _text_clip(entry["text"], entry["start"], entry["end"], font_path=font_path, color=color)
        subtitle_clips.append(clip)

    all_layers = [base_video, gradient_clip, *subtitle_clips]
    final_video = CompositeVideoClip(all_layers, size=TARGET_SIZE)

    # ══════════════════════════════════════════════════════════════════════════
    # AUDIO COMPOSE
    # ══════════════════════════════════════════════════════════════════════════
    audio_tracks = [voiceover]
    if music_dir:
        music_path = _pick_background_music(Path(music_dir))
        if music_path:
            bgm = AudioFileClip(str(music_path)).with_duration(total_duration)
            if hasattr(bgm, "with_volume_scaled"):
                bgm = bgm.with_volume_scaled(0.15)
            audio_tracks.append(bgm)
            
    final_audio = CompositeAudioClip(audio_tracks)
    final_video = final_video.with_audio(final_audio)

    # ══════════════════════════════════════════════════════════════════════════
    # RENDER
    # ══════════════════════════════════════════════════════════════════════════
    final_video.write_videofile(
        str(output),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=8,
    )

    # Cleanup memory
    final_video.close()
    final_audio.close()
    voiceover.close()
    for clip in visual_clips:
        try:
            clip.close()
        except Exception:
            pass
            
    return str(output)
