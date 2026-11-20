"""Optional video checks using ffprobe (part of FFmpeg). Skipped if ffprobe isn't installed."""
import json
import shutil
import subprocess

LIMITS = {
    "youtube": 180,    # Shorts: up to 3 minutes
    "instagram": 900,  # Reels via API: 3s - 15 min
    "facebook": 90,    # Facebook Reels: 3s - 90s
}


def probe(path: str) -> dict | None:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,codec_name:stream_tags=rotate:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(out.stdout)
        s = data["streams"][0]
        w, h = s["width"], s["height"]
        if str(s.get("tags", {}).get("rotate", "0")) in ("90", "270"):
            w, h = h, w
        return {"width": w, "height": h, "codec": s.get("codec_name"),
                "duration": float(data["format"]["duration"])}
    except Exception:
        return None


def warnings_for(path: str, platforms: list[str]) -> list[str]:
    info = probe(path)
    if info is None:
        return []
    warns = []
    if info["height"] <= info["width"]:
        warns.append(f"Video is {info['width']}x{info['height']} — Shorts/Reels should be vertical (9:16, e.g. 1080x1920).")
    if info["duration"] < 3:
        warns.append("Video is shorter than 3 seconds; Instagram and Facebook will reject it.")
    for p in platforms:
        if info["duration"] > LIMITS[p]:
            warns.append(f"Video is {info['duration']:.0f}s — {p.title()} allows max {LIMITS[p]}s for Shorts/Reels.")
    if info["codec"] not in ("h264", "hevc"):
        warns.append(f"Video codec is {info['codec']}; H.264 MP4 is the safest choice.")
    return warns
