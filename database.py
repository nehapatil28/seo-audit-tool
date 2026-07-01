"""
database.py — PostgreSQL database for SEO Crawler
Drop-in replacement for the old SQLite version.
Same function signatures — nothing else in the project needs to change.

Setup (one-time):
  pip install psycopg2-binary
  Set the DATABASE_URL environment variable, e.g.:
    Windows:  set DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/seo_tool
    .env file: DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/seo_tool
"""

import json
import os
import psycopg2
import psycopg2.extras        # RealDictCursor — returns rows as dicts like sqlite3.Row

# ── Connection string from environment (required) ──────────────────────────
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/seo_tool"   # safe local default
)


def get_connection():
    """Return a new psycopg2 connection with RealDictCursor as default."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id          SERIAL PRIMARY KEY,
            url         TEXT    NOT NULL,
            mode        TEXT    DEFAULT 'home',
            device      TEXT    DEFAULT 'desktop',
            seo_score   INTEGER,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            summary     TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id                SERIAL PRIMARY KEY,
            audit_id          INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url               TEXT    NOT NULL,
            status_code       INTEGER,
            category          TEXT,
            depth             INTEGER DEFAULT 0,
            is_orphan         INTEGER DEFAULT 0,
            title             TEXT,
            title_length      INTEGER,
            title_ok          INTEGER,
            title_duplicate   INTEGER DEFAULT 0,
            meta_desc         TEXT,
            meta_length       INTEGER,
            meta_ok           INTEGER,
            h1_count          INTEGER DEFAULT 0,
            h2_count          INTEGER DEFAULT 0,
            h3_count          INTEGER DEFAULT 0,
            h1_text           TEXT,
            word_count        INTEGER DEFAULT 0,
            readability       REAL    DEFAULT 0,
            readability_label TEXT,
            duplicate_content INTEGER DEFAULT 0,
            image_count       INTEGER DEFAULT 0,
            alt_missing       INTEGER DEFAULT 0,
            broken_images     INTEGER DEFAULT 0,
            large_images      INTEGER DEFAULT 0,
            internal_links    INTEGER DEFAULT 0,
            external_links    INTEGER DEFAULT 0,
            broken_links      INTEGER DEFAULT 0,
            canonical         TEXT,
            has_schema        INTEGER DEFAULT 0,
            schemas           TEXT,
            has_og            INTEGER DEFAULT 0,
            noindex           INTEGER DEFAULT 0,
            robots            TEXT,
            keywords          TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id          SERIAL PRIMARY KEY,
            audit_id    INTEGER REFERENCES audits(id)  ON DELETE CASCADE,
            page_id     INTEGER REFERENCES pages(id)   ON DELETE CASCADE,
            url         TEXT,
            type        TEXT,
            category    TEXT,
            message     TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS page_speed (
            id                SERIAL PRIMARY KEY,
            audit_id          INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url               TEXT    NOT NULL,
            strategy          TEXT    DEFAULT 'desktop',
            source            TEXT,
            performance_score INTEGER,
            lcp_ms            REAL,
            fcp_ms            REAL,
            cls_val           REAL,
            tbt_ms            REAL,
            si_ms             REAL,
            tti_ms            REAL,
            ttfb_ms           REAL,
            total_js_kb       REAL,
            total_css_kb      REAL,
            total_img_kb      REAL,
            unused_js_kb      REAL,
            unused_css_kb     REAL,
            page_size_kb      REAL,
            total_requests    INTEGER,
            render_blocking   INTEGER DEFAULT 0,
            lazy_issues       INTEGER DEFAULT 0,
            opportunities     TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS on_page (
            id              SERIAL PRIMARY KEY,
            audit_id        INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url             TEXT    NOT NULL,
            mode            TEXT,
            device          TEXT,
            seo_score       INTEGER,
            title_present   INTEGER DEFAULT 0,
            meta_present    INTEGER DEFAULT 0,
            h1_count        INTEGER DEFAULT 0,
            internal_links  INTEGER DEFAULT 0,
            external_links  INTEGER DEFAULT 0,
            broken_links    INTEGER DEFAULT 0,
            images_total    INTEGER DEFAULT 0,
            images_missing_alt INTEGER DEFAULT 0,
            full_result     TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS technical_seo (
            id              SERIAL PRIMARY KEY,
            audit_id        INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url             TEXT    NOT NULL,
            score           INTEGER,
            https_enabled   INTEGER DEFAULT 0,
            http_redirects  INTEGER DEFAULT 0,
            robots_present  INTEGER DEFAULT 0,
            sitemap_present INTEGER DEFAULT 0,
            sitemap_urls    INTEGER DEFAULT 0,
            canonical_ok    INTEGER DEFAULT 0,
            duplicate_urls  INTEGER DEFAULT 0,
            crawl_errors    INTEGER DEFAULT 0,
            full_result     TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS backlinks (
            id                      SERIAL PRIMARY KEY,
            audit_id                INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url                     TEXT    NOT NULL,
            overall_score           INTEGER DEFAULT 0,
            external_links          INTEGER DEFAULT 0,
            unique_domains          INTEGER DEFAULT 0,
            dofollow_count          INTEGER DEFAULT 0,
            nofollow_count          INTEGER DEFAULT 0,
            high_authority_links    INTEGER DEFAULT 0,
            broken_external_count   INTEGER DEFAULT 0,
            link_equity_score       INTEGER DEFAULT 0,
            full_result             TEXT,
            created_at              TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mobile_seo (
            id                  SERIAL PRIMARY KEY,
            audit_id            INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url                 TEXT    NOT NULL,
            score               INTEGER DEFAULT 0,
            mobile_friendly     INTEGER DEFAULT 0,
            passed_checks       INTEGER DEFAULT 0,
            total_checks        INTEGER DEFAULT 0,
            lcp_ms              REAL    DEFAULT 0,
            cls_val             REAL    DEFAULT 0,
            inp_ms              REAL    DEFAULT 0,
            viewport_ok         INTEGER DEFAULT 0,
            responsive          INTEGER DEFAULT 0,
            tap_targets_ok      INTEGER DEFAULT 0,
            font_ok             INTEGER DEFAULT 0,
            no_popups           INTEGER DEFAULT 0,
            full_result         TEXT,
            created_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS social_preview (
            id              SERIAL PRIMARY KEY,
            audit_id        INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url             TEXT    NOT NULL,
            og_score        INTEGER DEFAULT 0,
            twitter_score   INTEGER DEFAULT 0,
            has_og          INTEGER DEFAULT 0,
            has_twitter     INTEGER DEFAULT 0,
            image_ok        INTEGER DEFAULT 0,
            dims_ok         INTEGER DEFAULT 0,
            og_title        TEXT,
            og_description  TEXT,
            og_image        TEXT,
            twitter_title   TEXT,
            twitter_image   TEXT,
            full_result     TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS structured_data (
            id              SERIAL PRIMARY KEY,
            audit_id        INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url             TEXT    NOT NULL,
            overall_score   INTEGER DEFAULT 0,
            score_label     TEXT,
            has_jsonld      INTEGER DEFAULT 0,
            has_microdata   INTEGER DEFAULT 0,
            has_rdfa        INTEGER DEFAULT 0,
            total_schemas   INTEGER DEFAULT 0,
            total_errors    INTEGER DEFAULT 0,
            total_warnings  INTEGER DEFAULT 0,
            schema_types    TEXT,
            has_faq         INTEGER DEFAULT 0,
            has_article     INTEGER DEFAULT 0,
            has_product     INTEGER DEFAULT 0,
            full_result     TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS seo_scores (
            id              SERIAL PRIMARY KEY,
            audit_id        INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url             TEXT    NOT NULL,
            page_score      INTEGER DEFAULT 0,
            label           TEXT,
            title_score     INTEGER DEFAULT 0,
            meta_score      INTEGER DEFAULT 0,
            heading_score   INTEGER DEFAULT 0,
            content_score   INTEGER DEFAULT 0,
            image_score     INTEGER DEFAULT 0,
            link_score      INTEGER DEFAULT 0,
            speed_score     INTEGER DEFAULT 0,
            tech_score      INTEGER DEFAULT 0,
            full_result     TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id               SERIAL PRIMARY KEY,
            audit_id         INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url              TEXT    NOT NULL,
            summary          TEXT,
            critical_issues  TEXT,
            quick_wins       TEXT,
            long_term        TEXT,
            priority_actions TEXT,
            raw_text         TEXT,
            error            TEXT,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS content_generations (
            id                    SERIAL PRIMARY KEY,
            audit_id              INTEGER REFERENCES audits(id) ON DELETE CASCADE,
            url                   TEXT    NOT NULL,
            new_title             TEXT,
            new_meta_description  TEXT,
            new_h1                TEXT,
            alt_text_suggestions  TEXT,
            improvement_notes     TEXT,
            raw_text              TEXT,
            error                 TEXT,
            created_at            TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ PostgreSQL database initialized: {DATABASE_URL.split('@')[-1]}")


# ══════════════════════════════════════════
#  SAVE FUNCTIONS
# ══════════════════════════════════════════

def create_audit(url, device="desktop"):
    """
    Create ONE master audit row for a full scan session.
    Called once when the loading page starts — every subsequent
    mode-route (technical, backlinks, social_preview, ...) reuses
    this same audit_id instead of creating its own row.
    Returns audit_id.
    """
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO audits (url, mode, device)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (url, "full_scan", device))
    audit_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return audit_id


def save_audit(url, mode="home", device="desktop", seo_score=None, summary=None, audit_id=None):
    """
    Save/update an audit.

    - If audit_id IS given (session-based flow): reuse that existing row
      instead of inserting a new one, so all modes of one scan share a
      single id.
    - If audit_id is NOT given (old/standalone behaviour — kept for
      backward compatibility): inserts a brand-new row, exactly as before.

    Returns audit_id either way.
    """
    summary_json = json.dumps(summary, ensure_ascii=False) if summary is not None else None
    conn = get_connection()
    cur  = conn.cursor()

    if audit_id:
        cur.execute("""
            UPDATE audits
            SET seo_score = COALESCE(%s, seo_score),
                summary    = COALESCE(%s, summary),
                mode       = CASE WHEN mode = 'full_scan' THEN %s ELSE mode END
            WHERE id = %s
        """, (seo_score, summary_json, mode, audit_id))
        conn.commit()
        cur.close()
        conn.close()
        return audit_id

    cur.execute("""
        INSERT INTO audits (url, mode, device, seo_score, summary)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (url, mode, device, seo_score, summary_json))
    audit_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return audit_id


