from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import os
from dotenv import load_dotenv
load_dotenv()

# ── PageSpeed API Key ──
# .env file mein likho: GOOGLE_PAGESPEED_API_KEY=your_key_here
GOOGLE_PAGESPEED_KEY = os.getenv("GOOGLE_PAGESPEED_API_KEY", "").strip() or None

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "seo-crawler-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

active_crawlers = {}

# Initialize database on startup
from database import init_db
init_db()


# ── Start Audit Session ── (creates ONE audit_id shared by all modes of this scan)
@app.route("/api/start_audit", methods=["POST"])
def start_audit_route():
    try:
        from database import create_audit
        body   = request.get_json(force=True, silent=True) or {}
        url    = body.get("url", "").strip()
        device = body.get("device", "desktop")
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        audit_id = create_audit(url, device=device)
        return jsonify({"audit_id": audit_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return render_template("landing.html")   # nayi landing page


@app.route("/loading")
def loading():
    return render_template("loading.html")   # loading screen


@app.route("/dashboard")
def dashboard():
    return render_template("index.html")     # purana SEO tool


# ── PageSpeed API ──
@app.route("/api/pagespeed")
def pagespeed_route():
    try:
        from pagespeed import get_pagespeed
        url      = request.args.get("url", "").strip()
        strategy = request.args.get("device", request.args.get("strategy", "desktop"))
        audit_id = request.args.get("audit_id", type=int)
        # Use key from .env — never expose or ask from frontend
        api_key  = GOOGLE_PAGESPEED_KEY
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        result = get_pagespeed(url, api_key=api_key, strategy=strategy)

        try:
            from database import save_audit, save_page_speed
            summary = {
                "type":               "pagespeed",
                "strategy":           strategy,
                "performance_score":  result.get("performance_score"),
                "lcp_ms":             result.get("lcp_ms"),
                "fcp_ms":             result.get("fcp_ms"),
                "cls":                result.get("cls"),
                "tbt_ms":             result.get("tbt_ms"),
                "ttfb_ms":            result.get("ttfb_ms"),
                "si_ms":              result.get("si_ms"),
                "tti_ms":             result.get("tti_ms"),
                "total_js_kb":        result.get("total_js_kb", 0),
                "total_css_kb":       result.get("total_css_kb", 0),
                "total_img_kb":       result.get("total_img_kb", 0),
                "page_size_kb":       result.get("page_size_kb", 0),
                "total_requests":     result.get("total_requests", 0),
                "render_blocking":    result.get("render_blocking_count", 0),
                "unused_js_kb":       result.get("unused_js_kb", 0),
                "unused_css_kb":      result.get("unused_css_kb", 0),
            }
            audit_id = save_audit(url, mode="speed", device=strategy, summary=summary, audit_id=audit_id)
            save_page_speed(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (pagespeed):", e)

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Technical SEO ── (handles both /api/technical_seo and /api/technical)
@app.route("/api/technical_seo")
@app.route("/api/technical")
def technical_route():
    try:
        from technical_seo import get_technical_seo
        url = request.args.get("url", "").strip()
        audit_id = request.args.get("audit_id", type=int)
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        result = get_technical_seo(url)

        try:
            from database import save_audit, save_technical
            summary = {
                "type":            "technical",
                "score":           result.get("score", 0),
                "https_enabled":   result.get("https", False),
                "robots_present":  result.get("robots_txt", False),
                "sitemap_present": result.get("sitemap_xml", False),
                "sitemap_urls":    result.get("sitemap_url_count", 0),
                "canonical_ok":    result.get("canonical", False),
                "crawl_errors":    result.get("crawl_error_count", 0),
                "has_schema":      result.get("has_schema", False),
                "has_og":          result.get("has_og", False),
                "mobile_friendly": result.get("mobile_friendly", False),
                "load_time_ms":    result.get("load_time_ms", 0),
            }
            audit_id = save_audit(url, mode="technical", summary=summary, audit_id=audit_id)
            save_technical(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (technical):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ── Backlink Analysis ──
@app.route("/api/backlinks")
def backlinks_route():
    try:
        from backlink_analysis import get_backlink_analysis
        url = request.args.get("url", "").strip()
        audit_id = request.args.get("audit_id", type=int)
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        result = get_backlink_analysis(url)

        try:
            from database import save_audit, save_backlinks
            summary = {
                "type":                    "backlinks",
                "score":                   result.get("overall_score", 0),
                "external_links":          result.get("external_links", 0),
                "unique_domains":          result.get("unique_external_domains", 0),
                "dofollow_count":          result.get("dofollow_count", 0),
                "nofollow_count":          result.get("nofollow_count", 0),
                "high_authority_links":    result.get("high_authority_links", 0),
                "broken_external_count":   result.get("broken_external_count", 0),
                "link_equity_score":       result.get("link_equity_score", 0),
            }
            audit_id = save_audit(url, mode="backlinks", summary=summary, audit_id=audit_id)
            save_backlinks(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (backlinks):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ── Social Preview (OG + Twitter Cards) ──
@app.route("/api/social_preview")
def social_preview_route():
    try:
        from social_preview import get_social_preview
        url = request.args.get("url", "").strip()
        audit_id = request.args.get("audit_id", type=int)
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        result = get_social_preview(url)

        try:
            from database import save_audit, save_social_preview
            summary = {
                "type":          "social_preview",
                "og_score":      result.get("readiness", {}).get("og_score", 0),
                "twitter_score": result.get("readiness", {}).get("twitter_score", 0),
                "has_og":        result.get("readiness", {}).get("has_og", False),
                "has_twitter":   result.get("readiness", {}).get("has_twitter", False),
                "image_ok":      result.get("readiness", {}).get("image_accessible", False),
                "dims_ok":       result.get("readiness", {}).get("image_dimensions_ok", False),
            }
            audit_id = save_audit(url, mode="social_preview", summary=summary, audit_id=audit_id)
            save_social_preview(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (social_preview):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ── Mobile SEO ──
@app.route("/api/mobile_seo")
def mobile_seo_route():
    try:
        from mobile_seo import run_mobile_seo
        url = request.args.get("url", "").strip()
        audit_id = request.args.get("audit_id", type=int)
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        result = run_mobile_seo(url)

        try:
            from database import save_audit, save_mobile_seo
            summary = {
                "type":            "mobile_seo",
                "score":           result.get("summary", {}).get("score", 0),
                "mobile_friendly": result.get("summary", {}).get("mobile_friendly", False),
                "passed":          result.get("summary", {}).get("passed", 0),
                "total":           result.get("summary", {}).get("total", 0),
                "lcp_ms":          result.get("core_web_vitals", {}).get("lcp_ms", 0),
                "cls":             result.get("core_web_vitals", {}).get("cls", 0),
                "inp_ms":          result.get("core_web_vitals", {}).get("inp_ms", 0),
                "viewport_ok":     result.get("viewport", {}).get("ok", False),
                "responsive":      result.get("responsive_design", {}).get("ok", False),
                "tap_targets_ok":  result.get("tap_targets", {}).get("ok", False),
                "font_ok":         result.get("font_readability", {}).get("ok", False),
                "no_popups":       result.get("popups", {}).get("ok", False),
            }
            audit_id = save_audit(url, mode="mobile_seo", summary=summary, audit_id=audit_id)
            save_mobile_seo(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (mobile_seo):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ── Quick Audit (Home + Page) ──
@app.route("/api/quick_audit")
def quick_audit_route():
    try:
        import requests as req
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin, urlparse
        from onpage import analyze_onpage
        from linkanalysis import analyze_links

        url      = request.args.get("url",      "").strip()
        mode     = request.args.get("mode",     "home")
        device   = request.args.get("device",   "desktop")
        audit_id = request.args.get("audit_id", type=int)

        if not url.startswith("http"):
            url = "https://" + url

        domain  = urlparse(url).netloc
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
                if device == "mobile" else
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }

        # Fetch page — Playwright first, fallback requests
        html_content = ""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                ctx     = browser.new_context(user_agent=headers["User-Agent"], ignore_https_errors=True)
                pg      = ctx.new_page()
                pg.goto(url, timeout=20000, wait_until="domcontentloaded")
                pg.wait_for_timeout(1500)
                html_content = pg.content()
                browser.close()
        except Exception:
            try:
                r = req.get(url, headers=headers, timeout=10)
                html_content = r.text
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        soup = BeautifulSoup(html_content, "lxml")

        # ── SEO Analysis ──
        seo = analyze_onpage(url, html_content, headers)

        # ── Link Analysis ──
        links_data = {}
        try:
            links_data = analyze_links(
                url, html_content, domain, headers,
                all_page_depths=None, check_broken=True
            )
        except Exception as e:
            links_data = {
                "internal_count": 0, "external_count": 0, "broken_count": 0,
                "internal_links": [], "external_links": [], "broken_links": [],
                "top_anchors": [], "top_ext_domains": [], "issues": [],
                "error": str(e)
            }

        # ── Canonical ──
        canonical_tag = soup.find("link", rel=lambda r: r and "canonical" in r)
        canonical     = canonical_tag.get("href", "") if canonical_tag else ""

        # ── Schema.org ──
        schemas = []
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                import json as jsonlib
                d = jsonlib.loads(tag.string or "")
                t = d.get("@type", "")
                if isinstance(t, list):
                    schemas.extend(t)
                elif t:
                    schemas.append(t)
            except Exception:
                pass

        # ── Open Graph ──
        og = {}
        for tag in soup.find_all("meta"):
            prop = tag.get("property", "") or tag.get("name", "")
            if prop.startswith("og:"):
                og[prop[3:]] = tag.get("content", "")

        # ── Robots / Noindex ──
        robots_meta    = soup.find("meta", attrs={"name": lambda n: n and n.lower() == "robots"})
        robots_content = robots_meta.get("content", "index, follow") if robots_meta else "index, follow"
        noindex        = "noindex" in robots_content.lower()

        # ── URL Analysis ──
        parsed_url    = urlparse(url)
        url_path      = parsed_url.path
        url_has_https = parsed_url.scheme == "https"

        # ── Redirect ──
        redirect_info = {}
        try:
            r2 = req.head(url, headers=headers, timeout=6, allow_redirects=False)
            if r2.status_code in (301, 302, 307, 308):
                redirect_info = {
                    "has_redirect": True,
                    "status_code":  r2.status_code,
                    "location":     r2.headers.get("Location", "")
                }
            else:
                redirect_info = {"has_redirect": False, "status_code": r2.status_code}
        except Exception:
            redirect_info = {"has_redirect": False}

        # ── Inner Links ──
        inner_links = []
        seen        = set()
        base_clean  = url.rstrip("/")

        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            text = (tag.get_text(strip=True)[:80]
                    or tag.get("title", "")
                    or tag.get("aria-label", "")
                    or "(no text)")
            text = text.strip()[:60]

            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "whatsapp:", "sms:")):
                continue

            full     = urljoin(url, href).split("#")[0].rstrip("/")
            parsed_l = urlparse(full)

            if (parsed_l.netloc == domain
                and full not in seen
                and full != base_clean
                and parsed_l.scheme in ("http", "https")
                and not any(full.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".mp4", ".svg", ".webp"])
            ):
                seen.add(full)
                inner_links.append({
                    "url":    full,
                    "anchor": text,
                    "path":   parsed_l.path or "/",
                })

        inner_links.sort(key=lambda x: len(x["path"]))
        inner_links = inner_links[:20]

        # ── Build result ──
        result = {
            "url":          url,
            "mode":         mode,
            "seo":          seo,
            "links":        links_data,
            "canonical":    canonical,
            "canonical_ok": bool(canonical),
            "schemas":      schemas,
            "has_schema":   len(schemas) > 0,
            "og":           og,
            "has_og":       bool(og),
            "noindex":      noindex,
            "robots":       robots_content,
            "url_analysis": {
                "https":       url_has_https,
                "path":        url_path,
                "path_length": len(url_path),
                "clean_url":   " " not in url and url_path == url_path.lower(),
            },
            "redirect":    redirect_info,
            "inner_links": inner_links,
        }

        # ── Save to database with FULL summary ──
        try:
            from database import save_audit, save_page

            # Shortcuts into seo sub-dicts
            seo_title = seo.get("title",            {})
            seo_meta  = seo.get("meta_description", {})
            seo_h     = seo.get("headings",         {})
            seo_c     = seo.get("content",          {})
            seo_img   = seo.get("images",           {})

            tech_for_db = {
                "canonical":    canonical,
                "canonical_ok": bool(canonical),
                "has_schema":   len(schemas) > 0,
                "schemas":      schemas,
                "has_og":       bool(og),
                "noindex":      noindex,
                "robots":       robots_content,
            }

            # ── FULL summary — every field from the API response ──
            summary = {
                # ── Meta ──
                "type":              mode,
                "url":               url,
                "device":            device,

                # ── SEO Score ──
                "seo_score":         seo.get("seo_score", 0),
                "passed_checks":     seo.get("passed", 0),
                "total_checks":      seo.get("total_checks", 0),

                # ── Title ──
                "title_text":        seo_title.get("text", ""),
                "title_length":      seo_title.get("length", 0),
                "title_ok":          bool(seo_title.get("length_ok")),
                "title_present":     bool(seo_title.get("present")),
                "title_duplicate":   bool(seo_title.get("duplicate")),

                # ── Meta Description ──
                "meta_text":         seo_meta.get("text", ""),
                "meta_length":       seo_meta.get("length", 0),
                "meta_ok":           bool(seo_meta.get("length_ok")),
                "meta_present":      bool(seo_meta.get("present")),

                # ── Headings ──
                "h1_count":          seo_h.get("h1_count", 0),
                "h2_count":          seo_h.get("h2_count", 0),
                "h3_count":          seo_h.get("h3_count", 0),
                "h1_present":        bool(seo_h.get("h1_present")),
                "single_h1":         bool(seo_h.get("single_h1")),
                "h1_text":           seo_h.get("h1_texts", [""])[0] if seo_h.get("h1_texts") else "",

                # ── Content ──
                "word_count":        seo_c.get("word_count", 0),
                "word_count_ok":     bool(seo_c.get("word_count_ok")),
                "readability_score": seo_c.get("readability_score", 0),
                "readability_label": seo_c.get("readability_label", ""),
                "duplicate_content": bool(seo_c.get("duplicate_content")),
                "top_keywords":      seo_c.get("keywords", [])[:5],

                # ── Images ──
                "image_total":       seo_img.get("total", 0),
                "alt_missing":       seo_img.get("missing_alt_count", 0),
                "broken_images":     seo_img.get("broken_count", 0),
                "large_images":      seo_img.get("large_count", 0),
                "img_to_text_ratio": seo_img.get("img_to_text_ratio", 0),

                # ── Links ──
                "internal_links":    links_data.get("internal_count", 0),
                "external_links":    links_data.get("external_count", 0),
                "broken_links":      links_data.get("broken_count", 0),
                "total_links":       links_data.get("total_links", 0),
                "nofollow_count":    links_data.get("nofollow_count", 0),
                "broken_link_urls":  [b.get("url") for b in links_data.get("broken_links", [])[:5]],
                "top_anchors":       links_data.get("top_anchors", [])[:5],
                "top_ext_domains":   links_data.get("top_ext_domains", [])[:5],

                # ── Technical ──
                "canonical_url":     canonical,
                "canonical_ok":      bool(canonical),
                "has_schema":        len(schemas) > 0,
                "schema_types":      schemas,
                "has_og":            bool(og),
                "og_title":          og.get("title", ""),
                "og_description":    og.get("description", ""),
                "og_image":          og.get("image", ""),
                "noindex":           noindex,
                "robots":            robots_content,

                # ── URL ──
                "https":             url_has_https,
                "url_path":          url_path,
                "url_path_length":   len(url_path),
                "clean_url":         " " not in url and url_path == url_path.lower(),

                # ── Redirect ──
                "has_redirect":      redirect_info.get("has_redirect", False),
                "redirect_code":     redirect_info.get("status_code"),
                "redirect_location": redirect_info.get("location", ""),

                # ── Inner Links ──
                "inner_links_count": len(inner_links),
                "inner_links":       inner_links[:10],
            }

            audit_id = save_audit(
                url,
                mode=mode,
                device=device,
                seo_score=seo.get("seo_score"),
                summary=summary,
                audit_id=audit_id,
            )
            page_data = {"url": url, "status": 200, "category": "ok", "depth": 0}
            save_page(audit_id, page_data, seo_data=seo, links_data=links_data, tech_data=tech_for_db)
            from database import save_on_page
            save_on_page(audit_id, url, mode, device, result)

            print(f"✅ Saved audit {audit_id} with full summary for {url}")

        except Exception as e:
            import traceback
            print("DB SAVE ERROR (quick_audit):", e)
            print(traceback.format_exc())

        return jsonify(result)

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ══════════════════════════════════════════
#  DATABASE API ROUTES
# ══════════════════════════════════════════

@app.route("/api/db/audits")
def db_audits():
    try:
        from database import get_all_audits
        return jsonify(get_all_audits())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/audit/<int:audit_id>")
def db_audit(audit_id):
    try:
        from database import get_audit
        return jsonify(get_audit(audit_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── History: past scans for ONE url (Dashboard "History" tab) ──
@app.route("/api/db/history")
def db_history():
    try:
        from database import get_audit_history
        url        = request.args.get("url", "").strip()
        exclude_id = request.args.get("exclude_id", type=int)
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        return jsonify(get_audit_history(url, exclude_id=exclude_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Full reassembled result for ONE past scan (used to "open" history item) ──
@app.route("/api/db/audit_full/<int:audit_id>")
def db_audit_full(audit_id):
    try:
        from database import get_audit_full
        return jsonify(get_audit_full(audit_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/audit/<int:audit_id>/issues")
def db_audit_issues(audit_id):
    try:
        from database import get_audit_issues
        return jsonify(get_audit_issues(audit_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/audit/<int:audit_id>", methods=["DELETE"])
def db_delete_audit(audit_id):
    try:
        from database import delete_audit
        delete_audit(audit_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/stats")
def db_stats():
    try:
        from database import get_audit_stats
        return jsonify(get_audit_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/speed/<path:url>")
def db_speed_history(url):
    try:
        from database import get_page_speed_history
        return jsonify(get_page_speed_history(url))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════
#  SITE CRAWLER — SocketIO routes
# ══════════════════════════════════════════

@socketio.on("start_crawl")
def handle_start_crawl(data):
    from crawler import WebCrawler

    url       = data.get("url", "").strip()
    scan_type = data.get("scan_type", "single")
    depth     = int(data.get("depth", 2))
    device    = data.get("device", "desktop")
    sid       = request.sid

    if not url:
        emit("log", {"msg": "❌ No URL provided.", "type": "error"})
        return
    if not url.startswith("http"):
        url = "https://" + url

    # Stop any existing crawler for this session
    if sid in active_crawlers:
        try:
            active_crawlers[sid].stop()
        except Exception:
            pass

    crawler = WebCrawler(
        base_url  = url,
        scan_type = scan_type,
        depth     = depth,
        device    = device,
        socketio  = socketio,
        sid       = sid,
    )
    active_crawlers[sid] = crawler

    t = threading.Thread(target=crawler.crawl, daemon=True)
    t.start()


@socketio.on("stop_crawl")
def handle_stop_crawl():
    sid = request.sid
    if sid in active_crawlers:
        active_crawlers[sid].stop()
        emit("log", {"msg": "🛑 Crawl stopped by user.", "type": "warn"})


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    if sid in active_crawlers:
        try:
            active_crawlers[sid].stop()
        except Exception:
            pass
        del active_crawlers[sid]


# ── SEO Score ──
@app.route("/api/seo_score", methods=["POST"])
def seo_score_route():
    try:
        from seo_scoring import compute_page_score
        body = request.get_json(force=True, silent=True) or {}

        seo_data   = body.get("seo_data",   {})
        speed_data = body.get("speed_data", {})
        links_data = body.get("links_data", {})
        tech_data  = body.get("tech_data",  {})
        url        = body.get("url",        "")
        audit_id   = body.get("audit_id")

        result = compute_page_score(
            seo_data       = seo_data,
            pagespeed_data = speed_data,
            links_data     = links_data,
            tech_data      = tech_data,
        )
        result["url"] = url

        # Optionally persist to DB
        try:
            from database import save_audit, save_seo_score
            audit_id = save_audit(
                url,
                mode    = "seo_score",
                summary = {
                    "type":       "seo_score",
                    "page_score": result.get("page_score", 0),
                    "label":      result.get("label", ""),
                },
                audit_id = audit_id,
            )
            save_seo_score(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (seo_score):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500



# ── Structured Data Analyser ──
@app.route("/api/structured_data")
def structured_data_route():
    try:
        from structured_data import analyze_structured_data
        url = request.args.get("url", "").strip()
        audit_id = request.args.get("audit_id", type=int)
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        if not url.startswith("http"):
            url = "https://" + url
        result = analyze_structured_data(url)

        try:
            from database import save_audit, save_structured_data
            summary = {
                "type":            "structured_data",
                "has_jsonld":      result.get("has_jsonld", False),
                "has_microdata":   result.get("has_microdata", False),
                "has_rdfa":        result.get("has_rdfa", False),
                "total_schemas":   result.get("total_schemas", 0),
                "overall_score":   result.get("overall_score", 0),
                "score_label":     result.get("score_label", ""),
                "total_errors":    result.get("total_errors", 0),
                "total_warnings":  result.get("total_warnings", 0),
                "schema_types":    result.get("schema_types", []),
                "has_faq":         result.get("has_faq", False),
                "has_article":     result.get("has_article", False),
                "has_product":     result.get("has_product", False),
            }
            audit_id = save_audit(url, mode="structured_data", summary=summary, audit_id=audit_id)
            save_structured_data(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (structured_data):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

@app.route("/api/export", methods=["POST"])
def export_route():
    try:
        from flask import send_file
        from export import generate_pdf, generate_excel
        import io
 
        body   = request.get_json(force=True, silent=True) or {}
        fmt    = body.get("format", "pdf")   # "pdf" ya "excel"
        data   = body                         # poora body pass karo
 
        if fmt == "excel":
            file_bytes = generate_excel(data)
            return send_file(
                io.BytesIO(file_bytes),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"seobit_report_{data.get('url','site').replace('https://','').replace('/','_')}.xlsx"
            )
        else:
            file_bytes = generate_pdf(data)
            return send_file(
                io.BytesIO(file_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"seobit_report_{data.get('url','site').replace('https://','').replace('/','_')}.pdf"
            )
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500
"""
app_ai_patch.py
───────────────
Add this Flask route inside app.py, alongside the other @app.route blocks.
(Paste it anywhere before the `if __name__ == "__main__":` line)
"""

# ── AI Recommendation ──
@app.route("/api/ai_recommendation", methods=["POST"])
def ai_recommendation_route():
    try:
        from ai_recommendation import get_ai_recommendation
        from database import save_audit, save_ai_recommendation

        body       = request.get_json(force=True, silent=True) or {}
        url        = body.get("url", "").strip()
        audit_id   = body.get("audit_id")
        audit_data = body.get("audit_data", {})   # keys: pagespeed, technical,
                                                   # backlinks, mobile_seo,
                                                   # social_preview, seo_score,
                                                   # structured_data

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        result   = get_ai_recommendation(url, audit_data)
        has_data = not result.get("error")

        try:
            audit_id = save_audit(
                url,
                mode    = "ai_recommendation",
                summary = {"type": "ai_recommendation", "has_result": has_data},
                audit_id = audit_id,
            )
            save_ai_recommendation(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (ai_recommendation):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ── Get latest saved AI Recommendation ──
@app.route("/api/ai_recommendation/latest")
def ai_recommendation_latest():
    try:
        from database import get_ai_recommendation
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        return jsonify(get_ai_recommendation(url))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── AI Content Generator (Agent 2 — content writer) ──
@app.route("/api/content_generator", methods=["POST"])
def content_generator_route():
    try:
        from content_generator import generate_content_fixes
        from database import save_audit, save_content_fix

        body            = request.get_json(force=True, silent=True) or {}
        url             = body.get("url", "").strip()
        audit_id        = body.get("audit_id")
        onpage_data     = body.get("onpage_data", {})   # the "seo" dict from /api/quick_audit
        focus_keywords  = body.get("focus_keywords")    # optional list, overrides auto-extracted

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        result   = generate_content_fixes(url, onpage_data, focus_keywords)
        has_data = not result.get("error")

        try:
            audit_id = save_audit(
                url,
                mode    = "content_generator",
                summary = {
                    "type":                       "content_generator",
                    "has_result":                 has_data,
                    "new_title":                  result.get("new_title", ""),
                    "new_meta_description":       result.get("new_meta_description", ""),
                    "new_h1":                     result.get("new_h1", ""),
                    "og_title":                   result.get("og_title", ""),
                    "og_description":             result.get("og_description", ""),
                    "content_expansion":          result.get("content_expansion_paragraph", ""),
                    "readability_fix_note":       result.get("readability_fix_note", ""),
                    "alt_suggestions_count":      len(result.get("alt_text_suggestions", [])),
                    "h2_suggestions_count":       len(result.get("suggested_h2_subheadings", [])),
                    "improvement_notes":          result.get("improvement_notes", ""),
                },
                audit_id = audit_id,
            )
            save_content_fix(audit_id, url, result)
        except Exception as e:
            print("DB SAVE ERROR (content_generator):", e)

        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ── Get latest saved AI Content Generation ──
@app.route("/api/content_generator/latest")
def content_generator_latest():
    try:
        from database import get_content_fix
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        return jsonify(get_content_fix(url))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════════════
# Agent 3 — SEO Assistant Chatbot (Groq-powered, per-session memory)
# ══════════════════════════════════════════════════════════════════════════════

# In-memory store: session_id → list of {role, content}
_chat_sessions: dict = {}

@app.route("/api/chatbot", methods=["POST"])
def chatbot_route():
    """
    POST body (JSON):
      message    (str)  — user's message
      session_id (str)  — unique ID per browser tab/session
      audit_id   (int)  — currently loaded audit ID (optional, 0 if none)
    """
    try:
        from seo_chatbot import chat as groq_chat

        body       = request.get_json(force=True) or {}
        message    = (body.get("message") or "").strip()
        session_id = (body.get("session_id") or "default").strip()
        audit_id   = body.get("audit_id") or None

        if not message:
            return jsonify({"error": "No message provided"}), 400

        # Retrieve or create session history
        history = _chat_sessions.get(session_id, [])

        result = groq_chat(message, history, audit_id=audit_id)

        if result.get("error"):
            return jsonify({"error": result["error"]}), 500

        # Persist updated history
        _chat_sessions[session_id] = result["history"]

        return jsonify({"reply": result["reply"]})

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500
# ══════════════════════════════════════════════════════════════════════════════
# Agent 4 — AI Progress Tracker
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/progress_tracker", methods=["POST"])
def progress_tracker_route():
    """
    POST body (JSON):
      old_audit_id (int) — older audit
      new_audit_id (int) — newer audit
    """
    try:
        from progress_tracker import generate_progress_report
        body = request.get_json(force=True) or {}
        old_id = body.get("old_audit_id")
        new_id = body.get("new_audit_id")
        if not old_id or not new_id:
            return jsonify({"error": "old_audit_id and new_audit_id required"}), 400
        result = generate_progress_report(int(old_id), int(new_id))
        if result.get("error"):
            return jsonify(result), 500
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/chatbot/clear", methods=["POST"])
def chatbot_clear():
    """Clear conversation history for a session."""
    body       = request.get_json(force=True) or {}
    session_id = (body.get("session_id") or "default").strip()
    _chat_sessions.pop(session_id, None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    print(f"🚀 SEO Crawler running at http://localhost:{port}")
    socketio.run(app, debug=debug, host="0.0.0.0", port=port, use_reloader=False, allow_unsafe_werkzeug=True)