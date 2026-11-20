"""Instagram Reels + Facebook Page Reels via the Meta Graph API.

One Facebook login gives us:
  * a Page access token (never expires when derived from a long-lived user token)
  * the Instagram Business/Creator account linked to that Page
"""
import os
import secrets
import time
from urllib.parse import urlencode

import requests

from .. import tokens
from ..config import GRAPH_VERSION, META_APP_ID, META_APP_SECRET, META_CONFIG_ID, META_REDIRECT_URI

GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "business_management",
    "instagram_basic",
    "instagram_content_publish",
]

_pending_states: set[str] = set()


class MetaError(RuntimeError):
    pass


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        r.raise_for_status()
        raise MetaError(f"Unexpected response from Meta: {r.text[:300]}")
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        msg = err.get("error_user_msg") or err.get("message") or str(err)
        raise MetaError(f"Meta error: {msg}")
    r.raise_for_status()
    return data


def is_configured() -> bool:
    return bool(META_APP_ID and META_APP_SECRET)


# ---------------------------------------------------------------- login

def auth_start_url() -> str:
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "state": state,
        "response_type": "code",
    }
    if META_CONFIG_ID:   # "Facebook Login for Business" uses a configuration instead of scopes
        params["config_id"] = META_CONFIG_ID
    else:
        params["scope"] = ",".join(SCOPES)
    return f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?{urlencode(params)}"


def auth_callback(code: str, state: str):
    if state not in _pending_states:
        raise ValueError("Invalid or expired login attempt, please try again.")
    _pending_states.discard(state)

    short = _check(requests.get(f"{GRAPH}/oauth/access_token", params={
        "client_id": META_APP_ID, "client_secret": META_APP_SECRET,
        "redirect_uri": META_REDIRECT_URI, "code": code,
    }, timeout=30))["access_token"]

    long_user = _check(requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET, "fb_exchange_token": short,
    }, timeout=30))["access_token"]

    pages = _check(requests.get(f"{GRAPH}/me/accounts", params={
        "fields": "id,name,access_token,instagram_business_account{id,username}",
        "access_token": long_user, "limit": 100,
    }, timeout=30)).get("data", [])

    if not pages:
        raise ValueError("No Facebook Pages found. You need a Facebook Page (and to tick it "
                         "during login). See SETUP.md.")

    page_list = []
    for p in pages:
        ig = p.get("instagram_business_account") or {}
        page_list.append({
            "id": p["id"], "name": p["name"], "token": p["access_token"],
            "ig_id": ig.get("id"), "ig_username": ig.get("username"),
        })
    # Prefer a page that has Instagram linked
    selected = next((p["id"] for p in page_list if p["ig_id"]), page_list[0]["id"])
    tokens.save_section("meta", {"pages": page_list, "selected_page": selected})


def select_page(page_id: str):
    data = tokens.get_section("meta")
    if not data or not any(p["id"] == page_id for p in data["pages"]):
        raise ValueError("Unknown page")
    data["selected_page"] = page_id
    tokens.save_section("meta", data)


def _page() -> dict:
    data = tokens.get_section("meta")
    if not data:
        raise MetaError("Facebook/Instagram not connected. Click Connect next to Facebook + Instagram in the Accounts panel.")
    return next(p for p in data["pages"] if p["id"] == data["selected_page"])


def status() -> dict:
    data = tokens.get_section("meta")
    if not data:
        return {"configured": is_configured(), "connected": False, "pages": []}
    page = _page()
    return {
        "configured": is_configured(),
        "connected": True,
        "selected_page": data["selected_page"],
        "pages": [{"id": p["id"], "name": p["name"], "ig_username": p["ig_username"]} for p in data["pages"]],
        "facebook_account": page["name"],
        "instagram_account": f"@{page['ig_username']}" if page["ig_username"] else None,
    }


# ---------------------------------------------------------------- helpers

def _rupload(url: str, token: str, video_path: str, on_progress):
    size = os.path.getsize(video_path)
    on_progress("Uploading video")
    with open(video_path, "rb") as f:
        r = requests.post(url, data=f, timeout=600, headers={
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(size),
            "Content-Type": "application/octet-stream",
        })
    data = _check(r)
    if data.get("success") is False:
        raise MetaError(f"Video upload failed: {data}")


# ---------------------------------------------------------------- Instagram

def upload_instagram(video_path: str, caption: str, on_progress) -> str:
    page = _page()
    if not page["ig_id"]:
        raise MetaError("The selected Facebook Page has no Instagram Business/Creator account linked. "
                        "See SETUP.md step 2.")
    token, ig_id = page["token"], page["ig_id"]

    # 1. Create a resumable Reels container
    on_progress("Creating Reel")
    container = _check(requests.post(f"{GRAPH}/{ig_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable",
        "caption": caption or "", "share_to_feed": "true", "access_token": token,
    }, timeout=60))
    cid = container["id"]
    upload_uri = container.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{cid}"

    # 2. Upload the file bytes
    _rupload(upload_uri, token, video_path, on_progress)

    # 3. Wait for Instagram to process the video
    on_progress("Instagram is processing")
    for _ in range(120):  # up to ~10 minutes
        st = _check(requests.get(f"{GRAPH}/{cid}", params={
            "fields": "status_code,status", "access_token": token}, timeout=30))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise MetaError(f"Instagram could not process the video: {st.get('status')}")
        time.sleep(5)
    else:
        raise MetaError("Instagram took too long to process the video.")

    # 4. Publish
    on_progress("Publishing")
    media_id = _check(requests.post(f"{GRAPH}/{ig_id}/media_publish", data={
        "creation_id": cid, "access_token": token}, timeout=60))["id"]
    try:
        return _check(requests.get(f"{GRAPH}/{media_id}", params={
            "fields": "permalink", "access_token": token}, timeout=30))["permalink"]
    except Exception:
        return f"https://www.instagram.com/{page['ig_username']}/"


# ---------------------------------------------------------------- Facebook

def upload_facebook(video_path: str, caption: str, on_progress) -> str:
    page = _page()
    token, page_id = page["token"], page["id"]

    # 1. Start
    on_progress("Creating Reel")
    start = _check(requests.post(f"{GRAPH}/{page_id}/video_reels", data={
        "upload_phase": "start", "access_token": token}, timeout=60))
    video_id = start["video_id"]
    upload_url = start.get("upload_url") or f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{video_id}"

    # 2. Upload bytes
    _rupload(upload_url, token, video_path, on_progress)

    # 3. Finish + publish
    on_progress("Publishing")
    _check(requests.post(f"{GRAPH}/{page_id}/video_reels", data={
        "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
        "description": caption or "", "access_token": token}, timeout=60))

    # 4. Wait for processing so we can report real failures
    on_progress("Facebook is processing")
    for _ in range(120):
        st = _check(requests.get(f"{GRAPH}/{video_id}", params={
            "fields": "status", "access_token": token}, timeout=30)).get("status", {})
        if st.get("video_status") == "error":
            raise MetaError(f"Facebook could not process the video: {st}")
        publishing = (st.get("publishing_phase") or {}).get("status")
        if st.get("video_status") == "ready" or publishing == "complete":
            break
        time.sleep(5)

    return f"https://www.facebook.com/reel/{video_id}"
