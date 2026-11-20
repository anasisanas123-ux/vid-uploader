import json
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from . import db, tokens, video, worker
from .config import MEDIA_DIR, PLATFORMS, STATIC_DIR
from .platforms import meta, youtube


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="Uploader", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# ------------------------------------------------------------- accounts

@app.get("/api/accounts")
def accounts():
    return {"youtube": youtube.status(), "meta": meta.status()}


def _result_page(ok: bool, msg: str) -> HTMLResponse:
    color = "#16a34a" if ok else "#dc2626"
    return HTMLResponse(
        f"<body style='font-family:sans-serif;padding:40px'><h2 style='color:{color}'>{msg}</h2>"
        f"<a href='/'>Back to Uploader</a></body>",
        status_code=200 if ok else 400,
    )


@app.get("/auth/youtube/start")
def yt_start():
    if not youtube.is_configured():
        raise HTTPException(400, "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env first (see SETUP.md).")
    return RedirectResponse(youtube.auth_start_url())


@app.get("/auth/youtube/callback")
def yt_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return _result_page(False, f"YouTube login cancelled: {error}")
    try:
        youtube.auth_callback(code, state)
    except Exception as e:
        return _result_page(False, f"YouTube connection failed: {e}")
    return RedirectResponse("/")


@app.get("/auth/meta/start")
def meta_start():
    if not meta.is_configured():
        raise HTTPException(400, "Add META_APP_ID and META_APP_SECRET to .env first (see SETUP.md).")
    return RedirectResponse(meta.auth_start_url())


@app.get("/auth/meta/callback")
def meta_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error:
        return _result_page(False, f"Facebook login cancelled: {error_description or error}")
    try:
        meta.auth_callback(code, state)
    except Exception as e:
        return _result_page(False, f"Facebook/Instagram connection failed: {e}")
    return RedirectResponse("/")


@app.post("/api/meta/page")
def meta_page(page_id: str = Form(...)):
    try:
        meta.select_page(page_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/disconnect/{name}")
def disconnect(name: str):
    if name not in ("youtube", "meta"):
        raise HTTPException(404)
    tokens.save_section(name, None)
    return {"ok": True}


# ------------------------------------------------------------- posts

@app.post("/api/posts")
async def create_post(
    file: UploadFile = File(...),
    platforms: str = Form(...),           # JSON list
    yt_title: str = Form(""),
    yt_caption: str = Form(""),
    yt_privacy: str = Form("public"),
    ig_caption: str = Form(""),
    fb_caption: str = Form(""),
    scheduled_at: str = Form(""),         # "YYYY-MM-DDTHH:MM" local time, empty = now
):
    try:
        chosen = [p for p in json.loads(platforms) if p in PLATFORMS]
    except (ValueError, TypeError):
        raise HTTPException(400, "Bad platforms list.")
    if not chosen:
        raise HTTPException(400, "Pick at least one platform.")
    if "youtube" in chosen and not yt_title.strip():
        raise HTTPException(400, "YouTube needs a title.")
    if yt_privacy not in ("public", "unlisted", "private"):
        raise HTTPException(400, "Bad privacy value.")

    sched = None
    if scheduled_at:
        try:
            sched_dt = datetime.fromisoformat(scheduled_at)
        except ValueError:
            raise HTTPException(400, "Bad schedule date.")
        sched = sched_dt.replace(microsecond=0).isoformat()

    ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    dest = MEDIA_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=4 * 1024 * 1024)

    captions = {"youtube": yt_caption, "instagram": ig_caption, "facebook": fb_caption}
    jobs = [{
        "platform": p,
        "caption": captions[p],
        "title": yt_title if p == "youtube" else None,
        "privacy": yt_privacy if p == "youtube" else None,
    } for p in chosen]

    post_id = db.create_post(str(dest), file.filename or dest.name, sched, jobs)
    return {"id": post_id, "warnings": video.warnings_for(str(dest), chosen)}


@app.get("/api/posts")
def list_posts():
    return db.list_posts()


@app.post("/api/jobs/{job_id}/retry")
def retry(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404)
    if job["status"] not in ("failed", "cancelled"):
        raise HTTPException(400, "Only failed or cancelled uploads can be retried.")
    db.update_job(job_id, status="pending", error=None, progress=None)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404)
    if job["status"] != "pending":
        raise HTTPException(400, "Only waiting uploads can be cancelled.")
    db.update_job(job_id, status="cancelled")
    return {"ok": True}


@app.delete("/api/posts/{post_id}")
def delete_post(post_id: int):
    post = db.get_post(post_id)
    if not post:
        raise HTTPException(404)
    if any(j["status"] == "uploading" for j in post["jobs"]):
        raise HTTPException(400, "Wait for uploads to finish before deleting.")
    db.delete_post(post_id)
    Path(post["video_path"]).unlink(missing_ok=True)
    return {"ok": True}
