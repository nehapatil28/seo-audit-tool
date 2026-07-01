"""
content_generator.py — Groq-powered AI Content Writer (Agent 2)

This is stage 2 of a 2-agent LLM pipeline:
    Agent 1 (ai_recommendation.py) -> diagnoses problems, explains WHAT to fix
    Agent 2 (this file)            -> writes the actual replacement content

Given the page's real on-page data (current title, meta description,
headings, keywords, images missing alt text), this asks an LLM to generate
ready-to-publish replacement content — not generic advice, actual strings
that can be pasted into the site's HTML.

Setup:
    Set GROQ_API_KEY in your .env file. Get a free key at
    https://console.groq.com/keys (no credit card needed, generous
    free daily limits compared to Gemini's free tier).
"""

import os
import json
import textwrap
import requests
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip() or None
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ── Prompt Template ──────────────────────────────────────────────────────────

def _normalize_keywords(keywords) -> list:
    """Coerce a list of keywords into plain strings.

    content.get("keywords") may return plain strings, or dicts like
    {"keyword": "...", "count": 5} depending on the extractor used.
    This handles both so ', '.join(...) never blows up.
    """
    if not keywords:
        return []

    normalized = []
    for kw in keywords:
        if isinstance(kw, str):
            normalized.append(kw)
        elif isinstance(kw, dict):
            text = kw.get("keyword") or kw.get("text") or kw.get("term") or kw.get("word")
            if text:
                normalized.append(str(text))
        else:
            normalized.append(str(kw))
    return normalized


def _build_prompt(url: str, onpage_data: dict, focus_keywords=None) -> str:
    """Build a content-generation prompt from real on-page SEO data."""

    title    = onpage_data.get("title", {}) or {}
    meta     = onpage_data.get("meta_description", {}) or {}
    headings = onpage_data.get("headings", {}) or {}
    content  = onpage_data.get("content", {}) or {}
    images   = onpage_data.get("images", {}) or {}

    keywords = focus_keywords or content.get("keywords", [])
    keywords = _normalize_keywords(keywords)
    # Cap to 10 missing-alt images so the prompt doesn't blow up on big pages
    missing_alt_imgs = (images.get("missing_alt") or [])[:10]

    word_count        = content.get("word_count", 0)
    word_count_ok     = content.get("word_count_ok", True)
    readability_score = content.get("readability_score", 100)
    readability_label = content.get("readability_label", "")
    duplicate_content = content.get("duplicate_content", False)
    h2_count           = headings.get("h2_count", 0)
    h3_count           = headings.get("h3_count", 0)
    structure_ok        = headings.get("structure_ok", True)

    prompt = textwrap.dedent(f"""
        You are an expert SEO copywriter. Rewrite the on-page content below so it
        is SEO-optimized, natural-sounding, and ready to paste directly into the
        website's HTML. Do NOT use placeholder text like "[Your Product Here]" —
        write real, specific, publishable content based on the page's actual topic.

        URL: {url}
        Target keywords (from existing page content): {', '.join(keywords) or 'infer from the URL and current title'}

        CURRENT TITLE TAG       : "{title.get('text', '')}"  (length: {title.get('length', 0)} chars)
        CURRENT META DESCRIPTION: "{meta.get('text', '')}"  (length: {meta.get('length', 0)} chars)
        CURRENT H1(s)           : {headings.get('h1_texts', [])}
        H2 COUNT / H3 COUNT     : {h2_count} / {h3_count}  (structure_ok: {structure_ok})
        WORD COUNT              : {word_count}  (ok: {word_count_ok})
        READABILITY             : {readability_score} ({readability_label})
        DUPLICATE CONTENT       : {duplicate_content}
        IMAGES MISSING ALT TEXT : {missing_alt_imgs if missing_alt_imgs else 'None'}

        Generate the following:

        1. "new_title": a new title tag, 50-60 characters, includes a primary
           keyword near the start, written to be compelling for clicks (not clickbait).
        2. "new_meta_description": a new meta description, 140-160 characters,
           includes a keyword naturally and ends with a soft call-to-action.
        3. "new_h1": an improved H1 heading ONLY if the current H1 is missing, empty,
           or weak. If the current H1 is already good, return "" (empty string).
        4. "alt_text_suggestions": a list of objects, one per image listed above,
           each {{"image": "<the exact filename/URL from the list>", "suggested_alt":
           "<descriptive, keyword-aware alt text under 125 characters, inferred from
           the filename and the page's topic>"}}. Return an empty list if no images
           were listed above.
        5. "suggested_h2_subheadings": a list of 3-5 new H2 subheading strings ONLY if
           h2_count is 0 or structure_ok is false (weak/missing structure) — these should
           outline a logical content structure for this page's topic. Return an empty
           list [] if the current H2 structure is already adequate.
        6. "content_expansion_paragraph": ONE ready-to-paste paragraph (80-150 words) that
           expands on the page's topic, ONLY if word_count_ok is false (content too thin).
           Return "" if word count is already sufficient.
        7. "readability_fix_note": a short plain-language tip (1-2 sentences) on how to
           simplify the writing, ONLY if readability_label is "Difficult" or "Very Difficult".
           Return "" if readability is already Easy or Moderate.
        8. "og_title" / "og_description": a social-preview title (under 60 chars) and
           description (under 110 chars) for Open Graph / Twitter Card tags, written to be
           engaging when shared on social media. Always generate these two.
        9. "improvement_notes": 1-2 plain-language sentences explaining what changed
           and why, written for a non-technical site owner.

        Format your response as valid JSON with EXACTLY this structure:
        {{
          "new_title": "string",
          "new_meta_description": "string",
          "new_h1": "string",
          "alt_text_suggestions": [{{"image": "string", "suggested_alt": "string"}}],
          "suggested_h2_subheadings": ["string"],
          "content_expansion_paragraph": "string",
          "readability_fix_note": "string",
          "og_title": "string",
          "og_description": "string",
          "improvement_notes": "string"
        }}

        Return ONLY the JSON object. No markdown, no preamble, no code fences.
    """).strip()

    return prompt


