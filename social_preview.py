import re
import urllib.request
import urllib.error
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify

# ── Tags to extract ──
OG_TAGS = [
    "og:title", "og:description", "og:image", "og:url",
    "og:type", "og:site_name", "og:locale",
    "og:image:width", "og:image:height", "og:image:alt",
]
TWITTER_TAGS = [
    "twitter:card", "twitter:title", "twitter:description",
    "twitter:image", "twitter:site", "twitter:creator", "twitter:image:alt",
]

# Regex: finds every <meta ...> in the <head>
_META_RE = re.compile(r'<meta\s+([^>]+?)/?>', re.IGNORECASE | re.DOTALL)
_PROP_RE = re.compile(
    r'''(?:property|name)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^\s>/"\']+))''',
    re.IGNORECASE,
)
_CONT_RE = re.compile(
    r'''content\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^\s>/"\']+))''',
    re.IGNORECASE,
)


# ─────────────────────────────────────────────
def _fetch_html(url: str, timeout: int = 12) -> str:
    """Download up to 500 KB of the page HTML."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = "utf-8"
        ct = resp.headers.get_content_type() or ""
        if "charset=" in ct:
            charset = ct.split("charset=")[-1].strip().split(";")[0].strip()
        return resp.read(500_000).decode(charset, errors="replace")


def _parse_meta_tags(html: str) -> tuple[dict, dict]:
    """Extract og:* and twitter:* meta tags. Only scans <head> for speed."""
    head_end = html.lower().find("</head>")
    head = html[:head_end] if head_end != -1 else html

    og = {}
    twitter = {}

    for m in _META_RE.finditer(head):
        attrs = m.group(1)

        pm = _PROP_RE.search(attrs)
        if not pm:
            continue
        prop = (pm.group(1) or pm.group(2) or pm.group(3) or "").lower().strip()

        cm = _CONT_RE.search(attrs)
        if not cm:
            continue
        content = (cm.group(1) or cm.group(2) or cm.group(3) or "").strip()

        if not prop or not content:
            continue

        if prop.startswith("og:"):
            og[prop] = content
        elif prop.startswith("twitter:"):
            twitter[prop] = content

    return og, twitter


def _check_image(image_url: str, timeout: int = 6) -> bool:
    """HEAD the og:image URL to confirm it is publicly reachable."""
    if not image_url:
        return False
    try:
        req = urllib.request.Request(
            image_url,
            method="HEAD",
            headers={"User-Agent": "SocialPreviewBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except Exception:
        return False


def _build_readiness(og: dict, twitter: dict) -> dict:
    image_url = og.get("og:image", "")
    w = og.get("og:image:width",  "0") or "0"
    h = og.get("og:image:height", "0") or "0"
    try:
        dims_ok = int(w) >= 1200 and int(h) >= 630
    except ValueError:
        dims_ok = False

    return {
        "has_og":              bool(og),
        "has_twitter":         bool(twitter),
        "og_score":            sum(1 for t in OG_TAGS      if og.get(t)),
        "twitter_score":       sum(1 for t in TWITTER_TAGS if twitter.get(t)),
        "image_accessible":    _check_image(image_url),
        "image_dimensions_ok": dims_ok,
    }


# ─────────────────────────────────────────────
#  Public API — called from app.py
# ─────────────────────────────────────────────

def get_social_preview(url: str) -> dict:
    """
    Fetch *url* and return all OG / Twitter meta tags plus a readiness summary.
    Always returns a dict — never raises.
    """
    try:
        html = _fetch_html(url)
    except urllib.error.HTTPError as exc:
        return {"url": url, "og": {}, "twitter": {}, "readiness": {}, "error": f"HTTP {exc.code} — {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"url": url, "og": {}, "twitter": {}, "readiness": {}, "error": f"Could not reach URL: {exc.reason}"}
    except Exception as exc:
        return {"url": url, "og": {}, "twitter": {}, "readiness": {}, "error": str(exc)}

    og, twitter = _parse_meta_tags(html)
    readiness   = _build_readiness(og, twitter)

    # Strip prefixes so frontend can access og.title, og.image, tw.card etc.
    og_clean      = {k.replace("og:", "", 1): v for k, v in og.items()}
    twitter_clean = {k.replace("twitter:", "", 1): v for k, v in twitter.items()}

    return {
        "url":       url,
        "og":        og_clean,
        "twitter":   twitter_clean,
        "readiness": readiness,
        "error":     None,
    }

# ─────────────────────────────────────────────
# Flask Blueprint API
# ─────────────────────────────────────────────

social_preview_bp = Blueprint("social_preview", __name__)

@social_preview_bp.route("/api/social_preview", methods=["GET"])
def social_preview_api():
    url = request.args.get("url")

    if not url:
        return jsonify({
            "error": "Missing ?url= parameter"
        }), 400

    result = get_social_preview(url)
    return jsonify(result)