"""
seo_chatbot.py — Groq-powered SEO Assistant Chatbot (Agent 3)

Architecture:
  Agent 1 (ai_recommendation.py)  → diagnoses SEO problems
  Agent 2 (content_generator.py)  → generates replacement content
  Agent 3 (this file)             → conversational chatbot with full audit RAG

Features:
  - Floating chat widget visible on every dashboard page
  - Uses current audit data as RAG context (score, issues, pages, speed, mobile)
  - Multi-turn conversation memory (per session)
  - General SEO Q&A + site-specific answers in one agent
  - Powered by Groq (llama-3.3-70b-versatile) — same key as Agent 2
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_CHATBOT_KEY") or os.getenv("GROQ_API_KEY", "").strip() or None
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

# Max messages kept in conversation history (user+assistant pairs)
MAX_HISTORY_TURNS = 10

SYSTEM_PROMPT = """You are SEOBot, an expert SEO assistant embedded inside the SEOBit dashboard.

You have two roles:
1. **Site-specific advisor** — When the user asks about their website, you use the 
   audit context provided to give precise, data-driven answers about their actual 
   scores, issues, and recommendations.
2. **General SEO educator** — For broader SEO questions (best practices, how Google 
   works, schema markup, Core Web Vitals, etc.) you answer from your expertise.

Personality:
- Friendly, concise, and practical — like a senior SEO consultant
- Always cite specific numbers from the audit data when available
- Prioritise actionable advice over theory
- If the user's question is about their site but no audit data is provided yet, 
  politely ask them to run an audit first
- Use bullet points for lists of issues/fixes; prose for explanations
- Keep responses focused — don't dump everything at once

