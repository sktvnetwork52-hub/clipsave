import logging, os, re, shutil, tempfile, threading, time
from collections import defaultdict, deque
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

import config as C

log = logging.getLogger("uvicorn.error")
app = FastAPI(title="ClipSave")
jobs = threading.Semaphore(C.MAX_PARALLEL_DOWNLOADS)
hits: dict[str, deque] = defaultdict(deque)

# Cookies file may live on a read-only mount (e.g. Render secret files) while
# yt-dlp needs to write session cookies back — work from a writable copy.
_cookie_path = C.COOKIES_FILE
if _cookie_path and os.path.exists(_cookie_path):
    try:
        _dest = os.path.join(tempfile.gettempdir(), "cookies.txt")
        shutil.copyfile(_cookie_path, _dest)
        _cookie_path = _dest
    except OSError:
        pass


def guard(request: Request, url: str):
    """রেট-লিমিট + URL যাচাই (অনুমোদিত সাইট ছাড়া অন্য কিছু ফেচ করবে না)।"""
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    q, now = hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= C.RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "অনেক বেশি অনুরোধ, একটু পরে চেষ্টা করুন।")
    q.append(now)
    u = urlparse(url)
    host = (u.hostname or "").lower()
    ok = u.scheme in ("http", "https") and any(host == d or host.endswith("." + d) for d in C.ALLOWED_DOMAINS)
    if not ok:
        raise HTTPException(400, "এই লিংকটি সাপোর্ট করা হয় না।")


def reason(e: Exception) -> str:
    """yt-dlp এররের শেষ লাইন, রঙের কোড বাদ দিয়ে।"""
    t = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip().splitlines()
    return (t[-1] if t else "")[:200]


def base_opts():
    o = {"quiet": True, "noplaylist": True, "no_warnings": True}
    if C.PROXY: o["proxy"] = C.PROXY
    if _cookie_path: o["cookiefile"] = _cookie_path
    return o


@app.get("/api/config")
def config():
    return {"ads": {"enabled": C.ADS_ENABLED, "top": C.ADS_TOP_HTML, "bottom": C.ADS_BOTTOM_HTML}}


@app.get("/api/info")
def info(request: Request, url: str):
    guard(request, url)
    try:
        with yt_dlp.YoutubeDL(base_opts()) as y:
            d = y.extract_info(url, download=False)
    except Exception as e:
        log.exception("info failed: %s", url)
        raise HTTPException(400, "ভিডিওর তথ্য পাওয়া যায়নি। কারণ: " + reason(e))
    fmts = d.get("formats") or []
    heights = sorted({f["height"] for f in fmts if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
    return {"title": d.get("title"), "thumbnail": d.get("thumbnail"), "duration": d.get("duration"),
            "uploader": d.get("uploader"), "heights": heights}


@app.get("/api/download")
def download(request: Request, url: str, quality: str = "best"):
    guard(request, url)
    if not re.fullmatch(r"best|lowest|mp3|\d{3,4}", quality):
        raise HTTPException(400, "কোয়ালিটি সঠিক নয়।")
    if not jobs.acquire(blocking=False):
        raise HTTPException(503, "সার্ভার এখন ব্যস্ত, একটু পরে চেষ্টা করুন।")
    tmp = tempfile.mkdtemp(prefix="clip_")

    def cleanup():
        shutil.rmtree(tmp, ignore_errors=True)
        jobs.release()

    o = base_opts() | {"outtmpl": f"{tmp}/%(title).80s.%(ext)s", "restrictfilenames": False}
    if quality == "mp3":
        o |= {"format": "bestaudio/best",
              "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
    else:
        sel = {"best": "bv*+ba/b", "lowest": "wv*+wa/w"}.get(quality, f"bv*[height<={quality}]+ba/b[height<={quality}]")
        o |= {"format": sel, "merge_output_format": "mp4", "format_sort": ["res", "ext:mp4:m4a"]}
    try:
        with yt_dlp.YoutubeDL(o) as y:
            y.download([url])
        files = [os.path.join(tmp, f) for f in os.listdir(tmp)]
        path = max(files, key=os.path.getsize)
    except Exception as e:
        log.exception("download failed: %s", url)
        cleanup()
        raise HTTPException(500, "ডাউনলোড করা যায়নি। কারণ: " + reason(e))
    return FileResponse(path, filename=os.path.basename(path), background=BackgroundTask(cleanup))


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend"), html=True))
