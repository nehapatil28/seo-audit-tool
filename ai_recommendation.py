"""
ai_recommendation.py — Gemini-powered SEO Recommendations
Analyzes audit data and returns actionable AI suggestions.

Setup:
    pip install google-generativeai
    Add to .env:  GEMINI_API_KEY=your_key_here
    Free tier: https://aistudio.google.com/app/apikey

    Uses gemini-2.5-flash-lite — Google's free tier gives this model the
    highest daily request quota of any Gemini model (much higher than
    Flash or Pro), so it's the best free option for this use case.
"""

import os
import json
import textwrap
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip() or None
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()


# ── Prompt Template ──────────────────────────────────────────────────────────

def _build_prompt(url: str, audit_data: dict) -> str:
    """Build a structured prompt from collected audit data."""

    sections = []

    # PageSpeed
    ps = audit_data.get("pagespeed") or {}
    if ps:
        sections.append(f"""
[PageSpeed]
Performance Score : {ps.get('performance_score', 'N/A')}
LCP               : {ps.get('lcp_ms', 'N/A')} ms
FCP               : {ps.get('fcp_ms', 'N/A')} ms
CLS               : {ps.get('cls', 'N/A')}
TBT               : {ps.get('tbt_ms', 'N/A')} ms
TTFB              : {ps.get('ttfb_ms', 'N/A')} ms
Total JS          : {ps.get('total_js_kb', 0)} KB
Total CSS         : {ps.get('total_css_kb', 0)} KB
Total Images      : {ps.get('total_img_kb', 0)} KB
Page Size         : {ps.get('page_size_kb', 0)} KB
Total Requests    : {ps.get('total_requests', 0)}
Render Blocking   : {ps.get('render_blocking_count', 0)}
Unused JS         : {ps.get('unused_js_kb', 0)} KB
Unused CSS        : {ps.get('unused_css_kb', 0)} KB
""")

    # Technical SEO
    tech = audit_data.get("technical") or {}
    if tech:
        sections.append(f"""
[Technical SEO]
Score             : {tech.get('score', 'N/A')}
HTTPS             : {tech.get('https', False)}
Robots.txt        : {tech.get('robots_txt', False)}
Sitemap.xml       : {tech.get('sitemap_xml', False)}
Sitemap URL count : {tech.get('sitemap_url_count', 0)}
Canonical         : {tech.get('canonical', False)}
Crawl Errors      : {tech.get('crawl_error_count', 0)}
Has Schema        : {tech.get('has_schema', False)}
Has OG Tags       : {tech.get('has_og', False)}
Mobile Friendly   : {tech.get('mobile_friendly', False)}
Load Time         : {tech.get('load_time_ms', 0)} ms
""")

    # Backlinks
    bl = audit_data.get("backlinks") or {}
    if bl:
        sections.append(f"""
[Backlinks]
Overall Score     : {bl.get('overall_score', 'N/A')}
External Links    : {bl.get('external_links', 0)}
Unique Domains    : {bl.get('unique_external_domains', 0)}
Dofollow Links    : {bl.get('dofollow_count', 0)}
Nofollow Links    : {bl.get('nofollow_count', 0)}
High Authority    : {bl.get('high_authority_links', 0)}
Broken External   : {bl.get('broken_external_count', 0)}
Link Equity Score : {bl.get('link_equity_score', 0)}
""")

    # Mobile SEO
    mob = audit_data.get("mobile_seo") or {}
    if mob:
        summary = mob.get("summary", {})
        sections.append(f"""
[Mobile SEO]
Mobile Score      : {summary.get('score', 'N/A')}
Mobile Friendly   : {summary.get('mobile_friendly', False)}
Passed Checks     : {summary.get('passed', 0)} / {summary.get('total', 0)}
""")

    # Social Preview
    soc = audit_data.get("social_preview") or {}
    if soc:
        readiness = soc.get("readiness", {})
        sections.append(f"""
[Social Preview]
OG Score          : {readiness.get('og_score', 'N/A')}
Twitter Score     : {readiness.get('twitter_score', 'N/A')}
Has OG Tags       : {readiness.get('has_og', False)}
Has Twitter Cards : {readiness.get('has_twitter', False)}
Image Accessible  : {readiness.get('image_accessible', False)}
Image Dims OK     : {readiness.get('image_dimensions_ok', False)}
""")

    # SEO Score
    seo = audit_data.get("seo_score") or {}
    if seo:
        bd = seo.get("breakdown", {})
        sections.append(f"""
[SEO Score Breakdown]
Overall Score     : {seo.get('page_score', 'N/A')} — {seo.get('label', '')}
Title             : {bd.get('title', 0)}
Meta Description  : {bd.get('meta', 0)}
Headings          : {bd.get('headings', 0)}
Content           : {bd.get('content', 0)}
Images            : {bd.get('images', 0)}
Links             : {bd.get('links', 0)}
Speed             : {bd.get('speed', 0)}
Technical         : {bd.get('technical', 0)}
""")

    # Structured Data
    sd = audit_data.get("structured_data") or {}
    if sd:
        sections.append(f"""
[Structured Data]
Overall Score     : {sd.get('overall_score', 'N/A')} — {sd.get('score_label', '')}
Has JSON-LD       : {sd.get('has_jsonld', False)}
Has Microdata     : {sd.get('has_microdata', False)}
Total Schemas     : {sd.get('total_schemas', 0)}
Total Errors      : {sd.get('total_errors', 0)}
Total Warnings    : {sd.get('total_warnings', 0)}
Schema Types      : {', '.join(sd.get('schema_types', [])) or 'None'}
""")

    data_block = "\n".join(sections) if sections else "No audit data provided."

    prompt = textwrap.dedent(f"""
        You are an expert SEO consultant analyzing the following audit data for:
        URL: {url}

        {data_block}

        Based on this data, provide a structured, BEGINNER-FRIENDLY SEO recommendation
        report. The reader may not be an SEO expert, so explain things clearly and
        give concrete, step-by-step guidance rather than vague advice.

        1. **Overall Health Summary** (3-4 sentences, plain language, no jargon)
        2. **Critical Issues** (4-7 — things that urgently need fixing)
        3. **Quick Wins** (4-7 — easy improvements with high impact)
        4. **Long-Term Recommendations** (3-5 — strategic improvements)
        5. **Priority Action Plan** (ordered top-5 next steps the developer should do NOW)

        For EVERY Critical Issue and Quick Win, include:
        - "category": one of "Performance","Technical SEO","Content","Backlinks","Mobile","Structured Data","Social"
        - "title": short, specific issue name
        - "detail": explain WHY this matters in plain language (1-2 sentences)
        - "how_to_fix": a clear, numbered, step-by-step explanation of HOW to fix it
          (write as plain text with steps separated by "\\n", e.g. "1. ...\\n2. ...")
        - "estimated_time": realistic human time to fix, e.g. "10 min", "1-2 hours"
        - "code_snippet": a ready-to-use HTML/meta/config snippet IF the fix is code-related
          (use real data from the page where possible, e.g. actual title/meta text).
          Set to "" if not code-related (e.g. "write more content").

        Critical Issues additionally include:
        - "impact": "high"|"medium"|"low"

        Quick Wins additionally include:
        - "effort": "easy"|"medium"|"hard"
        - "expected_gain": short phrase on the benefit, e.g. "+5-10 SEO points", "Faster load time"

        Long-Term Recommendations include:
        - "title", "detail" (why it matters strategically)
        - "timeline": realistic timeframe, e.g. "2-4 weeks", "1-3 months"
        - "expected_outcome": what improves if this is done

        Priority Actions include:
        - "rank" (1-5), "action" (what to do), "reason" (why this is top priority),
        - "estimated_time"

        Format your response as valid JSON with this exact structure:
        {{
          "summary": "string",
          "critical_issues": [
            {{"category": "string", "title": "string", "detail": "string", "how_to_fix": "string",
              "estimated_time": "string", "impact": "high|medium|low", "code_snippet": "string"}}
          ],
          "quick_wins": [
            {{"category": "string", "title": "string", "detail": "string", "how_to_fix": "string",
              "estimated_time": "string", "effort": "easy|medium|hard", "expected_gain": "string", "code_snippet": "string"}}
          ],
          "long_term": [
            {{"title": "string", "detail": "string", "timeline": "string", "expected_outcome": "string"}}
          ],
          "priority_actions": [
            {{"rank": 1, "action": "string", "reason": "string", "estimated_time": "string"}}
          ]
        }}

        Return ONLY the JSON object. No markdown, no preamble.
    """).strip()

    return prompt