Language: Always respond in English only, regardless of what language the user writes in.
"""


# ── Context Builder ────────────────────────────────────────────────────────────

def build_audit_context(audit_id: int | None) -> str:
    """Pull audit data from DB and format it as a compact RAG context string."""
    if not audit_id:
        return ""

    try:
        from database import (
            get_audit, get_audit_issues, get_seo_score,
            get_mobile_seo, get_backlinks
        )

        audit   = get_audit(audit_id)
        issues  = get_audit_issues(audit_id)
        seo_sc  = get_seo_score(audit_id)
        mobile  = get_mobile_seo(audit_id)
        backlinks = get_backlinks(audit_id)

        if not audit:
            return ""

        # ── Basic audit summary ──
        url        = audit.get("url", "unknown")
        summary    = audit.get("summary") or {}
        pages      = audit.get("pages", [])
        total_pg   = len(pages)

        # Overall SEO score (from seo_score table or summary)
        overall_score = None
        if seo_sc:
            raw = seo_sc.get("result") or seo_sc.get("data")
            if isinstance(raw, str):
                try: raw = json.loads(raw)
                except: raw = {}
            overall_score = (raw or {}).get("overall_score") or (raw or {}).get("score")
        if overall_score is None:
            overall_score = summary.get("seo_score") or audit.get("seo_score")

        # ── Issues summary ──
        errors   = [i for i in issues if i.get("type") in ("error", "critical")]
        warnings = [i for i in issues if i.get("type") == "warning"]

        top_errors   = [f"- [{i.get('category','?')}] {i.get('message','?')} (×{i.get('count',1)})"
                        for i in errors[:8]]
        top_warnings = [f"- [{i.get('category','?')}] {i.get('message','?')} (×{i.get('count',1)})"
                        for i in warnings[:5]]

        # ── Page-level stats ──
        missing_h1   = sum(1 for p in pages if not p.get("h1_count"))
        bad_title    = sum(1 for p in pages if not p.get("title_ok"))
        bad_meta     = sum(1 for p in pages if not p.get("meta_ok"))
        alt_missing  = sum(p.get("alt_missing", 0) for p in pages)

        # ── Mobile ──
        mobile_score = None
        if mobile:
            raw = mobile.get("result") or mobile.get("data")
            if isinstance(raw, str):
                try: raw = json.loads(raw)
                except: raw = {}
            mobile_score = (raw or {}).get("mobile_score") or (raw or {}).get("score")

        # ── Backlinks ──
        bl_count = None
        if backlinks:
            raw = backlinks.get("result") or backlinks.get("data")
            if isinstance(raw, str):
                try: raw = json.loads(raw)
                except: raw = {}
            bl_count = (raw or {}).get("total_backlinks") or (raw or {}).get("count")

        # ── Assemble context string ──
        lines = [
            f"=== CURRENT AUDIT CONTEXT for {url} ===",
            f"Audit ID      : {audit_id}",
            f"Pages crawled : {total_pg}",
        ]
        if overall_score is not None:
            lines.append(f"Overall SEO score : {overall_score}/100")
        if mobile_score is not None:
            lines.append(f"Mobile SEO score  : {mobile_score}/100")
        if bl_count is not None:
            lines.append(f"Backlinks found   : {bl_count}")

        lines += [
            f"",
            f"--- On-page issues across all pages ---",
            f"Pages missing H1  : {missing_h1}/{total_pg}",
            f"Pages with bad title : {bad_title}/{total_pg}",
            f"Pages with bad meta  : {bad_meta}/{total_pg}",
            f"Total images missing alt : {alt_missing}",
        ]

        if top_errors:
            lines.append(f"\n--- Top Errors ({len(errors)} total) ---")
            lines.extend(top_errors)
        if top_warnings:
            lines.append(f"\n--- Top Warnings ({len(warnings)} total) ---")
            lines.extend(top_warnings)

        lines.append("=== END AUDIT CONTEXT ===")
        return "\n".join(lines)

    except Exception as e:
        return f"[Audit context unavailable: {e}]"


# ── Groq API Call ──────────────────────────────────────────────────────────────

def chat(user_message: str, history: list, audit_id: int | None = None) -> dict:
    """
    Send a message to Groq and get a response.

    Args:
        user_message: The user's latest message
        history: List of {role, content} dicts (previous turns)
        audit_id: Current audit ID for RAG context (None if no audit loaded)

    Returns:
        dict with keys:
            reply    (str)   — assistant response
            history  (list)  — updated conversation history
            error    (str)   — error message if failed, else None
    """
    if not GROQ_API_KEY:
        return {
            "reply": None,
            "history": history,
            "error": "GROQ_API_KEY not set in .env. Get a free key at https://console.groq.com/keys"
        }

    # Build system message — inject audit context if available
    audit_ctx   = build_audit_context(audit_id)
    system_body = SYSTEM_PROMPT
    if audit_ctx:
        system_body += f"\n\n{audit_ctx}"

    # Trim history to last N turns to stay within context limits
    trimmed_history = history[-(MAX_HISTORY_TURNS * 2):]

    messages = [
        {"role": "system", "content": system_body},
        *trimmed_history,
        {"role": "user", "content": user_message},
    ]

    payload = {
        "model":       GROQ_MODEL,
        "max_tokens":  1024,
        "temperature": 0.6,
        "messages":    messages,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        data = resp.json()

        if not resp.ok:
            return {
                "reply":   None,
                "history": history,
                "error":   f"Groq API error {resp.status_code}: {data.get('error', {}).get('message', resp.text[:300])}"
            }

        choice = (data.get("choices") or [{}])[0]
        reply  = choice.get("message", {}).get("content", "").strip()

        if not reply:
            return {
                "reply":   None,
                "history": history,
                "error":   "Empty response from Groq"
            }

        # Update history
        new_history = trimmed_history + [
            {"role": "user",      "content": user_message},
            {"role": "assistant", "content": reply},
        ]

        return {"reply": reply, "history": new_history, "error": None}

    except requests.exceptions.Timeout:
        return {"reply": None, "history": history, "error": "Request timed out. Please try again."}
    except Exception as e:
        return {"reply": None, "history": history, "error": f"Network error: {e}"}