def save_page(audit_id, page_data, seo_data=None, links_data=None, tech_data=None):
    """Save one page result under an audit."""
    seo = seo_data or {}
    t   = seo.get("title",            {})
    m   = seo.get("meta_description", {})
    h   = seo.get("headings",         {})
    c   = seo.get("content",          {})
    img = seo.get("images",           {})
    lnk = links_data or {}

    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO pages (
            audit_id, url, status_code, category, depth, is_orphan,
            title, title_length, title_ok, title_duplicate,
            meta_desc, meta_length, meta_ok,
            h1_count, h2_count, h3_count, h1_text,
            word_count, readability, readability_label, duplicate_content,
            image_count, alt_missing, broken_images, large_images,
            internal_links, external_links, broken_links,
            canonical, has_schema, schemas, has_og, noindex, robots,
            keywords
        ) VALUES (
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s
        ) RETURNING id
    """, (
        audit_id,
        page_data.get("url", ""),
        page_data.get("status"),
        page_data.get("category", "ok"),
        page_data.get("depth", 0),
        1 if page_data.get("orphan") else 0,

        t.get("text", ""),
        t.get("length", 0),
        1 if t.get("length_ok") else 0,
        1 if t.get("duplicate") else 0,

        m.get("text", ""),
        m.get("length", 0),
        1 if m.get("length_ok") else 0,

        h.get("h1_count", 0),
        h.get("h2_count", 0),
        h.get("h3_count", 0),
        h.get("h1_texts", [""])[0] if h.get("h1_texts") else "",

        c.get("word_count", 0),
        c.get("readability_score", 0),
        c.get("readability_label", ""),
        1 if c.get("duplicate_content") else 0,

        img.get("total", 0),
        img.get("missing_alt_count", 0),
        img.get("broken_count", 0),
        img.get("large_count", 0),

        lnk.get("internal_count", 0),
        lnk.get("external_count", 0),
        lnk.get("broken_count", 0),

        tech_data.get("canonical", "")         if tech_data else "",
        1 if tech_data and tech_data.get("has_schema") else 0,
        json.dumps(tech_data.get("schemas", []) if tech_data else []),
        1 if tech_data and tech_data.get("has_og") else 0,
        1 if tech_data and tech_data.get("noindex") else 0,
        tech_data.get("robots", "")            if tech_data else "",

        json.dumps(c.get("keywords", [])[:10]),
    ))
    page_id = cur.fetchone()["id"]
    _save_issues(cur, audit_id, page_id, page_data.get("url", ""), seo, tech_data)
    conn.commit()
    cur.close()
    conn.close()
    return page_id


def _save_issues(cur, audit_id, page_id, url, seo, tech_data):
    t   = seo.get("title",            {})
    m   = seo.get("meta_description", {})
    h   = seo.get("headings",         {})
    c   = seo.get("content",          {})
    img = seo.get("images",           {})
    issues = []

    if not t.get("present"):
        issues.append(("error",   "title",   "Title tag is missing"))
    elif not t.get("length_ok"):
        issues.append(("warning", "title",   f"Title length {t.get('length',0)} chars — ideal 30–60"))
    if t.get("duplicate"):
        issues.append(("error",   "title",   "Duplicate title detected"))

    if not m.get("present"):
        issues.append(("error",   "meta",    "Meta description is missing"))
    elif not m.get("length_ok"):
        issues.append(("warning", "meta",    f"Meta length {m.get('length',0)} chars — ideal 120–160"))

    if not h.get("h1_present"):
        issues.append(("error",   "heading", "H1 tag is missing"))
    if not h.get("single_h1") and h.get("h1_count", 0) > 1:
        issues.append(("warning", "heading", f"Multiple H1 tags: {h.get('h1_count',0)}"))

    if not c.get("word_count_ok"):
        issues.append(("warning", "content", f"Low word count: {c.get('word_count',0)} words"))
    if c.get("duplicate_content"):
        issues.append(("error",   "content", "Duplicate content detected"))

    if img.get("missing_alt_count", 0) > 0:
        issues.append(("warning", "image",   f"{img.get('missing_alt_count',0)} images missing alt tags"))
    if img.get("broken_count", 0) > 0:
        issues.append(("error",   "image",   f"{img.get('broken_count',0)} broken images"))
    if img.get("large_count", 0) > 0:
        issues.append(("warning", "image",   f"{img.get('large_count',0)} oversized images (>200KB)"))

    if tech_data:
        if not tech_data.get("canonical_ok"):
            issues.append(("warning", "technical", "Canonical tag is missing"))
        if tech_data.get("noindex"):
            issues.append(("error",   "technical", "NOINDEX — page won't be indexed"))
        if not tech_data.get("has_schema"):
            issues.append(("warning", "technical", "Schema.org markup is missing"))
        if not tech_data.get("has_og"):
            issues.append(("warning", "technical", "Open Graph tags are missing"))

    for itype, icat, imsg in issues:
        cur.execute("""
            INSERT INTO issues (audit_id, page_id, url, type, category, message)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (audit_id, page_id, url, itype, icat, imsg))


