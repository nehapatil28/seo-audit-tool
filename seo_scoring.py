from __future__ import annotations
from typing import Any


# ── Weight distribution ────────────────────────────────────────────────────
WEIGHT_CONTENT   = 0.30   # 30 %
WEIGHT_SPEED     = 0.30   # 30 %
WEIGHT_LINKS     = 0.20   # 20 %
WEIGHT_TECHNICAL = 0.20   # 20 %


# ══════════════════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════════════════

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _score_label(score: float) -> str:
    if score >= 80:
        return "Good"
    if score >= 50:
        return "Needs Work"
    return "Poor"


# ══════════════════════════════════════════════════════════════════════════
#  SECTION SCORERS
# ══════════════════════════════════════════════════════════════════════════

def score_content(seo: dict[str, Any]) -> dict[str, Any]:
    """
    Score the Content pillar (0-100) from on-page SEO data.

    Checks:
      • Title tag present + length ok        (15 pts)
      • Meta description present + length ok (15 pts)
      • H1 present + single H1 rule          (10 pts)
      • Word count ≥ 300                     (20 pts)
      • Readability score ≥ 50               (15 pts)
      • Primary keyword detected             (10 pts)
      • Images have alt text                 (10 pts)
      • No duplicate content                 ( 5 pts)
    """
    issues  : list[str] = []
    passed  : list[str] = []
    raw = 0.0

    t   = seo.get("title",            {})
    m   = seo.get("meta_description", {})
    h   = seo.get("headings",         {})
    c   = seo.get("content",          {})
    img = seo.get("images",           {})

    # Title (15 pts)
    if t.get("present") and t.get("length_ok"):
        raw += 15
        passed.append("Title tag present and correct length (30-60 chars)")
    elif t.get("present"):
        raw += 7
        issues.append(f"Title length not optimal — {t.get('length', 0)} chars (ideal 30-60)")
    else:
        issues.append("Title tag missing")

    # Meta description (15 pts)
    if m.get("present") and m.get("length_ok"):
        raw += 15
        passed.append("Meta description present and correct length (120-160 chars)")
    elif m.get("present"):
        raw += 7
        issues.append(f"Meta description length not optimal — {m.get('length', 0)} chars (ideal 120-160)")
    else:
        issues.append("Meta description missing")

    # H1 (10 pts)
    if h.get("h1_present") and h.get("single_h1"):
        raw += 10
        passed.append("Single H1 tag present")
    elif h.get("h1_present"):
        raw += 5
        issues.append(f"Multiple H1 tags found ({h.get('h1_count', 0)}) — keep only one")
    else:
        issues.append("H1 tag missing")

    # Word count (20 pts)
    wc = c.get("word_count", 0)
    if wc >= 800:
        raw += 20
        passed.append(f"Word count excellent — {wc} words")
    elif wc >= 300:
        raw += 12
        issues.append(f"Word count low — {wc} words (ideal 800+)")
    else:
        issues.append(f"Word count too low — {wc} words (minimum 300)")

    # Readability (15 pts)
    rs = c.get("readability_score", 0)
    if rs >= 70:
        raw += 15
        passed.append(f"Readability excellent — {rs}/100")
    elif rs >= 50:
        raw += 9
        issues.append(f"Readability average — {rs}/100 (aim for 70+)")
    else:
        issues.append(f"Readability poor — {rs}/100 (use shorter sentences)")

    # Primary keyword (10 pts)
    kws = c.get("keywords", [])
    if kws:
        kw0 = kws[0]
        density = kw0.get("density", 0)
        if 0.5 <= density <= 3.0:
            raw += 10
            passed.append(f"Primary keyword '{kw0.get('word','')}' at {density}% density")
        else:
            raw += 5
            issues.append(f"Keyword density {density}% — ideal 0.5-3%")
    else:
        issues.append("No primary keyword detected")

    # Alt text (10 pts)
    total_imgs   = img.get("total", 0)
    missing_alts = img.get("missing_alt_count", 0)
    if total_imgs == 0 or missing_alts == 0:
        raw += 10
        passed.append("All images have alt text" if total_imgs > 0 else "No images (alt check skipped)")
    else:
        frac = 1 - (missing_alts / total_imgs)
        raw += round(10 * frac, 1)
        issues.append(f"{missing_alts} of {total_imgs} images missing alt text")

    # Duplicate content (5 pts)
    if not c.get("duplicate_content"):
        raw += 5
        passed.append("No duplicate content detected")
    else:
        issues.append("Possible duplicate content detected")

    score = _clamp(raw)
    return {
        "score":  round(score, 1),
        "label":  _score_label(score),
        "passed": passed,
        "issues": issues,
    }


