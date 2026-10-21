"""সব সেটিংস এক জায়গায়। পরিবর্তন করতে .env / এনভায়রনমেন্ট ভ্যারিয়েবল ব্যবহার করুন।"""
import os

def _list(v): return [x.strip() for x in v.split(",") if x.strip()]

# --- বিজ্ঞাপন: ADS_ENABLED=true করে স্লটে HTML/স্ক্রিপ্ট বসালেই চালু ---
ADS_ENABLED = os.getenv("ADS_ENABLED", "false").lower() == "true"
ADS_TOP_HTML = os.getenv("ADS_TOP_HTML", "")        # ফলাফলের উপরে
ADS_BOTTOM_HTML = os.getenv("ADS_BOTTOM_HTML", "")  # পেজের নিচে

# --- সীমা ও সুরক্ষা ---
ALLOWED_DOMAINS = _list(os.getenv("ALLOWED_DOMAINS",
    "youtube.com,youtu.be,facebook.com,fb.watch,tiktok.com,instagram.com,twitter.com,x.com"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
MAX_PARALLEL_DOWNLOADS = int(os.getenv("MAX_PARALLEL_DOWNLOADS", "3"))

# --- ইউটিউব ব্লক হলে ---
PROXY = os.getenv("PROXY") or None            # যেমন http://user:pass@host:port
COOKIES_FILE = os.getenv("COOKIES_FILE") or None
