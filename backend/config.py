from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    pexels_api_key: str = os.getenv("PEXELS_API_KEY", "")
    hf_api_token: str = os.getenv("HF_API_TOKEN", "")
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    tts_voice: str = os.getenv("TTS_VOICE", "en-US-ChristopherNeural")
    instagram_username: str = os.getenv("INSTAGRAM_USERNAME", "")
    instagram_password: str = os.getenv("INSTAGRAM_PASSWORD", "")
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", str(ROOT_DIR / "output"))).resolve()
    assets_dir: Path = Path(os.getenv("ASSETS_DIR", str(ROOT_DIR / "assets"))).resolve()
    data_dir: Path = (ROOT_DIR / "data").resolve()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "analytics.db"

    @property
    def jobs_dir(self) -> Path:
        return self.output_dir / "jobs"

    @property
    def images_dir(self) -> Path:
        return self.output_dir / "images"

    @property
    def music_dir(self) -> Path:
        return self.assets_dir / "music"

    @property
    def fonts_dir(self) -> Path:
        return self.assets_dir / "fonts"


settings = Settings()

# Runtime credentials — updated from the UI, never saved to disk
runtime_credentials: dict[str, str] = {}


def get_instagram_creds() -> tuple[str, str]:
    """Return (username, password). Prefers UI-entered creds, falls back to .env."""
    username = runtime_credentials.get("instagram_username") or settings.instagram_username
    password = runtime_credentials.get("instagram_password") or settings.instagram_password
    return username, password



def ensure_directories() -> None:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.assets_dir.mkdir(parents=True, exist_ok=True)
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    settings.fonts_dir.mkdir(parents=True, exist_ok=True)
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)

