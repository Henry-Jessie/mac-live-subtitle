import os
from pathlib import Path


APP_NAME = "Mac Live Subtitle"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
RESOURCE_DIR = Path(os.environ.get("RESOURCEPATH", PROJECT_ROOT))


def default_config_path() -> Path:
    if "RESOURCEPATH" in os.environ:
        return APP_SUPPORT_DIR / "config.ini"
    return PROJECT_ROOT / "config.ini"


def default_credentials_path() -> Path:
    return APP_SUPPORT_DIR / "credentials.json"


def resource_path(*parts: str) -> Path:
    return RESOURCE_DIR.joinpath(*parts)
