import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
MEDIA_DIR = ROOT / "media"
STATIC_DIR = ROOT / "static"
DB_PATH = DATA_DIR / "uploader.db"
TOKENS_PATH = DATA_DIR / "tokens.json"

DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)

PORT = int(os.getenv("PORT", "8000"))
BASE_URL = f"http://localhost:{PORT}"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = f"{BASE_URL}/auth/youtube/callback"

META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_CONFIG_ID = os.getenv("META_CONFIG_ID", "")  # optional, for "Facebook Login for Business"
META_REDIRECT_URI =f"{BASE_URL}/auth/meta/callback"
GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v21.0")

PLATFORMS = ("youtube", "instagram", "facebook")
