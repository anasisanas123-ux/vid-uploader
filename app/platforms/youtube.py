"""YouTube Shorts upload via YouTube Data API v3."""
import secrets
from urllib.parse import urlencode

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .. import tokens
from ..config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_pending_states: set[str] = set()


def is_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def auth_start_url() -> str:
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",   # gives us a refresh token
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def auth_callback(code: str, state: str):
    if state not in _pending_states:
        raise ValueError("Invalid or expired login attempt, please try again.")
    _pending_states.discard(state)
    r = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=30)
    r.raise_for_status()
    tok = r.json()
    if "refresh_token" not in tok:
        raise ValueError("Google did not return a refresh token. Remove the app at "
                         "myaccount.google.com/permissions and connect again.")
    creds = _creds_from({"token": tok["access_token"], "refresh_token": tok["refresh_token"]})
    channel = _channel_name(creds)
    tokens.save_section("youtube", {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "channel": channel,
    })


def _creds_from(data: dict) -> Credentials:
    return Credentials(
        token=data.get("token"),
        refresh_token=data["refresh_token"],
        token_uri=TOKEN_URL,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )


def _get_creds() -> Credentials:
    data = tokens.get_section("youtube")
    if not data:
        raise RuntimeError("YouTube is not connected. Click Connect next to YouTube in the Accounts panel.")
    creds = _creds_from(data)
    if not creds.valid:
        creds.refresh(Request())
        data["token"] = creds.token
        tokens.save_section("youtube", data)
    return creds


def _channel_name(creds: Credentials) -> str:
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    res = yt.channels().list(part="snippet", mine=True).execute()
    items = res.get("items", [])
    return items[0]["snippet"]["title"] if items else "(no channel)"


def status() -> dict:
    data = tokens.get_section("youtube")
    return {"configured": is_configured(), "connected": bool(data),
            "account": data.get("channel") if data else None}


def upload(video_path: str, title: str, description: str, privacy: str, on_progress) -> str:
    creds = _get_creds()
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    title = (title or "").strip() or "New Short"
    # #Shorts in the title/description helps YouTube classify it as a Short
    # (vertical + under 3 minutes is what actually matters).
    if "#shorts" not in (title + " " + (description or "")).lower():
        description = ((description or "") + "\n\n#Shorts").strip()

    body = {
        "snippet": {"title": title[:100], "description": (description or "")[:5000], "categoryId": "22"},
        "status": {"privacyStatus": privacy or "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/*")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    try:
        while response is None:
            prog, response = req.next_chunk(num_retries=3)
            if prog:
                on_progress(f"Uploading {int(prog.progress() * 100)}%")
    except HttpError as e:
        raise RuntimeError(_explain(e)) from e

    return f"https://youtube.com/shorts/{response['id']}"


def _explain(e: HttpError) -> str:
    text = str(e)
    if "quotaExceeded" in text:
        return "YouTube daily quota used up (about 6 uploads/day). Try again tomorrow."
    if "uploadLimitExceeded" in text:
        return "Your YouTube channel hit its upload limit. Try again later."
    return f"YouTube error: {text}"
