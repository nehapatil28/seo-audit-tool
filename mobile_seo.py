"""
mobile_seo.py — Mobile SEO Checker
====================================
Checks all mobile SEO signals for a given URL using Playwright (headless Chromium).
Designed to plug into the existing SEO Crawler Flask + Socket.IO app.

Checks performed:
  1.  Mobile-Friendly Check         — overall verdict
  2.  Viewport Meta Tag             — presence & content
  3.  Responsive Design Detection   — CSS media queries present
  4.  Content Fits Screen Width     — no horizontal scroll
  5.  Font Readability              — base font-size ≥ 16 px
  6.  Touch Element Spacing         — adjacent tap targets far enough apart
  7.  Tap Target Size               — buttons/links ≥ 48 × 48 px
  8.  Buttons / Links Spacing       — padding/margin around interactive elements
  9.  Responsive Images             — max-width:100% or srcset present
 10.  Pop-up / Interstitial Check   — intrusive overlay detection
 11.  Mobile Navigation Usability   — nav menu reachable at 390 px width
 12.  Form Usability on Mobile      — inputs have labels, type attrs set
 13.  Mobile Page Speed Score       — LCP, CLS, INP via PerformanceObserver
 14.  Mobile Core Web Vitals        — LCP / CLS / INP ratings
"""

import asyncio
import time
import re
from urllib.parse import urlparse

# ── Playwright is required ───────────────────────────────────────────────────
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

