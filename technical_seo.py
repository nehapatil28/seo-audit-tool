"""
technical_seo.py
----------------
Performs a full Technical SEO audit on a given URL.

Checks:
  1.  HTTPS / SSL
  2.  HTTP status code & redirects
  3.  robots.txt  (present, parseable, Sitemap declared)
  4.  sitemap.xml (present, URL count, index vs regular)
  5.  Canonical tag
  6.  Noindex / robots meta
  7.  Mobile-friendly  (viewport meta)
  8.  Server response time (TTFB)
  9.  Crawl errors (broken internal links sampled from sitemap)
  10. Disallowed paths from robots.txt
  11. Open Graph tags
  12. Structured data / Schema.org
  13. Hreflang tags
  14. Pagination (rel=next/prev)
  15. AMP link

Usage:
    from technical_seo import get_technical_seo
    result = get_technical_seo("https://example.com")
"""

import time
import re
from urllib.parse import urljoin, urlparse


def get_technical_seo(url: str) -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return {"error": "Missing dependencies. Run: pip install requests beautifulsoup4 lxml"}

    if not url.startswith("http"):
        url = "https://" + url

    parsed   = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; RankScanBot/1.0; "
            "+https://rankscan.io/bot)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    session = requests.Session()
    session.max_redirects = 10

    result = {
        "url": url,
        # ── Core checks ──
        "https":            False,
        "status_code":      None,
        "redirect_chain":   [],
        "final_url":        url,
        # ── robots.txt ──
        "robots_txt":           False,
        "robots_url":           "",
        "robots_disallow":      [],
        "disallow":             [],
        "declared_in_robots":   False,
        "sitemap_in_robots":    [],
        # ── sitemap.xml ──
        "sitemap_xml":      False,
        "sitemap_url":      "",
        "sitemap_url_count": 0,
        "sitemap_is_index": False,
        # ── on-page ──
        "canonical":        False,
        "canonical_url":    "",
        "noindex":          False,
        "robots_meta":      "",
        "has_viewport":     False,
        "viewport_content": "",
        "mobile_friendly":  False,
        # ── performance ──
        "load_time_ms":     None,
        "load_time_ok":     False,
        # ── crawl errors ──
        "no_crawl_errors":  True,
        "crawl_errors":     [],
        "crawl_error_count": 0,
        # ── structured data ──
        "has_schema":       False,
        "schemas":          [],
        # ── open graph ──
        "has_og":           False,
        "og":               {},
        # ── other ──
        "hreflang":         [],
        "has_hreflang":     False,
        "has_pagination":   False,
        "has_amp":          False,
        "amp_url":          "",
    }

    # ── 1. Fetch the page ──────────────────────────────────────
    try:
        t0   = time.time()
        resp = session.get(url, headers=headers, timeout=15, allow_redirects=True)
        ttfb = round((time.time() - t0) * 1000)
    except requests.exceptions.SSLError:
        result["https"] = False
        result["error_detail"] = "SSL certificate error"
        # Try HTTP fallback
        try:
            http_url = url.replace("https://", "http://")
            resp = session.get(http_url, headers=headers, timeout=15, allow_redirects=True)
            ttfb = round((time.time() - t0) * 1000)
        except Exception as e:
            return {**result, "error": f"Could not fetch URL: {e}"}
    except Exception as e:
        return {**result, "error": f"Could not fetch URL: {e}"}

    result["status_code"]  = resp.status_code
    result["final_url"]    = resp.url
    result["load_time_ms"] = ttfb
    result["load_time_ok"] = ttfb < 600
    result["https"]        = resp.url.startswith("https://")

    # Redirect chain
    if resp.history:
        result["redirect_chain"] = [
            {"url": r.url, "status": r.status_code}
            for r in resp.history
        ]

    if resp.status_code not in (200, 301, 302, 307, 308):
        result["error_detail"] = f"Page returned HTTP {resp.status_code}"

    # Parse HTML
    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception:
        soup = BeautifulSoup(resp.text, "html.parser")

    # ── 2. Canonical ──────────────────────────────────────────
    canonical_tag = soup.find("link", rel=lambda r: r and "canonical" in r)
    if canonical_tag and canonical_tag.get("href"):
        result["canonical"]     = True
        result["canonical_url"] = canonical_tag["href"].strip()

    # ── 3. Robots meta / noindex ──────────────────────────────
    robots_meta = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    if robots_meta:
        content = robots_meta.get("content", "")
        result["robots_meta"] = content
        result["noindex"]     = "noindex" in content.lower()

    # X-Robots-Tag header
    x_robots = resp.headers.get("X-Robots-Tag", "")
    if x_robots and "noindex" in x_robots.lower():
        result["noindex"]     = True
        result["robots_meta"] = result["robots_meta"] or x_robots

    # ── 4. Viewport / mobile-friendly ─────────────────────────
    vp = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    if vp and vp.get("content"):
        result["has_viewport"]     = True
        result["viewport_content"] = vp["content"].strip()
        result["mobile_friendly"]  = "width=device-width" in vp["content"].lower()

    # ── 5. Open Graph ─────────────────────────────────────────
    og_tags = soup.find_all("meta", property=re.compile(r"^og:", re.I))
    if not og_tags:
        og_tags = soup.find_all("meta", attrs={"property": re.compile(r"^og:", re.I)})
    og = {}
    for tag in og_tags:
        prop = (tag.get("property") or "").replace("og:", "")
        if prop and tag.get("content"):
            og[prop] = tag["content"].strip()[:200]
    result["has_og"] = len(og) >= 2
    result["og"]     = og

    # ── 6. Schema.org / JSON-LD ───────────────────────────────
    schema_types = set()
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            ld = json.loads(script.string or "")
            if isinstance(ld, list):
                for item in ld:
                    if isinstance(item, dict) and item.get("@type"):
                        t = item["@type"]
                        schema_types.update(t if isinstance(t, list) else [t])
            elif isinstance(ld, dict):
                if ld.get("@type"):
                    t = ld["@type"]
                    schema_types.update(t if isinstance(t, list) else [t])
                # Check @graph
                for item in ld.get("@graph", []):
                    if isinstance(item, dict) and item.get("@type"):
                        t = item["@type"]
                        schema_types.update(t if isinstance(t, list) else [t])
        except Exception:
            pass

    # Microdata
    for el in soup.find_all(attrs={"itemtype": True}):
        itype = el.get("itemtype", "")
        m = re.search(r"schema\.org/(\w+)", itype)
        if m:
            schema_types.add(m.group(1))

    result["schemas"]    = sorted(schema_types)
    result["has_schema"] = len(schema_types) > 0

    # ── 7. Hreflang ───────────────────────────────────────────
    hreflang_tags = soup.find_all("link", rel="alternate", hreflang=True)
    hreflangs = [{"lang": t.get("hreflang",""), "url": t.get("href","")} for t in hreflang_tags]
    result["hreflang"]     = hreflangs
    result["has_hreflang"] = len(hreflangs) > 0

    # ── 8. Pagination ─────────────────────────────────────────
    result["has_pagination"] = bool(
        soup.find("link", rel="next") or soup.find("link", rel="prev")
    )

    # ── 9. AMP ────────────────────────────────────────────────
    amp_link = soup.find("link", rel="amphtml")
    if amp_link and amp_link.get("href"):
        result["has_amp"] = True
        result["amp_url"] = amp_link["href"].strip()

    # ── 10. robots.txt ────────────────────────────────────────
    robots_url = urljoin(base_url, "/robots.txt")
    result["robots_url"] = robots_url
    disallowed   = []
    sitemap_urls = []
    try:
        rb = session.get(robots_url, headers=headers, timeout=8)
        if rb.status_code == 200 and rb.text.strip():
            result["robots_txt"] = True
            for line in rb.text.splitlines():
                line = line.strip()
                if line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path:
                        disallowed.append(path)
                elif line.lower().startswith("sitemap:"):
                    sm_url = line.split(":", 1)[1].strip()
                    if sm_url:
                        sitemap_urls.append(sm_url)
                        result["declared_in_robots"] = True
    except Exception:
        pass

    result["robots_disallow"]   = disallowed[:20]
    result["disallow"]          = disallowed[:20]
    result["sitemap_in_robots"] = sitemap_urls

    # ── 11. sitemap.xml ───────────────────────────────────────
    # Use sitemap from robots.txt first, then guess common paths
    sm_candidates = sitemap_urls or [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
        urljoin(base_url, "/sitemap/sitemap.xml"),
    ]

    for sm_url in sm_candidates[:3]:
        try:
            sr = session.get(sm_url, headers=headers, timeout=10)
            if sr.status_code == 200 and sr.text.strip().startswith("<?xml"):
                result["sitemap_xml"]  = True
                result["sitemap_url"]  = sm_url
                sm_soup = BeautifulSoup(sr.text, "xml")
                # Sitemap index
                if sm_soup.find("sitemapindex"):
                    result["sitemap_is_index"]  = True
                    result["sitemap_url_count"] = len(sm_soup.find_all("sitemap"))
                else:
                    result["sitemap_url_count"] = len(sm_soup.find_all("url"))
                break
        except Exception:
            continue

    # ── 12. Crawl errors (sample internal links) ──────────────
    internal_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_href = urljoin(result["final_url"], href)
        if urlparse(abs_href).netloc == parsed.netloc:
            internal_links.append(abs_href)

    # Check up to 8 internal links for crawl errors
    crawl_errors = []
    seen = set()
    for link in internal_links[:20]:
        if link in seen or len(crawl_errors) >= 8:
            break
        seen.add(link)
        try:
            lr = session.head(link, headers=headers, timeout=5, allow_redirects=True)
            if lr.status_code in (404, 410, 500, 502, 503):
                crawl_errors.append({"url": link, "status": lr.status_code})
        except Exception:
            pass

    result["crawl_errors"]     = crawl_errors
    result["crawl_error_count"] = len(crawl_errors)
    result["no_crawl_errors"]  = len(crawl_errors) == 0

    # ── 13. Compute overall score ─────────────────────────────
    checks = [
        result["https"],
        result["robots_txt"],
        result["sitemap_xml"],
        result["canonical"],
        not result["noindex"],
        result["mobile_friendly"],
        result["load_time_ok"],
        result["no_crawl_errors"],
        result["has_schema"],
        result["has_og"],
    ]
    passed = sum(bool(c) for c in checks)
    result["passed"]       = passed
    result["total_checks"] = len(checks)
    result["score"]        = round(passed / len(checks) * 100)

    return result