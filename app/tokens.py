"""Stores OAuth tokens locally in data/tokens.json (never leaves your PC)."""
import json
import threading

from .config import TOKENS_PATH

_lock = threading.Lock()


def load() -> dict:
    with _lock:
        if TOKENS_PATH.exists():
            return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
        return {}


def save_section(name: str, value: dict | None):
    with _lock:
        data = json.loads(TOKENS_PATH.read_text(encoding="utf-8")) if TOKENS_PATH.exists() else {}
        if value is None:
            data.pop(name, None)
        else:
            data[name] = value
        TOKENS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_section(name: str) -> dict | None:
    return load().get(name)
