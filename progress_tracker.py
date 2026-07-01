"""
progress_tracker.py — AI-powered SEO Progress Tracker (Agent 4)

Compares two audits of the same site and generates a natural language
progress report: what improved, what regressed, what still needs work.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_CHATBOT_KEY") or os.getenv("GROQ_API_KEY", "").strip() or None
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


def _extract_metrics(audit: dict, issues: list) -> dict:
    """Pull key comparable metrics from an audit."""
    pages = audit.get("pages", [])
    n     = len(pages) or 1

    errors   = sum(1 for i in issues if i.get("type") in ("error", "critical"))
    warnings = sum(1 for i in issues if i.get("type") == "warning")

    return {
        "seo_score":      audit.get("seo_score"),
        "page_count":     len(pages),
        "errors":         errors,
        "warnings":       warnings,
        "missing_h1":     sum(1 for p in pages if not p.get("h1_count")),
        "bad_title":      sum(1 for p in pages if not p.get("title_ok")),
        "bad_meta":       sum(1 for p in pages if not p.get("meta_ok")),
        "alt_missing":    sum(p.get("alt_missing", 0) for p in pages),
        "broken_links":   sum(p.get("broken_links", 0) for p in pages),
        "broken_images":  sum(p.get("broken_images", 0) for p in pages),
        "avg_word_count": round(sum(p.get("word_count", 0) for p in pages) / n, 0),
        "noindex_pages":  sum(1 for p in pages if p.get("noindex")),
        "orphan_pages":   sum(1 for p in pages if p.get("is_orphan")),
    }


def _build_comparison_prompt(url: str, old_m: dict, new_m: dict,
                              old_date: str, new_date: str) -> str:
    def delta(key, good_direction="down"):
        o, n = old_m.get(key), new_m.get(key)
        if o is None or n is None:
            return "N/A"
        diff = n - o
        if diff == 0:
            return f"{n} (no change)"
        sign  = "+" if diff > 0 else ""
        arrow = ""
        if good_direction == "down":
            arrow = "✅" if diff < 0 else "🔴"
        else:
            arrow = "✅" if diff > 0 else "🔴"
        return f"{n} ({sign}{diff}) {arrow}"

    lines = [
        f"You are an expert SEO analyst. Compare these two audits for {url} and write a clear progress report.",
        f"",
        f"AUDIT 1 (older): {old_date}",
        f"AUDIT 2 (newer): {new_date}",
        f"",
        f"METRIC COMPARISON:",
        f"SEO Score        : {delta('seo_score', 'up')}",
        f"Total Errors     : {delta('errors', 'down')}",
        f"Total Warnings   : {delta('warnings', 'down')}",
        f"Pages Crawled    : {delta('page_count', 'up')}",
        f"Missing H1       : {delta('missing_h1', 'down')}",
        f"Bad Titles       : {delta('bad_title', 'down')}",
        f"Bad Meta Desc    : {delta('bad_meta', 'down')}",
        f"Alt Text Missing : {delta('alt_missing', 'down')}",
        f"Broken Links     : {delta('broken_links', 'down')}",
        f"Broken Images    : {delta('broken_images', 'down')}",
        f"Avg Word Count   : {delta('avg_word_count', 'up')}",
        f"Noindex Pages    : {delta('noindex_pages', 'down')}",
        f"Orphan Pages     : {delta('orphan_pages', 'down')}",
        f"",
        f"Write a progress report with these EXACT sections:",
        f"",
        f"## 🏆 Overall Progress",
        f"One paragraph summary — is the site improving, declining, or stagnant?",
        f"",
        f"## ✅ What Improved",
        f"Bullet list of specific metrics that got better. Be precise with numbers.",
        f"",
        f"## 🔴 What Got Worse",
        f"Bullet list of metrics that regressed. If nothing regressed, say so.",
        f"",
        f"## ⚠️ Still Needs Work",
        f"Top 3 issues that remain high even in the new audit.",
        f"",
        f"## 🎯 Next Priority Actions",
        f"Top 3 concrete actions the site owner should do next, ranked by impact.",
        f"",
        f"Be specific, data-driven, and concise. Use the actual numbers. English only.",
    ]
    return "\n".join(lines)


def generate_progress_report(old_audit_id: int, new_audit_id: int) -> dict:
    """
    Compare two audits and return an AI-generated progress report.

    Returns:
        dict with keys: report (str), metrics_old, metrics_new, error
    """
    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY not set in .env", "report": None}

    try:
        from database import get_audit, get_audit_issues

        old_audit  = get_audit(old_audit_id)
        new_audit  = get_audit(new_audit_id)

        if not old_audit or not new_audit:
            return {"error": "One or both audit IDs not found", "report": None}

        url = new_audit.get("url", "unknown")

        old_issues = get_audit_issues(old_audit_id)
        new_issues = get_audit_issues(new_audit_id)

        old_m = _extract_metrics(old_audit, old_issues)
        new_m = _extract_metrics(new_audit, new_issues)

        old_date = old_audit.get("created_at", "unknown date")
        new_date = new_audit.get("created_at", "unknown date")

        prompt = _build_comparison_prompt(url, old_m, new_m, old_date, new_date)

        payload = {
            "model":       GROQ_MODEL,
            "max_tokens":  1500,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": "You are a professional SEO analyst. Always respond in English. Be concise and data-driven."},
                {"role": "user",   "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type":  "application/json",
        }

        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=45)
        data = resp.json()

        if not resp.ok:
            return {"error": f"Groq error {resp.status_code}: {data.get('error',{}).get('message','')}", "report": None}

        report = data["choices"][0]["message"]["content"].strip()

        return {
            "report":      report,
            "metrics_old": old_m,
            "metrics_new": new_m,
            "url":         url,
            "old_date":    old_date,
            "new_date":    new_date,
            "error":       None,
        }

    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc(), "report": None}