# ── Gemini API Call ──────────────────────────────────────────────────────────

def get_ai_recommendation(url: str, audit_data: dict) -> dict:
    """
    Call Gemini API with audit data and return structured recommendations.

    Args:
        url:        The website URL that was audited.
        audit_data: Dict with keys: pagespeed, technical, backlinks,
                    mobile_seo, social_preview, seo_score, structured_data.
                    All are optional — pass what you have.

    Returns:
        dict with keys: summary, critical_issues, quick_wins,
                        long_term, priority_actions, raw_text, error (if any)
    """
    if not GEMINI_API_KEY:
        return {
            "error": "GEMINI_API_KEY not set in .env file. "
                     "Get a free key at https://aistudio.google.com/app/apikey"
        }

    try:
        import google.generativeai as genai
    except ImportError:
        return {
            "error": "google-generativeai not installed. Run: pip install google-generativeai"
        }

    raw_text = ""
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            GEMINI_MODEL,
            generation_config={
                "response_mime_type": "application/json",
                "max_output_tokens": 8192,
                "temperature": 0.4,
            },
        )
        prompt = _build_prompt(url, audit_data)

        response = model.generate_content(prompt)

        # Detect truncation before even trying to parse — gives a much
        # clearer error than "Unterminated string ..."
        try:
            finish_reason = response.candidates[0].finish_reason
        except (IndexError, AttributeError):
            finish_reason = None

        # google-generativeai's finish_reason is an enum; compare by name
        # to stay version-agnostic (MAX_TOKENS == truncated).
        if finish_reason is not None and getattr(finish_reason, "name", str(finish_reason)) == "MAX_TOKENS":
            return {
                "error": "Gemini response was cut off because it hit the max_output_tokens "
                         "limit before finishing the JSON. Increase max_output_tokens or "
                         "shorten the requested output (fewer issues, shorter how_to_fix/code_snippet).",
                "raw_text": getattr(response, "text", ""),
            }

        raw_text = response.text.strip()
        clean = _strip_markdown_fences(raw_text)

        parsed = json.loads(clean)
        parsed["raw_text"] = raw_text
        return parsed

    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse Gemini response as JSON: {e}. "
                     "This usually means the response was truncated (try increasing "
                     "max_output_tokens) or contains an unescaped control character.",
            "raw_text": raw_text,
        }
    except Exception as e:
        err_str = str(e)
        # Gemini's google-generativeai client raises a generic Exception for
        # 429s rather than giving us a clean status code, so detect by text.
        if "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str:
            return {
                "error": "AI Recommendations are temporarily unavailable — "
                         "the free daily usage limit has been reached. "
                         "Please try again in a little while or tomorrow.",
                "limit_reached": True,
                "raw_text": raw_text,
            }
        return {"error": err_str, "raw_text": raw_text}


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