def save_page_speed(audit_id, url, speed_data):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO page_speed (
            audit_id, url, strategy, source, performance_score,
            lcp_ms, fcp_ms, cls_val, tbt_ms, si_ms, tti_ms, ttfb_ms,
            total_js_kb, total_css_kb, total_img_kb,
            unused_js_kb, unused_css_kb, page_size_kb,
            total_requests, render_blocking, lazy_issues, opportunities
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        speed_data.get("strategy", "desktop"),
        speed_data.get("source", "playwright"),
        speed_data.get("performance_score"),
        speed_data.get("lcp_ms"),
        speed_data.get("fcp_ms"),
        speed_data.get("cls"),
        speed_data.get("tbt_ms"),
        speed_data.get("si_ms"),
        speed_data.get("tti_ms"),
        speed_data.get("ttfb_ms"),
        speed_data.get("total_js_kb",   0),
        speed_data.get("total_css_kb",  0),
        speed_data.get("total_img_kb",  0),
        speed_data.get("unused_js_kb",  0),
        speed_data.get("unused_css_kb", 0),
        speed_data.get("page_size_kb",  0),
        speed_data.get("total_requests", 0),
        speed_data.get("render_blocking_count", 0),
        speed_data.get("lazy_load_count", 0),
        json.dumps(speed_data.get("opportunities", [])),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_on_page(audit_id, url, mode, device, result):
    """
    Save the FULL raw result of quick_audit (the 'home' page on-page scan)
    so the History tab can re-render the Overview / On-Page tab exactly
    as it looked originally — same as technical/backlinks/etc already do
    via their `full_result` column.
    """
    seo = result.get("seo", {}) or {}
    lnk = result.get("links", {}) or {}
    img = seo.get("images", {}) or {}

    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO on_page (
            audit_id, url, mode, device, seo_score,
            title_present, meta_present, h1_count,
            internal_links, external_links, broken_links,
            images_total, images_missing_alt, full_result
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url, mode, device,
        seo.get("seo_score"),
        1 if seo.get("title", {}).get("present") else 0,
        1 if seo.get("meta_description", {}).get("present") else 0,
        seo.get("h1_count", 0),
        lnk.get("internal_count", 0),
        lnk.get("external_count", 0),
        lnk.get("broken_count", 0),
        img.get("total", 0),
        img.get("missing_alt_count", 0),
        json.dumps(result, ensure_ascii=False),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_technical(audit_id, url, tech_result):
    checks = tech_result.get("checks", {})
    conn   = get_connection()
    cur    = conn.cursor()
    cur.execute("""
        INSERT INTO technical_seo (
            audit_id, url, score,
            https_enabled, http_redirects,
            robots_present, sitemap_present, sitemap_urls,
            canonical_ok, duplicate_urls, crawl_errors, full_result
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        tech_result.get("score", 0),
        1 if checks.get("https", {}).get("enabled")        else 0,
        1 if checks.get("https", {}).get("http_redirects") else 0,
        1 if checks.get("robots_txt", {}).get("present")   else 0,
        1 if checks.get("sitemap", {}).get("present")      else 0,
        checks.get("sitemap", {}).get("url_count", 0),
        1 if checks.get("canonical", {}).get("homepage_has_canonical") else 0,
        checks.get("duplicate_urls", {}).get("count", 0),
        checks.get("crawl_errors", {}).get("total", 0),
        json.dumps(tech_result),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_backlinks(audit_id, url, result):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO backlinks (
            audit_id, url, overall_score, external_links, unique_domains,
            dofollow_count, nofollow_count, high_authority_links,
            broken_external_count, link_equity_score, full_result
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        result.get("overall_score", 0),
        result.get("external_links", 0),
        result.get("unique_external_domains", 0),
        result.get("dofollow_count", 0),
        result.get("nofollow_count", 0),
        result.get("high_authority_links", 0),
        result.get("broken_external_count", 0),
        result.get("link_equity_score", 0),
        json.dumps(result, ensure_ascii=False),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_mobile_seo(audit_id, url, result):
    summary = result.get("summary", {})
    cwv     = result.get("core_web_vitals", {})
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO mobile_seo (
            audit_id, url, score, mobile_friendly, passed_checks, total_checks,
            lcp_ms, cls_val, inp_ms, viewport_ok, responsive,
            tap_targets_ok, font_ok, no_popups, full_result
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        summary.get("score", 0),
        1 if summary.get("mobile_friendly") else 0,
        summary.get("passed", 0),
        summary.get("total", 0),
        cwv.get("lcp_ms", 0),
        cwv.get("cls", 0),
        cwv.get("inp_ms", 0),
        1 if result.get("viewport", {}).get("ok") else 0,
        1 if result.get("responsive_design", {}).get("ok") else 0,
        1 if result.get("tap_targets", {}).get("ok") else 0,
        1 if result.get("font_readability", {}).get("ok") else 0,
        1 if result.get("popups", {}).get("ok") else 0,
        json.dumps(result, ensure_ascii=False),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_social_preview(audit_id, url, result):
    readiness = result.get("readiness", {})
    og        = result.get("og_tags", {})
    tw        = result.get("twitter_tags", {})
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO social_preview (
            audit_id, url, og_score, twitter_score, has_og, has_twitter,
            image_ok, dims_ok, og_title, og_description, og_image,
            twitter_title, twitter_image, full_result
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        readiness.get("og_score", 0),
        readiness.get("twitter_score", 0),
        1 if readiness.get("has_og") else 0,
        1 if readiness.get("has_twitter") else 0,
        1 if readiness.get("image_accessible") else 0,
        1 if readiness.get("image_dimensions_ok") else 0,
        og.get("og:title", ""),
        og.get("og:description", ""),
        og.get("og:image", ""),
        tw.get("twitter:title", ""),
        tw.get("twitter:image", ""),
        json.dumps(result, ensure_ascii=False),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_structured_data(audit_id, url, result):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO structured_data (
            audit_id, url, overall_score, score_label,
            has_jsonld, has_microdata, has_rdfa,
            total_schemas, total_errors, total_warnings, schema_types,
            has_faq, has_article, has_product, full_result
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        result.get("overall_score", 0),
        result.get("score_label", ""),
        1 if result.get("has_jsonld") else 0,
        1 if result.get("has_microdata") else 0,
        1 if result.get("has_rdfa") else 0,
        result.get("total_schemas", 0),
        result.get("total_errors", 0),
        result.get("total_warnings", 0),
        json.dumps(result.get("schema_types", [])),
        1 if result.get("has_faq") else 0,
        1 if result.get("has_article") else 0,
        1 if result.get("has_product") else 0,
        json.dumps(result, ensure_ascii=False),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_seo_score(audit_id, url, result):
    breakdown = result.get("breakdown", {})
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO seo_scores (
            audit_id, url, page_score, label,
            title_score, meta_score, heading_score, content_score,
            image_score, link_score, speed_score, tech_score, full_result
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        result.get("page_score", 0),
        result.get("label", ""),
        breakdown.get("title", 0),
        breakdown.get("meta", 0),
        breakdown.get("headings", 0),
        breakdown.get("content", 0),
        breakdown.get("images", 0),
        breakdown.get("links", 0),
        breakdown.get("speed", 0),
        breakdown.get("technical", 0),
        json.dumps(result, ensure_ascii=False),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_ai_recommendation(audit_id, url, result):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO ai_recommendations (
            audit_id, url, summary, critical_issues,
            quick_wins, long_term, priority_actions, raw_text, error
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        result.get("summary", ""),
        json.dumps(result.get("critical_issues", []), ensure_ascii=False),
        json.dumps(result.get("quick_wins",      []), ensure_ascii=False),
        json.dumps(result.get("long_term",        []), ensure_ascii=False),
        json.dumps(result.get("priority_actions", []), ensure_ascii=False),
        result.get("raw_text", ""),
        result.get("error",    ""),
    ))
    conn.commit()
    cur.close()
    conn.close()


def save_content_fix(audit_id, url, result):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO content_generations (
            audit_id, url, new_title, new_meta_description,
            new_h1, alt_text_suggestions, improvement_notes, raw_text, error
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        audit_id, url,
        result.get("new_title", ""),
        result.get("new_meta_description", ""),
        result.get("new_h1", ""),
        json.dumps(result.get("alt_text_suggestions", []), ensure_ascii=False),
        result.get("improvement_notes", ""),
        result.get("raw_text", ""),
        result.get("error", ""),
    ))
    conn.commit()
    cur.close()
    conn.close()


# ══════════════════════════════════════════
#  GET / READ FUNCTIONS
# ══════════════════════════════════════════

def _parse_summary(row_dict):
    if row_dict.get("summary") and isinstance(row_dict["summary"], str):
        try:
            row_dict["summary"] = json.loads(row_dict["summary"])
        except Exception:
            pass
    return row_dict


def get_all_audits():
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT a.*, COUNT(p.id) as page_count
        FROM audits a
        LEFT JOIN pages p ON p.audit_id = a.id
        GROUP BY a.id
        ORDER BY a.created_at DESC
    """)
    rows = [_parse_summary(dict(r)) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_audit(audit_id):
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM audits WHERE id = %s", (audit_id,))
    audit = _parse_summary(dict(cur.fetchone() or {}))

    cur.execute("SELECT * FROM pages WHERE audit_id = %s ORDER BY depth, url", (audit_id,))
    audit["pages"] = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM issues WHERE audit_id = %s ORDER BY type DESC", (audit_id,))
    audit["issues"] = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return audit


def get_audit_issues(audit_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT type, category, message, url, COUNT(*) as count
        FROM issues WHERE audit_id = %s
        GROUP BY type, category, message, url
        ORDER BY type DESC, count DESC
    """, (audit_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_page_speed_history(url):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT * FROM page_speed WHERE url = %s
        ORDER BY created_at DESC LIMIT 10
    """, (url,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_audit_stats():
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(DISTINCT a.id)        as total_audits,
            COUNT(p.id)                 as total_pages,
            AVG(p.word_count)           as avg_word_count,
            SUM(p.alt_missing)          as total_alt_missing,
            SUM(p.broken_images)        as total_broken_images,
            COUNT(CASE WHEN p.title_ok=0 THEN 1 END) as pages_bad_title,
            COUNT(CASE WHEN p.meta_ok=0  THEN 1 END) as pages_bad_meta,
            COUNT(CASE WHEN p.h1_count=0 THEN 1 END) as pages_no_h1
        FROM audits a
        LEFT JOIN pages p ON p.audit_id = a.id
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return {
            "total_audits": 0, "total_pages": 0, "avg_word_count": 0,
            "total_alt_missing": 0, "total_broken_images": 0,
            "pages_bad_title": 0, "pages_bad_meta": 0, "pages_no_h1": 0,
        }
    return {
        "total_audits":        row["total_audits"]        or 0,
        "total_pages":         row["total_pages"]         or 0,
        "avg_word_count":      round(float(row["avg_word_count"]), 1) if row["avg_word_count"] else 0,
        "total_alt_missing":   row["total_alt_missing"]   or 0,
        "total_broken_images": row["total_broken_images"] or 0,
        "pages_bad_title":     row["pages_bad_title"]     or 0,
        "pages_bad_meta":      row["pages_bad_meta"]      or 0,
        "pages_no_h1":         row["pages_no_h1"]         or 0,
    }


def delete_audit(audit_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM audits WHERE id = %s", (audit_id,))
    conn.commit()
    cur.close()
    conn.close()


def get_backlinks(audit_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM backlinks WHERE audit_id = %s ORDER BY created_at DESC LIMIT 1", (audit_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


def get_mobile_seo(audit_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM mobile_seo WHERE audit_id = %s ORDER BY created_at DESC LIMIT 1", (audit_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


def get_social_preview(audit_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM social_preview WHERE audit_id = %s ORDER BY created_at DESC LIMIT 1", (audit_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


def get_structured_data(audit_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM structured_data WHERE audit_id = %s ORDER BY created_at DESC LIMIT 1", (audit_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


def get_audit_history(url, limit=20, exclude_id=None):
    """
    List of past scans for ONE url — newest first.
    Each item: id, created_at, device, seo_score, mode.
    `exclude_id`, if given, skips that one row — used so the CURRENT
    session's own just-created audit doesn't show up as its own "latest"
    history entry; the real previous scan shows instead.
    """
    conn = get_connection()
    cur  = conn.cursor()
    if exclude_id:
        cur.execute("""
            SELECT id, created_at, device, seo_score, mode
            FROM audits
            WHERE url = %s AND id != %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (url, exclude_id, limit))
    else:
        cur.execute("""
            SELECT id, created_at, device, seo_score, mode
            FROM audits
            WHERE url = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (url, limit))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_audit_full(audit_id):
    """
    Re-assemble ONE past scan's full result set, in the SAME shape the
    live dashboard cache uses (auditData/techData/speedData/backlinkData/
    socialData/schemaData/mobileData) so it can be fed straight into the
    existing `_restoreFromCache()` JS function — no separate render path
    needed for history. auditData now comes from the real `on_page`
    full_result (same as the other modes), not a best-effort summary.
    """
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("SELECT * FROM audits WHERE id = %s", (audit_id,))
    audit = cur.fetchone()
    audit = dict(audit) if audit else {}

    def _full_result(table):
        cur.execute(f"SELECT full_result FROM {table} WHERE audit_id = %s ORDER BY created_at DESC LIMIT 1", (audit_id,))
        row = cur.fetchone()
        if not row or not row.get("full_result"):
            return None
        try:
            return json.loads(row["full_result"])
        except Exception:
            return None

    audit_data    = _full_result("on_page")
    tech_data     = _full_result("technical_seo")
    backlink_data = _full_result("backlinks")
    mobile_data   = _full_result("mobile_seo")
    social_data   = _full_result("social_preview")
    schema_data   = _full_result("structured_data")

    # page_speed has no full_result column — rebuild the key fields the
    # speed-tab render function reads, from the individual columns.
    cur.execute("SELECT * FROM page_speed WHERE audit_id = %s ORDER BY created_at DESC LIMIT 1", (audit_id,))
    ps_row = cur.fetchone()
    speed_data = None
    if ps_row:
        ps = dict(ps_row)
        try:
            opportunities = json.loads(ps.get("opportunities") or "[]")
        except Exception:
            opportunities = []
        speed_data = {
            "strategy":               ps.get("strategy"),
            "performance_score":      ps.get("performance_score"),
            "lcp_ms":                 ps.get("lcp_ms"),
            "fcp_ms":                 ps.get("fcp_ms"),
            "cls":                    ps.get("cls_val"),
            "tbt_ms":                 ps.get("tbt_ms"),
            "si_ms":                  ps.get("si_ms"),
            "tti_ms":                 ps.get("tti_ms"),
            "ttfb_ms":                ps.get("ttfb_ms"),
            "total_js_kb":            ps.get("total_js_kb"),
            "total_css_kb":           ps.get("total_css_kb"),
            "total_img_kb":           ps.get("total_img_kb"),
            "unused_js_kb":           ps.get("unused_js_kb"),
            "unused_css_kb":          ps.get("unused_css_kb"),
            "page_size_kb":           ps.get("page_size_kb"),
            "total_requests":         ps.get("total_requests"),
            "render_blocking_count":  ps.get("render_blocking"),
            "opportunities":          opportunities,
        }

    cur.close()
    conn.close()

    return {
        "audit_id":     audit_id,
        "url":          audit.get("url"),
        "device":       audit.get("device"),
        "created_at":   str(audit.get("created_at") or ""),
        "seo_score":    audit.get("seo_score"),
        "auditData":    audit_data,
        "techData":     tech_data,
        "speedData":    speed_data,
        "backlinkData": backlink_data,
        "socialData":   social_data,
        "schemaData":   schema_data,
        "mobileData":   mobile_data,
    }


def get_seo_score(audit_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM seo_scores WHERE audit_id = %s ORDER BY created_at DESC LIMIT 1", (audit_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


def get_ai_recommendation(url):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT * FROM ai_recommendations
        WHERE url = %s
        ORDER BY created_at DESC LIMIT 1
    """, (url,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return {}
    rec = dict(row)
    for field in ("critical_issues", "quick_wins", "long_term", "priority_actions"):
        try:
            rec[field] = json.loads(rec[field] or "[]")
        except Exception:
            rec[field] = []
    return rec


def get_content_fix(url):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT * FROM content_generations
        WHERE url = %s
        ORDER BY created_at DESC LIMIT 1
    """, (url,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return {}
    rec = dict(row)
    try:
        rec["alt_text_suggestions"] = json.loads(rec["alt_text_suggestions"] or "[]")
    except Exception:
        rec["alt_text_suggestions"] = []
    return rec


# Initialize on import
init_db()