def score_speed(pagespeed: dict[str, Any]) -> dict[str, Any]:
    """
    Score the Speed pillar (0-100) using real Google PageSpeed / Lighthouse data.

    The Lighthouse performance_score (0-100) is the authoritative base.
    Core Web Vitals (LCP, CLS, TBT) are verified against Google's exact thresholds
    and can add bonus pts or trigger pass/fail notes — but the final score is
    anchored to the real Lighthouse number, not a made-up calculation.

    Google's thresholds:
      LCP  — Good ≤ 2.5 s   |  Needs Work ≤ 4.0 s  |  Poor > 4.0 s
      CLS  — Good ≤ 0.1     |  Needs Work ≤ 0.25    |  Poor > 0.25
      TBT  — Good ≤ 200 ms  |  Needs Work ≤ 600 ms  |  Poor > 600 ms
      FCP  — Good ≤ 1.8 s   |  Needs Work ≤ 3.0 s   |  Poor > 3.0 s
      SI   — Good ≤ 3.4 s   |  Needs Work ≤ 5.8 s   |  Poor > 5.8 s
      TTI  — Good ≤ 3.8 s   |  Needs Work ≤ 7.3 s   |  Poor > 7.3 s
    """
    issues : list[str] = []
    passed : list[str] = []

    perf = pagespeed.get("performance_score")

    # ── No real data yet ──
    if perf is None or perf == "":
        return {
            "score":  0.0,
            "label":  "No Data",
            "passed": [],
            "issues": ["PageSpeed data not yet available — run Page Speed tab first"],
        }

    # treat 0 performance score as real (a site can legitimately score 0)
    score = float(perf)

    # ── LCP — Largest Contentful Paint ──
    lcp_ms = pagespeed.get("lcp_ms", 0) or 0
    if lcp_ms > 0:
        lcp_s = lcp_ms / 1000
        if lcp_ms <= 2500:
            passed.append(f"LCP Good — {lcp_s:.1f}s (Google threshold: ≤ 2.5s)")
        elif lcp_ms <= 4000:
            issues.append(f"LCP Needs Work — {lcp_s:.1f}s (Good ≤ 2.5s, Poor > 4.0s)")
        else:
            issues.append(f"LCP Poor — {lcp_s:.1f}s (Google: Poor > 4.0s) ❌")
    else:
        issues.append("LCP — no data")

    # ── CLS — Cumulative Layout Shift ──
    cls = pagespeed.get("cls")
    if cls is not None and cls != "":
        cls = float(cls)
        if cls <= 0.1:
            passed.append(f"CLS Good — {cls:.3f} (Google threshold: ≤ 0.1)")
        elif cls <= 0.25:
            issues.append(f"CLS Needs Work — {cls:.3f} (Good ≤ 0.1, Poor > 0.25)")
        else:
            issues.append(f"CLS Poor — {cls:.3f} (Google: Poor > 0.25) ❌")
    else:
        issues.append("CLS — no data")

    # ── TBT — Total Blocking Time ──
    tbt_ms = pagespeed.get("tbt_ms", 0) or 0
    if tbt_ms > 0 or "tbt_ms" in pagespeed:
        if tbt_ms <= 200:
            passed.append(f"TBT Good — {tbt_ms}ms (Google threshold: ≤ 200ms)")
        elif tbt_ms <= 600:
            issues.append(f"TBT Needs Work — {tbt_ms}ms (Good ≤ 200ms, Poor > 600ms)")
        else:
            issues.append(f"TBT Poor — {tbt_ms}ms (Google: Poor > 600ms) ❌")
    else:
        issues.append("TBT — no data")

    # ── Render-blocking resources ──
    rb = pagespeed.get("render_blocking_count", 0) or 0
    if rb == 0:
        passed.append("No render-blocking resources")
    elif rb <= 2:
        issues.append(f"{rb} render-blocking resource(s) — consider deferring")
    else:
        issues.append(f"{rb} render-blocking resources — eliminate to improve FCP ❌")

    # ── Overall label based on Lighthouse score ──
    if score >= 90:
        label_detail = "Fast (90-100)"
    elif score >= 50:
        label_detail = "Moderate (50-89)"
    else:
        label_detail = "Slow (0-49)"

    passed.insert(0, f"Lighthouse Performance score: {int(score)}/100 — {label_detail}")

    score = _clamp(score)
    return {
        "score":  round(score, 1),
        "label":  _score_label(score),
        "passed": passed,
        "issues": issues,
    }