# ── Mobile emulation profile (iPhone 14 Pro ≈ 390 px CSS width) ─────────────
MOBILE_VIEWPORT = {"width": 390, "height": 844}
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_mobile_seo(url: str) -> dict:
    """
    Synchronous wrapper — call from Flask route.
    Returns a dict with all mobile SEO check results.
    """
    if not PLAYWRIGHT_OK:
        return {"error": "Playwright not installed. Run: pip install playwright && playwright install chromium"}

    try:
        return asyncio.run(_audit(url))
    except Exception as exc:
        return {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
#  ASYNC CORE
# ─────────────────────────────────────────────────────────────────────────────

async def _audit(url: str) -> dict:
    t0 = time.time()
    results = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # ── Mobile context ──────────────────────────────────────────────────
        ctx = await browser.new_context(
            viewport=MOBILE_VIEWPORT,
            user_agent=MOBILE_UA,
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        page = await ctx.new_page()

        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=30_000)
            status_code = resp.status if resp else None
        except Exception as e:
            await browser.close()
            return {"error": f"Page load failed: {e}"}

        # ── 1. Viewport meta tag ─────────────────────────────────────────────
        viewport_meta = await page.evaluate("""() => {
            const m = document.querySelector('meta[name="viewport"]');
            return m ? m.getAttribute('content') : null;
        }""")
        has_viewport   = viewport_meta is not None
        vp_has_width   = "width=device-width" in (viewport_meta or "")
        vp_has_initial = "initial-scale=1" in (viewport_meta or "")
        vp_no_scale    = "user-scalable=no" not in (viewport_meta or "") and \
                         "maximum-scale=1" not in (viewport_meta or "")

        results["viewport"] = {
            "present":        has_viewport,
            "content":        viewport_meta or "",
            "width_device":   vp_has_width,
            "initial_scale":  vp_has_initial,
            "allows_zoom":    vp_no_scale,
            "ok":             has_viewport and vp_has_width and vp_has_initial,
        }

        # ── 2. Responsive design — CSS media queries ────────────────────────
        responsive_data = await page.evaluate("""() => {
            const sheets = Array.from(document.styleSheets);
            let mqCount = 0;
            let hasMaxWidth = false;
            let hasMinWidth = false;
            for (const sheet of sheets) {
                try {
                    const rules = Array.from(sheet.cssRules || []);
                    for (const rule of rules) {
                        if (rule.type === CSSRule.MEDIA_RULE) {
                            mqCount++;
                            const text = rule.conditionText || rule.media?.mediaText || "";
                            if (text.includes("max-width")) hasMaxWidth = true;
                            if (text.includes("min-width")) hasMinWidth = true;
                        }
                    }
                } catch(e) {}
            }
            return { mqCount, hasMaxWidth, hasMinWidth };
        }""")
        results["responsive_design"] = {
            "media_query_count": responsive_data["mqCount"],
            "has_max_width_mq":  responsive_data["hasMaxWidth"],
            "has_min_width_mq":  responsive_data["hasMinWidth"],
            "ok": responsive_data["mqCount"] > 0,
        }

        # ── 3. Content fits screen (no horizontal overflow) ──────────────────
        overflow_data = await page.evaluate("""() => {
            const bodyW   = document.body.scrollWidth;
            const viewW   = window.innerWidth;
            const overflowEls = [];
            document.querySelectorAll('*').forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.right > viewW + 5) {
                    overflowEls.push({
                        tag: el.tagName,
                        id:  el.id || '',
                        cls: el.className || '',
                        right: Math.round(rect.right)
                    });
                }
            });
            return {
                bodyScrollWidth: bodyW,
                viewportWidth:   viewW,
                overflowCount:   overflowEls.length,
                overflowSamples: overflowEls.slice(0, 5)
            };
        }""")
        results["content_width"] = {
            "body_scroll_width":  overflow_data["bodyScrollWidth"],
            "viewport_width":     overflow_data["viewportWidth"],
            "overflow_count":     overflow_data["overflowCount"],
            "overflow_samples":   overflow_data["overflowSamples"],
            "ok": overflow_data["overflowCount"] == 0,
        }

        # ── 4. Font readability (base font size ≥ 16 px) ────────────────────
        font_data = await page.evaluate("""() => {
            const body   = document.body;
            const style  = window.getComputedStyle(body);
            const fsize  = parseFloat(style.fontSize);
            // also scan paragraph / article text
            const textEls = Array.from(document.querySelectorAll('p, article, .content, main'));
            let minFont = fsize;
            for (const el of textEls) {
                const s = parseFloat(window.getComputedStyle(el).fontSize);
                if (s < minFont) minFont = s;
            }
            return { bodyFontSize: fsize, minTextFontSize: minFont };
        }""")
        results["font_readability"] = {
            "body_font_size_px":    font_data["bodyFontSize"],
            "min_text_font_size_px": font_data["minTextFontSize"],
            "ok": font_data["bodyFontSize"] >= 14,   # 14px min; 16px ideal
            "ideal": font_data["bodyFontSize"] >= 16,
        }

        # ── 5 & 6 & 7. Tap targets — size + spacing ─────────────────────────
        tap_data = await page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role="button"], [onclick]'));
            const small = [];
            const spaced = [];
            const MIN = 48;
            for (let i = 0; i < els.length; i++) {
                const r = els[i].getBoundingClientRect();
                const w = r.width, h = r.height;
                if (w < 1 && h < 1) continue;   // invisible
                if (w < MIN || h < MIN) {
                    small.push({
                        tag: els[i].tagName,
                        text: (els[i].innerText || els[i].value || '').substring(0,30),
                        w: Math.round(w), h: Math.round(h)
                    });
                }
                // Check spacing to next element
                if (i + 1 < els.length) {
                    const r2 = els[i + 1].getBoundingClientRect();
                    if (r2.width < 1) continue;
                    const gap = Math.max(0, r2.top - r.bottom, r2.left - r.right);
                    if (gap < 8) {
                        spaced.push({
                            el1: els[i].tagName,
                            el2: els[i+1].tagName,
                            gap: Math.round(gap)
                        });
                    }
                }
            }
            return {
                totalTapTargets: els.length,
                smallCount:      small.length,
                smallSamples:    small.slice(0, 5),
                spacingIssues:   spaced.length,
                spacingSamples:  spaced.slice(0, 5)
            };
        }""")
        results["tap_targets"] = {
            "total":          tap_data["totalTapTargets"],
            "small_count":    tap_data["smallCount"],
            "small_samples":  tap_data["smallSamples"],
            "ok": tap_data["smallCount"] == 0,
            "pct_ok": round(
                100 * (tap_data["totalTapTargets"] - tap_data["smallCount"]) / max(tap_data["totalTapTargets"], 1)
            ),
        }
        results["touch_spacing"] = {
            "spacing_issues":  tap_data["spacingIssues"],
            "spacing_samples": tap_data["spacingSamples"],
            "ok": tap_data["spacingIssues"] == 0,
        }

        # ── 8. Responsive images ─────────────────────────────────────────────
        img_data = await page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            let hasSrcset = 0, hasMaxWidth = 0, overflowing = 0;
            for (const img of imgs) {
                if (img.srcset)               hasSrcset++;
                const st = window.getComputedStyle(img);
                if (st.maxWidth === '100%' || parseFloat(st.maxWidth) <= window.innerWidth) hasMaxWidth++;
                const r = img.getBoundingClientRect();
                if (r.width > window.innerWidth + 5)  overflowing++;
            }
            return {
                total: imgs.length,
                hasSrcset,
                hasMaxWidth,
                overflowing
            };
        }""")
        results["responsive_images"] = {
            "total":        img_data["total"],
            "has_srcset":   img_data["hasSrcset"],
            "has_max_width": img_data["hasMaxWidth"],
            "overflowing":  img_data["overflowing"],
            "ok": img_data["overflowing"] == 0,
        }

        # ── 9. Pop-up / Interstitial check ───────────────────────────────────
        popup_data = await page.evaluate("""() => {
            const fixed = Array.from(document.querySelectorAll('*')).filter(el => {
                const st = window.getComputedStyle(el);
                return (st.position === 'fixed' || st.position === 'sticky') &&
                       st.display !== 'none' &&
                       st.visibility !== 'hidden' &&
                       parseFloat(st.opacity) > 0;
            });
            const overlays = fixed.filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > window.innerWidth * 0.5 && r.height > window.innerHeight * 0.25;
            });
            return {
                fixedCount:   fixed.length,
                overlayCount: overlays.length,
                samples: overlays.slice(0, 3).map(el => ({
                    tag: el.tagName,
                    id:  el.id || '',
                    cls: (el.className || '').toString().substring(0,40)
                }))
            };
        }""")
        results["popups"] = {
            "fixed_elements":  popup_data["fixedCount"],
            "overlay_count":   popup_data["overlayCount"],
            "samples":         popup_data["samples"],
            "ok": popup_data["overlayCount"] == 0,
        }

        # ── 10. Mobile navigation usability ──────────────────────────────────
        nav_data = await page.evaluate("""() => {
            const navEl = document.querySelector('nav, [role="navigation"], header nav, .navbar, .nav-menu, #nav');
            if (!navEl) return { found: false };
            const links = navEl.querySelectorAll('a');
            const r     = navEl.getBoundingClientRect();
            return {
                found:      true,
                linkCount:  links.length,
                width:      Math.round(r.width),
                height:     Math.round(r.height),
                isVisible:  r.width > 0 && r.height > 0,
                fitsScreen: r.width <= window.innerWidth + 5
            };
        }""")
        results["mobile_nav"] = {
            "nav_found":    nav_data.get("found", False),
            "link_count":   nav_data.get("linkCount", 0),
            "is_visible":   nav_data.get("isVisible", False),
            "fits_screen":  nav_data.get("fitsScreen", True),
            "ok": nav_data.get("found", False) and nav_data.get("isVisible", False) and nav_data.get("fitsScreen", True),
        }

        # ── 11. Form usability on mobile ─────────────────────────────────────
        form_data = await page.evaluate("""() => {
            const inputs = Array.from(document.querySelectorAll('input:not([type=hidden]), textarea, select'));
            let missingLabel = 0, missingType = 0, smallInput = 0;
            for (const inp of inputs) {
                const id   = inp.id;
                const name = inp.name;
                const hasLabel = id && document.querySelector(`label[for="${id}"]`) ||
                                 inp.closest('label') ||
                                 inp.getAttribute('aria-label') ||
                                 inp.getAttribute('placeholder');
                if (!hasLabel) missingLabel++;
                if (inp.tagName === 'INPUT' && !inp.type) missingType++;
                const r = inp.getBoundingClientRect();
                if (r.height > 0 && r.height < 40) smallInput++;
            }
            return { total: inputs.length, missingLabel, missingType, smallInput };
        }""")
        results["form_usability"] = {
            "total_inputs":   form_data["total"],
            "missing_label":  form_data["missingLabel"],
            "missing_type":   form_data["missingType"],
            "small_inputs":   form_data["smallInput"],
            "ok": form_data["total"] == 0 or (form_data["missingLabel"] == 0 and form_data["smallInput"] == 0),
        }

        # ── 12 & 13. Core Web Vitals — LCP, CLS, INP (via JS API) ───────────
        # We inject a PerformanceObserver snippet and wait briefly
        try:
            cwv = await page.evaluate("""() => new Promise((resolve) => {
                const out = { lcp: null, cls: 0, inp: null };
                try {
                    new PerformanceObserver(list => {
                        for (const e of list.getEntries())
                            out.lcp = e.startTime;
                    }).observe({ type: 'largest-contentful-paint', buffered: true });

                    new PerformanceObserver(list => {
                        for (const e of list.getEntries())
                            out.cls += e.value;
                    }).observe({ type: 'layout-shift', buffered: true });

                    new PerformanceObserver(list => {
                        for (const e of list.getEntries())
                            if (!out.inp || e.processingStart - e.startTime > out.inp)
                                out.inp = e.processingStart - e.startTime;
                    }).observe({ type: 'event', buffered: true, durationThreshold: 0 });
                } catch(e) {}

                // Also grab navigation timing for LCP fallback
                setTimeout(() => {
                    const nav = performance.getEntriesByType('navigation')[0] || {};
                    if (!out.lcp) out.lcp = nav.domContentLoadedEventEnd || null;
                    resolve(out);
                }, 3000);
            })""")
        except Exception:
            cwv = {"lcp": None, "cls": 0, "inp": None}

        lcp_ms  = round(cwv.get("lcp") or 0)
        cls_val = round(cwv.get("cls") or 0, 3)
        inp_ms  = round(cwv.get("inp") or 0)

        def lcp_rating(ms):
            if ms <= 2500: return "good"
            if ms <= 4000: return "needs-improvement"
            return "poor"

        def cls_rating(v):
            if v <= 0.1:  return "good"
            if v <= 0.25: return "needs-improvement"
            return "poor"

        def inp_rating(ms):
            if ms <= 200: return "good"
            if ms <= 500: return "needs-improvement"
            return "poor"

        results["core_web_vitals"] = {
            "lcp_ms":     lcp_ms,
            "lcp_rating": lcp_rating(lcp_ms),
            "cls":        cls_val,
            "cls_rating": cls_rating(cls_val),
            "inp_ms":     inp_ms,
            "inp_rating": inp_rating(inp_ms),
            "ok": lcp_rating(lcp_ms) == "good" and cls_rating(cls_val) == "good",
        }

        # ── 13. Page speed score (simple Lighthouse-like calc) ────────────────
        # Approximate score from LCP + CLS (no full Lighthouse without API key)
        lcp_score = max(0, min(100, int(100 - (lcp_ms - 1000) / 40))) if lcp_ms else 50
        cls_score = max(0, min(100, int(100 - cls_val * 500)))
        mobile_speed_score = round((lcp_score * 0.6 + cls_score * 0.4))

        results["mobile_speed"] = {
            "score":       mobile_speed_score,
            "lcp_score":   lcp_score,
            "cls_score":   cls_score,
            "label":       "Good" if mobile_speed_score >= 70 else "Needs Work" if mobile_speed_score >= 40 else "Poor",
        }

        await browser.close()

    # ── Overall mobile-friendly score ────────────────────────────────────────
    checks = [
        results["viewport"]["ok"],
        results["responsive_design"]["ok"],
        results["content_width"]["ok"],
        results["font_readability"]["ok"],
        results["tap_targets"]["ok"],
        results["touch_spacing"]["ok"],
        results["responsive_images"]["ok"],
        results["popups"]["ok"],
        results["mobile_nav"]["ok"],
        results["form_usability"]["ok"],
        results["core_web_vitals"]["ok"],
    ]
    passed      = sum(1 for c in checks if c)
    total       = len(checks)
    score       = round(passed / total * 100)
    mobile_ok   = score >= 70

    results["summary"] = {
        "url":          url,
        "score":        score,
        "passed":       passed,
        "total":        total,
        "mobile_friendly": mobile_ok,
        "label":        "Good" if score >= 70 else "Needs Work" if score >= 40 else "Poor",
        "elapsed_ms":   round((time.time() - t0) * 1000),
    }

    return results