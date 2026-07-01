"""
backlink_analysis.py
--------------------
Performs a basic Backlink Analysis by crawling the page and
examining all outbound/inbound link signals available from HTML.

Checks:
  1. External linking domains (unique root domains)
  2. Nofollow / Dofollow classification
  3. UGC / Sponsored rel attributes
  4. Anchor text analysis (branded, keyword, generic, naked URL)
  5. Basic authority estimation per domain (Alexa-style heuristic)
  6. Link equity / PageRank flow signals
  7. Broken external links
  8. Redirect chains on external links
  9. Link velocity hint (last-modified header)
  10. Overall backlink profile health score

Usage:
    from backlink_analysis import get_backlink_analysis
    result = get_backlink_analysis("https://example.com")
"""

import re
import time
from urllib.parse import urljoin, urlparse
from collections import Counter, defaultdict


# ── Well-known high-authority domains (basic heuristic list) ──
HIGH_AUTHORITY_DOMAINS = {
    "google.com", "youtube.com", "facebook.com", "twitter.com", "x.com",
    "linkedin.com", "wikipedia.org", "github.com", "apple.com", "microsoft.com",
    "amazon.com", "instagram.com", "reddit.com", "medium.com", "wordpress.com",
    "w3.org", "mozilla.org", "stackoverflow.com", "cloudflare.com", "ahrefs.com",
    "moz.com", "semrush.com", "hubspot.com", "shopify.com", "wix.com",
    "squarespace.com", "blogger.com", "tumblr.com", "pinterest.com", "tiktok.com",
    "netflix.com", "adobe.com", "salesforce.com", "oracle.com", "ibm.com",
    "nytimes.com", "bbc.com", "cnn.com", "reuters.com", "theguardian.com",
    "gov", "edu", "ac.uk", "gov.uk",
}

GENERIC_ANCHORS = {
    "click here", "here", "read more", "learn more", "more", "link",
    "this", "visit", "website", "page", "article", "source", "view",
    "see more", "details", "info", "information", "check", "go", "get",
}


def _root_domain(hostname: str) -> str:
    """Extract root domain (e.g. sub.example.com → example.com)."""
    parts = hostname.lower().split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname.lower()


def _estimate_authority(domain: str) -> dict:
    """
    Heuristic authority score (0–100).
    Real DA/PA requires Moz/Ahrefs API — this is a structural estimate.
    """
    root = _root_domain(domain)
    tld  = root.split(".")[-1] if "." in root else ""

    # Check well-known list
    for known in HIGH_AUTHORITY_DOMAINS:
        if root == known or root.endswith("." + known) or tld == known:
            return {"score": 85, "tier": "High", "reason": "Well-known authority domain"}

    # TLD signals
    if tld in ("gov", "edu", "mil"):
        return {"score": 80, "tier": "High", "reason": f".{tld} domain — government/educational"}
    if tld in ("org",):
        return {"score": 55, "tier": "Medium", "reason": ".org domain"}
    if tld in ("ac", "edu"):
        return {"score": 75, "tier": "High", "reason": "Academic domain"}

    # Domain length heuristic (shorter = usually older/more established)
    name_len = len(root.replace("." + tld, ""))
    if name_len <= 5:
        return {"score": 50, "tier": "Medium", "reason": "Short domain name — possibly established"}
    if name_len <= 10:
        return {"score": 35, "tier": "Low-Medium", "reason": "Medium-length domain"}

    return {"score": 20, "tier": "Low", "reason": "Unknown domain — no authority signals"}


def _classify_anchor(anchor_text: str, page_domain: str) -> str:
    """Classify anchor text type."""
    text = anchor_text.strip().lower()
    if not text or text in ("", " "):
        return "empty"
    if re.match(r'^https?://', text):
        return "naked_url"
    if text in GENERIC_ANCHORS or len(text.split()) <= 1 and len(text) <= 4:
        return "generic"
    if page_domain and page_domain.replace("www.", "").split(".")[0] in text:
        return "branded"
    if re.match(r'^[^a-zA-Z]*$', text):
        return "image_or_symbol"
    return "keyword_rich"


