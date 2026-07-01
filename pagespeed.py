"""
pagespeed.py — Page Speed Analyzer (Lighthouse)
=================================================
Two modes:
  1. Google PageSpeed Insights API  — if api_key provided
  2. Local Lighthouse CLI           — fallback (no API key needed)

Called from app.py as:
    from pagespeed import get_pagespeed
    result = get_pagespeed(url, api_key=None, strategy="desktop")
"""

import subprocess
import json
import tempfile
import os
import time
import requests as req


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def get_pagespeed(url: str, api_key: str = None, strategy: str = "desktop") -> dict:
    if api_key:
        try:
            return _from_google_api(url, api_key, strategy)
        except Exception as e:
            print(f"[pagespeed] Google API failed: {e} — falling back to Lighthouse")

    return _from_lighthouse(url, strategy)


# ─────────────────────────────────────────────────────────────────────────────
#  MODE 1 — GOOGLE PAGESPEED INSIGHTS API
# ─────────────────────────────────────────────────────────────────────────────

def _from_google_api(url: str, api_key: str, strategy: str) -> dict:
    endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params   = {
        "url":      url,
        "key":      api_key.strip("'\""),   # extra quotes remove karo
        "strategy": strategy,
        "category": ["performance", "accessibility", "best-practices", "seo"],
    }

    last_error = None
    for attempt in range(3):
        try:
            print(f"[pagespeed] Google API attempt {attempt + 1}/3 ...")
            r    = req.get(endpoint, params=params, timeout=60)
            data = r.json()

            if "error" in data:
                raise Exception(data["error"].get("message", "API error"))

            print(f"[pagespeed] Google API success on attempt {attempt + 1}")
            return _parse_lighthouse_json(data.get("lighthouseResult", {}), strategy, source="google_api")

        except req.exceptions.Timeout:
            last_error = f"Timeout on attempt {attempt + 1}"
            print(f"[pagespeed] {last_error}, retrying in 3s...")
            time.sleep(3)
        except req.exceptions.ConnectionError as e:
            last_error = f"Connection error: {e}"
            print(f"[pagespeed] {last_error}, retrying in 3s...")
            time.sleep(3)

    raise Exception(f"Google API failed after 3 attempts: {last_error}")


# ─────────────────────────────────────────────────────────────────────────────
#  MODE 2 — LOCAL LIGHTHOUSE CLI
# ─────────────────────────────────────────────────────────────────────────────

def _from_lighthouse(url: str, strategy: str) -> dict:
    t0 = time.time()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        output_path = f.name

    try:
        form_factor = "mobile" if strategy == "mobile" else "desktop"

        cmd = [
            "lighthouse",
            url,
            "--output=json",
            f"--output-path={output_path}",
            f"--form-factor={form_factor}",
            "--chrome-flags=--headless --no-sandbox --disable-gpu",
            "--only-categories=performance,accessibility,best-practices,seo",
            "--quiet",
        ]

        if strategy == "mobile":
            cmd += [
                "--screenEmulation.mobile=true",
                "--screenEmulation.width=390",
                "--screenEmulation.height=844",
                "--screenEmulation.deviceScaleFactor=3",
            ]
        else:
            cmd += [
                "--screenEmulation.mobile=false",
                "--screenEmulation.width=1350",
                "--screenEmulation.height=940",
                "--screenEmulation.deviceScaleFactor=1",
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            shell=True,
        )

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception(f"Lighthouse produced no output. stderr: {result.stderr[:300]}")

        with open(output_path, "r", encoding="utf-8") as f:
            lh_data = json.load(f)

        elapsed = round((time.time() - t0) * 1000)
        parsed  = _parse_lighthouse_json(lh_data, strategy, source="lighthouse")
        parsed["elapsed_ms"] = elapsed
        return parsed

    finally:
        try:
            os.unlink(output_path)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  SHARED PARSER
# ─────────────────────────────────────────────────────────────────────────────