def score_links(links: dict[str, Any]) -> dict[str, Any]:
    """
    Score the Links pillar (0-100).

    Checks:
      • Internal links count      (25 pts)
      • External links count      (15 pts)
      • No broken links           (40 pts)
      • No-follow ratio ok        (10 pts)
      • Top anchors exist         (10 pts)
    """
    issues : list[str] = []
    passed : list[str] = []
    raw = 0.0

    internal = links.get("internal_count", 0) or 0
    external = links.get("external_count", 0) or 0
    broken   = links.get("broken_count",   0) or 0
    nofollow = links.get("nofollow_count", 0) or 0
    total    = internal + external or 1
    anchors  = links.get("top_anchors", [])

    # Internal links (25 pts)
    if internal >= 10:
        raw += 25
        passed.append(f"Good internal link count — {internal}")
    elif internal >= 3:
        raw += 15
        issues.append(f"Low internal link count — {internal} (aim for 10+)")
    else:
        raw += 5
        issues.append(f"Very few internal links — {internal}")

    # External links (15 pts)
    if external >= 3:
        raw += 15
        passed.append(f"External links present — {external}")
    elif external >= 1:
        raw += 8
        issues.append(f"Few external links — {external} (aim for 3+)")
    else:
        issues.append("No external links found")

    # Broken links (40 pts)
    if broken == 0:
        raw += 40
        passed.append("No broken links")
    else:
        penalty = min(40, broken * 8)
        raw += max(0, 40 - penalty)
        issues.append(f"{broken} broken link(s) — fix immediately")

    # Nofollow ratio (10 pts)
    nf_ratio = nofollow / total
    if nf_ratio <= 0.3:
        raw += 10
        passed.append(f"Nofollow ratio acceptable — {round(nf_ratio*100)}%")
    else:
        issues.append(f"High nofollow ratio — {round(nf_ratio*100)}%")

    # Top anchors (10 pts)
    if anchors:
        raw += 10
        passed.append("Anchor text diversity looks good")
    else:
        issues.append("No anchor text data available")

    score = _clamp(raw)
    return {
        "score":  round(score, 1),
        "label":  _score_label(score),
        "passed": passed,
        "issues": issues,
    }