# ── Groq API Call ────────────────────────────────────────────────────────────

def generate_content_fixes(url: str, onpage_data: dict, focus_keywords=None) -> dict:
    """
    Agent 2: AI Content Writer.

    Args:
        url:            The audited page URL.
        onpage_data:    The "seo" dict produced by onpage.analyze_onpage()
                        (keys: title, meta_description, headings, content, images).
        focus_keywords: Optional list of keywords to target instead of the
                        auto-extracted ones.

    Returns:
        dict with keys: new_title, new_meta_description, new_h1,
                        alt_text_suggestions, improvement_notes, raw_text, error (if any)
    """
    if not GROQ_API_KEY:
        return {
            "error": "GROQ_API_KEY not set in .env file. "
                     "Get a free key at https://console.groq.com/keys"
        }

    if not onpage_data:
        return {
            "error": "No on-page data provided. Run an On-Page / Quick Audit on this URL first."
        }

    raw_text = ""
    try:
        prompt = _build_prompt(url, onpage_data, focus_keywords)

        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert SEO copywriter. Always respond with "
                                "valid JSON only, matching exactly the schema requested. "
                                "No markdown, no preamble, no code fences.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.6,  # higher than the analyst agent — this is creative writing
            "max_tokens": 6144,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)

        if resp.status_code == 429:
            return {
                "error": "AI Content Generator is temporarily unavailable — "
                         "the free daily usage limit has been reached. "
                         "Please try again in a little while or tomorrow.",
                "limit_reached": True,
                "raw_text": resp.text,
            }
        if resp.status_code != 200:
            return {
                "error": f"Groq API error (status {resp.status_code}): {resp.text[:500]}",
                "raw_text": resp.text,
            }

        data = resp.json()

        try:
            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError):
            return {"error": f"Unexpected Groq response shape: {data}", "raw_text": resp.text}

        if finish_reason == "length":
            return {
                "error": "Groq response was cut off because it hit the max_tokens "
                         "limit before finishing the JSON. Increase max_tokens or "
                         "reduce the number of missing-alt images sent in the prompt.",
                "raw_text": choice.get("message", {}).get("content", ""),
            }

        raw_text = (choice.get("message", {}).get("content") or "").strip()
        clean = _strip_markdown_fences(raw_text)

        parsed = json.loads(clean)
        parsed["raw_text"] = raw_text
        return parsed

    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse Groq response as JSON: {e}. "
                     "This usually means the response was truncated (try increasing "
                     "max_tokens) or contains an unescaped control character.",
            "raw_text": raw_text,
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error calling Groq API: {e}", "raw_text": raw_text}
    except Exception as e:
        return {"error": str(e), "raw_text": raw_text}


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json / ``` fences if the model wrapped the JSON in them.

    Uses literal prefix/suffix removal (not str.strip's character-set
    semantics) so it can't accidentally eat valid leading/trailing
    characters from the JSON payload itself.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        else:
            cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()