def _parse_lighthouse_json(lh: dict, strategy: str, source: str) -> dict:
    cats   = lh.get("categories", {})
    audits = lh.get("audits", {})

    def score(key):
        c = cats.get(key, {}).get("score")
        return round(c * 100) if c is not None else None

    def ms(audit_key):
        v = audits.get(audit_key, {}).get("numericValue")
        return round(v) if v is not None else None

    def kb(audit_key):
        v = audits.get(audit_key, {}).get("numericValue")
        return round(v / 1024, 1) if v is not None else None

    def display(audit_key):
        return audits.get(audit_key, {}).get("displayValue", "")

    def _resource_kb(resource_type):
        items = audits.get("resource-summary", {}).get("details", {}).get("items", [])
        for item in items:
            if item.get("resourceType") == resource_type:
                return round(item.get("transferSize", 0) / 1024, 1)
        return 0

    rb_items = audits.get("render-blocking-resources", {}).get("details", {}).get("items", [])
    rb_list  = [{"url": i.get("url", ""), "savings_ms": round(i.get("wastedMs", 0))} for i in rb_items]

    ll_items = audits.get("offscreen-images", {}).get("details", {}).get("items", [])
    ll_list  = [{"url": i.get("url", i.get("label", "")), "savings_kb": round(i.get("wastedBytes", 0) / 1024, 1)} for i in ll_items]

    opp_keys = [
        "unused-javascript", "unused-css-rules", "uses-optimized-images",
        "uses-webp-images", "uses-text-compression", "uses-responsive-images",
        "efficient-animated-content", "duplicated-javascript",
        "legacy-javascript", "uses-long-cache-ttl",
    ]
    opps = []
    for k in opp_keys:
        a = audits.get(k, {})
        if a and a.get("score") is not None and a["score"] < 1:
            savings = a.get("details", {}).get("overallSavingsMs") or a.get("numericValue") or 0
            opps.append({
                "id":          k,
                "title":       a.get("title", k),
                "description": a.get("description", ""),
                "savings_ms":  round(savings),
                "display":     a.get("displayValue", ""),
            })

    lcp_ms  = ms("largest-contentful-paint")
    fcp_ms  = ms("first-contentful-paint")
    cls_val = audits.get("cumulative-layout-shift", {}).get("numericValue")
    tbt_ms  = ms("total-blocking-time")
    ttfb_ms = ms("server-response-time")
    si_ms   = ms("speed-index")
    tti_ms  = ms("interactive")

    def lcp_rating(v):
        if v is None: return None
        return "good" if v <= 2500 else "needs-improvement" if v <= 4000 else "poor"

    def fcp_rating(v):
        if v is None: return None
        return "good" if v <= 1800 else "needs-improvement" if v <= 3000 else "poor"

    def cls_rating(v):
        if v is None: return None
        return "good" if v <= 0.1 else "needs-improvement" if v <= 0.25 else "poor"

    def tbt_rating(v):
        if v is None: return None
        return "good" if v <= 200 else "needs-improvement" if v <= 600 else "poor"

    def ttfb_rating(v):
        if v is None: return None
        return "good" if v <= 800 else "needs-improvement" if v <= 1800 else "poor"

    return {
        "performance_score":    score("performance"),
        "accessibility_score":  score("accessibility"),
        "best_practices_score": score("best-practices"),
        "seo_score":            score("seo"),

        "lcp_ms":   lcp_ms,
        "fcp_ms":   fcp_ms,
        "cls":      round(cls_val, 3) if cls_val is not None else None,
        "tbt_ms":   tbt_ms,
        "ttfb_ms":  ttfb_ms,
        "si_ms":    si_ms,
        "tti_ms":   tti_ms,

        "lcp_display":  display("largest-contentful-paint"),
        "fcp_display":  display("first-contentful-paint"),
        "cls_display":  display("cumulative-layout-shift"),
        "tbt_display":  display("total-blocking-time"),
        "si_display":   display("speed-index"),
        "tti_display":  display("interactive"),
        "ttfb_display": display("server-response-time"),

        "lcp_rating":  lcp_rating(lcp_ms),
        "fcp_rating":  fcp_rating(fcp_ms),
        "cls_rating":  cls_rating(cls_val),
        "tbt_rating":  tbt_rating(tbt_ms),
        "ttfb_rating": ttfb_rating(ttfb_ms),

        "total_html_kb": _resource_kb("document"),
        "total_js_kb":   _resource_kb("script"),
        "total_css_kb":  _resource_kb("stylesheet"),
        "total_img_kb":  _resource_kb("image"),
        "total_font_kb": _resource_kb("font"),
        "page_size_kb":  _resource_kb("total"),
        "total_requests": sum(
            1 for i in audits.get("resource-summary", {}).get("details", {}).get("items", [])
            if i.get("resourceType") != "total"
        ),

        "unused_js_kb":  kb("unused-javascript"),
        "unused_css_kb": kb("unused-css-rules"),

        "render_blocking_count":     len(rb_list),
        "render_blocking_resources": rb_list,
        "lazy_loading_issues":       ll_list,
        "opportunities":             opps,

        "strategy": strategy,
        "source":   source,
    }