def score_technical(tech: dict[str, Any]) -> dict[str, Any]:
    """
    Score the Technical pillar (0-100).

    Checks:
      • HTTPS enabled             (15 pts)
      • Robots.txt present        (10 pts)
      • Sitemap.xml present       (10 pts)
      • Canonical tag present     (15 pts)
      • Page is indexable         (15 pts)
      • Schema markup present     (15 pts)
      • Open Graph tags present   (10 pts)
      • Mobile-friendly           (10 pts)
    """
    issues : list[str] = []
    passed : list[str] = []
    raw = 0.0

    # HTTPS (15 pts)
    if tech.get("https") or tech.get("https_enabled"):
        raw += 15
        passed.append("HTTPS / SSL enabled")
    else:
        issues.append("HTTPS not detected — migrate to SSL")

    # Robots.txt (10 pts)
    if tech.get("robots_txt") or tech.get("robots_present"):
        raw += 10
        passed.append("robots.txt present")
    else:
        issues.append("robots.txt missing")

    # Sitemap (10 pts)
    if tech.get("sitemap_xml") or tech.get("sitemap_present"):
        raw += 10
        passed.append("sitemap.xml present")
    else:
        issues.append("sitemap.xml missing")

    # Canonical (15 pts)
    if tech.get("canonical") or tech.get("canonical_ok"):
        raw += 15
        passed.append("Canonical tag implemented")
    else:
        issues.append("Canonical tag missing — duplicate content risk")

    # Indexable (15 pts)
    noindex = tech.get("noindex", False)
    if not noindex:
        raw += 15
        passed.append("Page is indexable (no NOINDEX directive)")
    else:
        issues.append("NOINDEX detected — Google will not index this page")

    # Schema (15 pts)
    if tech.get("has_schema"):
        raw += 15
        passed.append("Schema.org structured data present")
    else:
        issues.append("Schema.org markup missing")

    # Open Graph (10 pts)
    if tech.get("has_og"):
        raw += 10
        passed.append("Open Graph tags present")
    else:
        issues.append("Open Graph tags missing — affects social sharing")

    # Mobile-friendly (10 pts)
    if tech.get("mobile_friendly"):
        raw += 10
        passed.append("Mobile-friendly")
    else:
        issues.append("Mobile-friendliness not confirmed")

    score = _clamp(raw)
    return {
        "score":  round(score, 1),
        "label":  _score_label(score),
        "passed": passed,
        "issues": issues,
    }


# ══════════════════════════════════════════════════════════════════════════
#  PAGE-LEVEL SCORE  (0-100)
# ══════════════════════════════════════════════════════════════════════════

