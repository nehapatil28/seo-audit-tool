"""
linkanalysis.py — Complete Link Analysis Module
- Internal / External link counts
- Broken link detection
- Anchor text analysis
- Link depth analysis
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import Counter
import concurrent.futures
import re


def normalize_url(url):
    return url.rstrip("/").lower().split("#")[0].split("?")[0]


def is_internal(href, domain):
    parsed = urlparse(href)
    return parsed.netloc == "" or parsed.netloc == domain or parsed.netloc == "www." + domain or "www." + parsed.netloc == domain


def check_link_status(args):
    """Check if a URL is alive — used in thread pool."""
    url, headers = args
    try:
        resp = requests.head(url, headers=headers, timeout=8, allow_redirects=True)
        if resp.status_code == 405:
            # HEAD not allowed, try GET
            resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True, stream=True)
        return {
            "url":    url,
            "status": resp.status_code,
            "ok":     resp.status_code < 400,
            "broken": resp.status_code >= 400,
        }
    except Exception as e:
        return {
            "url":    url,
            "status": "error",
            "ok":     False,
            "broken": True,
            "error":  str(e)[:100],
        }


def analyze_links(url, html, domain, headers, all_page_depths=None, check_broken=True):
    """
    Analyze all links on a single page.
    all_page_depths: dict of {url: depth} from crawler for depth analysis
    """
    soup     = BeautifulSoup(html, "lxml")
    base_url = url

    internal_links = []
    external_links = []
    all_anchors    = []

    seen = set()

    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()
        text = tag.get_text(strip=True) or tag.get("title", "") or tag.get("aria-label", "") or ""
        text = re.sub(r'\s+', ' ', text)[:100]

        # Skip non-HTTP links
        if href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue

        full_url = urljoin(base_url, href).split("#")[0].rstrip("/")
        parsed   = urlparse(full_url)

        if parsed.scheme not in ("http", "https"):
            continue

        link_domain = parsed.netloc

        link_data = {
            "url":         full_url,
            "anchor_text": text if text else "(no text)",
            "nofollow":    "nofollow" in (tag.get("rel") or []),
            "target_blank": tag.get("target") == "_blank",
        }

        if is_internal(full_url, domain):
            link_data["type"] = "internal"
            # Add depth info if available
            if all_page_depths:
                link_data["depth"] = all_page_depths.get(normalize_url(full_url), "?")
            internal_links.append(link_data)
        else:
            link_data["type"]   = "external"
            link_data["domain"] = link_domain
            external_links.append(link_data)

        all_anchors.append(text if text else "(no text)")

    # ── Anchor Text Analysis ──
    anchor_counts = Counter(a for a in all_anchors if a != "(no text)")
    top_anchors   = [{"text": t, "count": c} for t, c in anchor_counts.most_common(15)]

    # Count generic anchors
    generic_anchors = ["click here", "read more", "here", "learn more",
                       "more", "link", "this", "page", "website", "visit"]
    generic_count   = sum(1 for a in all_anchors if a.lower() in generic_anchors)
    nofollow_count  = sum(1 for l in internal_links + external_links if l.get("nofollow"))

    # ── Broken Link Detection (parallel HEAD requests) ──
    broken_links = []
    if check_broken:
        all_urls_to_check = list({l["url"] for l in internal_links + external_links})
        # Limit to 30 per page for speed
        all_urls_to_check = all_urls_to_check[:30]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(
                check_link_status,
                [(u, headers) for u in all_urls_to_check]
            ))

        broken_links = [r for r in results if r["broken"]]

        # Tag broken status on links
        broken_set = {r["url"] for r in broken_links}
        for l in internal_links + external_links:
            if l["url"] in broken_set:
                l["broken"] = True

    # ── External domain breakdown ──
    ext_domains = Counter(l.get("domain", "") for l in external_links)
    top_ext_domains = [{"domain": d, "count": c} for d, c in ext_domains.most_common(10)]

    # ── Link depth distribution (internal links only) ──
    depth_dist = {}
    if all_page_depths:
        for l in internal_links:
            d = str(l.get("depth", "?"))
            depth_dist[d] = depth_dist.get(d, 0) + 1

    return {
        "url": url,

        # Counts
        "internal_count":  len(internal_links),
        "external_count":  len(external_links),
        "total_links":     len(internal_links) + len(external_links),
        "broken_count":    len(broken_links),
        "nofollow_count":  nofollow_count,
        "generic_anchor_count": generic_count,

        # Link lists
        "internal_links":  internal_links[:50],   # top 50 for UI
        "external_links":  external_links[:50],
        "broken_links":    broken_links[:20],

        # Analysis
        "top_anchors":     top_anchors,
        "top_ext_domains": top_ext_domains,
        "depth_distribution": depth_dist,

        # Issues
        "issues": _get_issues(len(internal_links), len(external_links),
                              len(broken_links), generic_count, nofollow_count),
    }


def _get_issues(internal, external, broken, generic, nofollow):
    issues = []
    if broken > 0:
        issues.append({"type": "error",   "msg": f"{broken} broken link(s) found — fix immediately"})
    if internal < 3:
        issues.append({"type": "warning", "msg": f"Only {internal} internal links — add more for better crawlability"})
    if external > 50:
        issues.append({"type": "warning", "msg": f"{external} external links — too many may dilute link equity"})
    if generic > 5:
        issues.append({"type": "warning", "msg": f"{generic} generic anchors ('click here', 'read more') — use descriptive text"})
    if nofollow > internal * 0.5 and internal > 0:
        issues.append({"type": "info",    "msg": f"{nofollow} nofollow links — check if intentional"})
    return issues


def analyze_site_links(pages, domain, headers):
    """
    Site-wide link analysis across all crawled pages.
    pages: list of dicts with {url, depth, content (html)}
    """
    all_internal   = []
    all_external   = []
    all_broken     = []
    all_anchors    = []
    page_results   = []

    # Build depth map
    depth_map = {normalize_url(p["url"]): p.get("depth", 0) for p in pages}

    for page in pages:
        if not page.get("content") or page.get("category") != "ok":
            continue
        result = analyze_links(
            page["url"], page["content"], domain, headers,
            all_page_depths=depth_map, check_broken=False
        )
        page_results.append(result)
        all_internal.extend(result["internal_links"])
        all_external.extend(result["external_links"])
        all_anchors.extend([a["anchor_text"] for a in result["internal_links"] + result["external_links"]])

    # Site-wide anchor text
    anchor_counts   = Counter(a for a in all_anchors if a not in ("(no text)", ""))
    top_anchors     = [{"text": t, "count": c} for t, c in anchor_counts.most_common(20)]

    # Site-wide external domains
    ext_domains     = Counter(l.get("domain","") for l in all_external if l.get("domain"))
    top_ext_domains = [{"domain": d, "count": c} for d, c in ext_domains.most_common(15)]

    # Depth distribution of all internal links
    depth_dist = {}
    for l in all_internal:
        d = str(l.get("depth", "?"))
        depth_dist[d] = depth_dist.get(d, 0) + 1

    # Check broken links site-wide (unique URLs only)
    unique_urls = list({l["url"] for l in all_internal + all_external})[:50]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        broken_results = list(executor.map(
            check_link_status, [(u, headers) for u in unique_urls]
        ))
    all_broken = [r for r in broken_results if r["broken"]]

    return {
        "total_pages_analysed": len(page_results),
        "total_internal":       len(all_internal),
        "total_external":       len(all_external),
        "unique_internal":      len({normalize_url(l["url"]) for l in all_internal}),
        "unique_external":      len({normalize_url(l["url"]) for l in all_external}),
        "broken_links":         all_broken,
        "broken_count":         len(all_broken),
        "top_anchors":          top_anchors,
        "top_ext_domains":      top_ext_domains,
        "depth_distribution":   depth_dist,
        "page_results":         page_results,
    }