def get_backlink_analysis(url: str) -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return {"error": "Missing dependencies. Run: pip install requests beautifulsoup4 lxml"}

    if not url.startswith("http"):
        url = "https://" + url

    parsed      = urlparse(url)
    page_domain = parsed.netloc.lower().replace("www.", "")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    session = requests.Session()
    session.max_redirects = 10

    result = {
        "url":              url,
        "final_url":        url,
        "status_code":      None,
        "page_domain":      page_domain,

        # ── Link counts ──
        "total_links":          0,
        "internal_links":       0,
        "external_links":       0,
        "dofollow_count":       0,
        "nofollow_count":       0,
        "ugc_count":            0,
        "sponsored_count":      0,

        # ── External domains ──
        "unique_external_domains": 0,
        "external_domains":     [],   # [{domain, count, dofollow, nofollow, authority}]

        # ── Anchor text ──
        "anchor_types":         {},   # {keyword_rich, branded, generic, naked_url, empty, image_or_symbol}
        "top_anchors":          [],   # [{text, count, type}]

        # ── Authority ──
        "high_authority_links": 0,
        "medium_authority_links": 0,
        "low_authority_links":  0,
        "authority_domains":    [],   # top 10 by authority score

        # ── Link health ──
        "broken_external":      [],
        "broken_external_count": 0,
        "redirect_external":    [],
        "redirect_external_count": 0,

        # ── Page signals ──
        "last_modified":        None,
        "link_equity_score":    0,    # 0-100

        # ── Overall ──
        "overall_score":        0,
        "passed":               0,
        "total_checks":         0,
        "issues":               [],
        "recommendations":      [],
    }

    # ── Fetch page ───────────────────────────────────────────────
    try:
        t0   = time.time()
        resp = session.get(url, headers=headers, timeout=15, allow_redirects=True)
        ttfb = round((time.time() - t0) * 1000)
    except Exception as e:
        return {**result, "error": f"Could not fetch URL: {e}"}

    result["status_code"] = resp.status_code
    result["final_url"]   = resp.url
    result["last_modified"] = resp.headers.get("Last-Modified", None)

    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception:
        soup = BeautifulSoup(resp.text, "html.parser")

    # ── Parse all <a> tags ────────────────────────────────────────
    all_links     = soup.find_all("a", href=True)
    internal_count = 0
    external_count = 0
    dofollow_count = 0
    nofollow_count = 0
    ugc_count      = 0
    sponsored_count = 0

    domain_map     = defaultdict(lambda: {"count": 0, "dofollow": 0, "nofollow": 0, "anchors": []})
    anchor_counter = Counter()
    anchor_type_map = {}

    for a in all_links:
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        abs_href = urljoin(result["final_url"], href)
        link_parsed = urlparse(abs_href)
        link_domain = link_parsed.netloc.lower().replace("www.", "")

        # Internal vs external
        is_external = link_domain and link_domain != page_domain
        if is_external:
            external_count += 1
        else:
            internal_count += 1
            continue  # Only process external links further

        # Rel attributes
        rel = " ".join(a.get("rel") or []).lower()
        is_nofollow  = "nofollow"  in rel
        is_ugc       = "ugc"       in rel
        is_sponsored = "sponsored" in rel
        is_dofollow  = not is_nofollow

        if is_nofollow:  nofollow_count  += 1
        else:            dofollow_count  += 1
        if is_ugc:       ugc_count       += 1
        if is_sponsored: sponsored_count += 1

        # Anchor text
        anchor_text = a.get_text(separator=" ", strip=True)
        if not anchor_text:
            img = a.find("img")
            anchor_text = img.get("alt", "") if img else ""
        anchor_text = re.sub(r'\s+', ' ', anchor_text).strip()[:120]

        anchor_type = _classify_anchor(anchor_text, page_domain)
        if anchor_text:
            anchor_counter[anchor_text] += 1
            anchor_type_map[anchor_text] = anchor_type

        # Domain tracking
        root = _root_domain(link_domain)
        domain_map[root]["count"]   += 1
        domain_map[root]["anchors"].append(anchor_text[:60])
        if is_dofollow:
            domain_map[root]["dofollow"] += 1
        else:
            domain_map[root]["nofollow"] += 1

    result["total_links"]    = len(all_links)
    result["internal_links"] = internal_count
    result["external_links"] = external_count
    result["dofollow_count"] = dofollow_count
    result["nofollow_count"] = nofollow_count
    result["ugc_count"]      = ugc_count
    result["sponsored_count"] = sponsored_count

    # ── External domains with authority ──────────────────────────
    ext_domain_list = []
    high_auth = medium_auth = low_auth = 0

    for domain, info in domain_map.items():
        auth = _estimate_authority(domain)
        entry = {
            "domain":    domain,
            "count":     info["count"],
            "dofollow":  info["dofollow"],
            "nofollow":  info["nofollow"],
            "anchors":   list(set(info["anchors"]))[:3],
            "authority": auth,
        }
        ext_domain_list.append(entry)
        tier = auth["tier"]
        if tier == "High":          high_auth   += 1
        elif "Medium" in tier:      medium_auth += 1
        else:                       low_auth    += 1

    ext_domain_list.sort(key=lambda x: (-x["authority"]["score"], -x["count"]))
    result["unique_external_domains"] = len(ext_domain_list)
    result["external_domains"]        = ext_domain_list[:30]
    result["high_authority_links"]    = high_auth
    result["medium_authority_links"]  = medium_auth
    result["low_authority_links"]     = low_auth
    result["authority_domains"]       = ext_domain_list[:10]

    # ── Anchor text summary ───────────────────────────────────────
    type_counts = Counter()
    for text, atype in anchor_type_map.items():
        type_counts[atype] += anchor_counter[text]
    result["anchor_types"] = dict(type_counts)
    result["top_anchors"]  = [
        {"text": t, "count": c, "type": anchor_type_map.get(t, "keyword_rich")}
        for t, c in anchor_counter.most_common(15)
    ]

    # ── Check broken external links (sample up to 10) ──────────────
    checked   = set()
    broken    = []
    redirects = []

    sample_domains = list(domain_map.keys())[:10]  # limit to 10 domains
    for a in all_links:
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_href = urljoin(result["final_url"], href)
        link_domain = _root_domain(urlparse(abs_href).netloc.lower())

        if link_domain not in sample_domains:
            continue
        if abs_href in checked or len(checked) >= 15:
            break
        checked.add(abs_href)

        try:
            lr = session.head(abs_href, headers=headers, timeout=5, allow_redirects=False)
            if lr.status_code in (301, 302, 307, 308):
                location = lr.headers.get("Location", "")
                redirects.append({
                    "url":      abs_href,
                    "status":   lr.status_code,
                    "location": location[:120],
                })
            elif lr.status_code >= 400:
                broken.append({"url": abs_href, "status": lr.status_code})
        except Exception:
            broken.append({"url": abs_href, "status": "timeout"})

    result["broken_external"]          = broken[:10]
    result["broken_external_count"]    = len(broken)
    result["redirect_external"]        = redirects[:10]
    result["redirect_external_count"]  = len(redirects)

    # ── Issues & Recommendations ─────────────────────────────────
    issues = []
    recs   = []

    if external_count == 0:
        issues.append("No external links found — outbound links to authority sites improve trust signals")
        recs.append("Add 2–5 outbound links to relevant high-authority sources")
    if dofollow_count == 0 and external_count > 0:
        issues.append("All external links are nofollow — no link equity being passed")
        recs.append("Keep dofollow links to trusted external sources; only nofollow paid/untrusted links")
    if nofollow_count > dofollow_count and external_count > 0:
        recs.append("Most external links are nofollow — consider adding dofollow links to trusted resources")
    if high_auth == 0 and external_count > 0:
        issues.append("No links to high-authority domains detected")
        recs.append("Link to authoritative sources (Wikipedia, gov, edu, industry leaders) to boost trust")
    if len(broken) > 0:
        issues.append(f"{len(broken)} broken external link(s) found — fix or remove them")
        recs.append("Audit and fix broken external links — they harm UX and crawl signals")
    if type_counts.get("generic", 0) > type_counts.get("keyword_rich", 0):
        recs.append("Too many generic anchors (\"click here\", \"read more\") — use descriptive keyword-rich anchor text")
    if ugc_count > 0:
        recs.append(f"{ugc_count} UGC-tagged link(s) — ensure user-generated content links are properly marked")
    if sponsored_count > 0:
        recs.append(f"{sponsored_count} sponsored link(s) — make sure all paid links use rel=\"sponsored\"")

    result["issues"]          = issues
    result["recommendations"] = recs

    # ── Link equity score (heuristic) ────────────────────────────
    equity = 0
    if external_count > 0:
        equity += min(30, external_count * 3)
    if high_auth > 0:
        equity += min(30, high_auth * 10)
    if medium_auth > 0:
        equity += min(15, medium_auth * 5)
    if dofollow_count > 0:
        equity += min(15, dofollow_count * 3)
    if len(broken) == 0:
        equity += 10
    result["link_equity_score"] = min(100, equity)

    # ── Overall score ────────────────────────────────────────────
    checks = [
        external_count > 0,
        dofollow_count > 0,
        high_auth > 0,
        result["unique_external_domains"] >= 3,
        len(broken) == 0,
        len(redirects) <= 2,
        type_counts.get("keyword_rich", 0) >= type_counts.get("generic", 0),
        nofollow_count <= dofollow_count or external_count == 0,
    ]
    passed = sum(bool(c) for c in checks)
    result["passed"]        = passed
    result["total_checks"]  = len(checks)
    result["overall_score"] = round(passed / len(checks) * 100)

    return result