def compute_page_score(
    seo_data       : dict[str, Any],
    pagespeed_data : dict[str, Any] | None = None,
    links_data     : dict[str, Any] | None = None,
    tech_data      : dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compute the page-level SEO score (0-100) and per-pillar breakdown.

    Parameters
    ----------
    seo_data       : on-page SEO dict from analyze_onpage()
    pagespeed_data : PageSpeed dict from get_pagespeed()   (optional)
    links_data     : link analysis dict from analyze_links() (optional)
    tech_data      : technical SEO dict from get_technical_seo() (optional)

    Returns
    -------
    {
        "page_score": float,
        "label":      str,
        "breakdown": {
            "Content":   {"score": float, "label": str, "passed": [...], "issues": [...]},
            "Speed":     {...},
            "Links":     {...},
            "Technical": {...},
        },
        "weighted": {
            "Content":   float,   # contribution to final score
            "Speed":     float,
            "Links":     float,
            "Technical": float,
        }
    }
    """
    # ── Pillar scores ──
    content_result   = score_content(seo_data)
    speed_result     = score_speed(pagespeed_data if pagespeed_data is not None else {})
    links_result     = score_links(links_data if links_data is not None else {})
    technical_result = score_technical(tech_data if tech_data else seo_data)

    c_score = content_result["score"]
    s_score = speed_result["score"]
    l_score = links_result["score"]
    t_score = technical_result["score"]

    # ── Weighted total ──
    weighted_content   = round(c_score * WEIGHT_CONTENT,   2)
    weighted_speed     = round(s_score * WEIGHT_SPEED,     2)
    weighted_links     = round(l_score * WEIGHT_LINKS,     2)
    weighted_technical = round(t_score * WEIGHT_TECHNICAL, 2)

    page_score = _clamp(
        weighted_content + weighted_speed + weighted_links + weighted_technical
    )

    return {
        "page_score": round(page_score, 1),
        "label":      _score_label(page_score),
        "breakdown": {
            "Content":   content_result,
            "Speed":     speed_result,
            "Links":     links_result,
            "Technical": technical_result,
        },
        "weighted": {
            "Content":   weighted_content,
            "Speed":     weighted_speed,
            "Links":     weighted_links,
            "Technical": weighted_technical,
        },
        "weights": {
            "Content":   int(WEIGHT_CONTENT   * 100),
            "Speed":     int(WEIGHT_SPEED     * 100),
            "Links":     int(WEIGHT_LINKS     * 100),
            "Technical": int(WEIGHT_TECHNICAL * 100),
        },
    }


# ══════════════════════════════════════════════════════════════════════════
#  WEBSITE OVERALL SCORE  (average across pages)
# ══════════════════════════════════════════════════════════════════════════

def compute_website_score(page_results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute the website overall SEO score from a list of page results.

    Each element of page_results must be the return value of compute_page_score()
    optionally augmented with a "url" key.

    Returns
    -------
    {
        "website_score":  float,
        "label":          str,
        "total_pages":    int,
        "pillar_averages": {
            "Content":   float,
            "Speed":     float,
            "Links":     float,
            "Technical": float,
        },
        "weighted_averages": {
            "Content":   float,
            "Speed":     float,
            "Links":     float,
            "Technical": float,
        },
        "weights": {
            "Content":   30,
            "Speed":     30,
            "Links":     20,
            "Technical": 20,
        },
        "pages": [  # per-page summary
            {"url": str, "page_score": float, "label": str, ...}
        ]
    }
    """
    if not page_results:
        return {
            "website_score":     0.0,
            "label":             "Poor",
            "total_pages":       0,
            "pillar_averages":   {"Content": 0, "Speed": 0, "Links": 0, "Technical": 0},
            "weighted_averages": {"Content": 0, "Speed": 0, "Links": 0, "Technical": 0},
            "weights":           {"Content": 30, "Speed": 30, "Links": 20, "Technical": 20},
            "pages":             [],
        }

    n = len(page_results)

    # Sum per pillar
    sums = {"Content": 0.0, "Speed": 0.0, "Links": 0.0, "Technical": 0.0}
    pages_summary = []

    for pr in page_results:
        bd = pr.get("breakdown", {})
        for pillar in sums:
            sums[pillar] += bd.get(pillar, {}).get("score", 0.0)

        pages_summary.append({
            "url":        pr.get("url", ""),
            "page_score": pr.get("page_score", 0.0),
            "label":      pr.get("label", "Poor"),
            "breakdown":  {p: bd.get(p, {}).get("score", 0) for p in sums},
        })

    pillar_avgs = {p: round(sums[p] / n, 1) for p in sums}

    weighted_avgs = {
        "Content":   round(pillar_avgs["Content"]   * WEIGHT_CONTENT,   2),
        "Speed":     round(pillar_avgs["Speed"]      * WEIGHT_SPEED,     2),
        "Links":     round(pillar_avgs["Links"]      * WEIGHT_LINKS,     2),
        "Technical": round(pillar_avgs["Technical"]  * WEIGHT_TECHNICAL, 2),
    }

    website_score = _clamp(sum(weighted_avgs.values()))

    return {
        "website_score":     round(website_score, 1),
        "label":             _score_label(website_score),
        "total_pages":       n,
        "pillar_averages":   pillar_avgs,
        "weighted_averages": weighted_avgs,
        "weights": {
            "Content":   int(WEIGHT_CONTENT   * 100),
            "Speed":     int(WEIGHT_SPEED     * 100),
            "Links":     int(WEIGHT_LINKS     * 100),
            "Technical": int(WEIGHT_TECHNICAL * 100),
        },
        "pages": pages_summary,
    }