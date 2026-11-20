"""Background worker: every few seconds, picks up due jobs and uploads them."""
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import db
from .platforms import meta, youtube

POLL_SECONDS = 10
_executor = ThreadPoolExecutor(max_workers=3)
_stop = threading.Event()


def run_job(job: dict):
    job_id = job["id"]

    def progress(msg: str):
        db.update_job(job_id, progress=msg)

    try:
        p = job["platform"]
        if p == "youtube":
            url = youtube.upload(job["video_path"], job["title"], job["caption"], job["privacy"], progress)
        elif p == "instagram":
            url = meta.upload_instagram(job["video_path"], job["caption"], progress)
        elif p == "facebook":
            url = meta.upload_facebook(job["video_path"], job["caption"], progress)
        else:
            raise RuntimeError(f"Unknown platform {p}")
        db.update_job(job_id, status="done", progress="Posted", result_url=url, error=None)
    except Exception as e:
        traceback.print_exc()
        db.update_job(job_id, status="failed", progress=None, error=str(e)[:1000])


def _loop():
    while not _stop.is_set():
        try:
            for job in db.claim_due_jobs():
                _executor.submit(run_job, job)
        except Exception:
            traceback.print_exc()
        _stop.wait(POLL_SECONDS)


def start():
    threading.Thread(target=_loop, daemon=True, name="upload-worker").start()


def stop():
    _stop.set()
