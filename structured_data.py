import gzip
import json
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse

from bs4 import BeautifulSoup


# ─────────────────────────────────────────────
#  VALIDATION RULES
#  Source: Google Rich Results documentation
# ─────────────────────────────────────────────
VALIDATION_RULES = {
    "FAQPage": {
        "required":    ["mainEntity"],
        "recommended": [],
        "child_rules": {
            "mainEntity": {
                "type":     "Question",
                "required": ["name", "acceptedAnswer"],
                "child_rules": {
                    "acceptedAnswer": {
                        "type":     "Answer",
                        "required": ["text"],
                    }
                }
            }
        }
    },
    "Article": {
        "required":    ["headline", "author", "datePublished"],
        "recommended": ["image", "dateModified", "publisher", "description"],
    },
    "NewsArticle": {
        "required":    ["headline", "author", "datePublished"],
        "recommended": ["image", "dateModified", "publisher", "description"],
    },
    "BlogPosting": {
        "required":    ["headline", "author", "datePublished"],
        "recommended": ["image", "dateModified", "publisher", "description"],
    },
    "Product": {
        "required":    ["name"],
        "recommended": ["image", "description", "offers", "brand",
                        "sku", "aggregateRating", "review"],
    },
    "LocalBusiness": {
        "required":    ["name", "address"],
        "recommended": ["telephone", "openingHours", "geo", "url",
                        "image", "priceRange"],
    },
    "Organization": {
        "required":    ["name"],
        "recommended": ["url", "logo", "contactPoint", "sameAs"],
    },
    "WebSite": {
        "required":    ["name", "url"],
        "recommended": ["potentialAction"],
    },
    "BreadcrumbList": {
        "required":    ["itemListElement"],
        "recommended": [],
    },
    "Event": {
        "required":    ["name", "startDate", "location"],
        "recommended": ["endDate", "description", "image", "offers", "organizer"],
    },
    "Recipe": {
        "required":    ["name", "image", "author", "datePublished",
                        "description", "recipeYield", "recipeIngredient",
                        "recipeInstructions"],
        "recommended": ["totalTime", "nutrition", "aggregateRating"],
    },
    "JobPosting": {
        "required":    ["title", "description", "datePosted",
                        "hiringOrganization", "jobLocation"],
        "recommended": ["baseSalary", "employmentType", "validThrough"],
    },
    "Review": {
        "required":    ["itemReviewed", "reviewRating", "author"],
        "recommended": ["datePublished", "reviewBody"],
    },
    "SoftwareApplication": {
        "required":    ["name", "operatingSystem", "applicationCategory",
                        "offers", "aggregateRating"],
        "recommended": ["description", "url", "image"],
    },
    "VideoObject": {
        "required":    ["name", "description", "thumbnailUrl", "uploadDate"],
        "recommended": ["duration", "contentUrl", "embedUrl"],
    },
    "HowTo": {
        "required":    ["name", "step"],
        "recommended": ["image", "totalTime", "supply", "tool"],
    },
}

TYPE_ALIASES = {
    "newsarticle":         "NewsArticle",
    "blogposting":         "BlogPosting",
    "article":             "Article",
    "faqpage":             "FAQPage",
    "product":             "Product",
    "localbusiness":       "LocalBusiness",
    "organization":        "Organization",
    "website":             "WebSite",
    "breadcrumblist":      "BreadcrumbList",
    "event":               "Event",
    "recipe":              "Recipe",
    "jobposting":          "JobPosting",
    "review":              "Review",
    "aggregaterating":     "AggregateRating",
    "softwareapplication": "SoftwareApplication",
    "videoobject":         "VideoObject",
    "howto":               "HowTo",
}

ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting"}

REQUEST_TIMEOUT = 15

# Multiple User-Agents to rotate on 403
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def _make_headers(ua_index=0):
    return {
        "User-Agent":      _USER_AGENTS[ua_index % len(_USER_AGENTS)],
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection":      "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":  "document",
        "Sec-Fetch-Mode":  "navigate",
        "Sec-Fetch-Site":  "none",
        "Sec-Fetch-User":  "?1",
        "Cache-Control":   "max-age=0",
    }

# Keep HEADERS for backward compat
HEADERS = _make_headers(0)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _canonical_type(raw):
    return TYPE_ALIASES.get(raw.lower(), raw)


def _get_type(schema):
    t = schema.get("@type", "")
    if isinstance(t, list):
        t = t[0] if t else ""
    return t or ""


def _has_value(v):
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def _fetch(url):
    """Fetch with urllib + UA rotation. On 403, tries all user agents before giving up."""
    last_exc = None
    for i, ua in enumerate(_USER_AGENTS):
        headers = _make_headers(i)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                charset = "utf-8"
                ct = resp.headers.get_content_type() or ""
                if "charset=" in ct:
                    charset = ct.split("charset=")[-1].strip().split(";")[0].strip()
                raw_bytes = resp.read(500_000)
                # Decompress gzip if server ignored our missing Accept-Encoding
                encoding = resp.headers.get("Content-Encoding", "")
                if encoding == "gzip" or (raw_bytes[:2] == b'\x1f\x8b'):
                    raw_bytes = gzip.decompress(raw_bytes)
                html = raw_bytes.decode(charset, errors="replace")
                return html, resp.status, resp.url
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503):
                last_exc = e
                time.sleep(0.3)
                continue
            raise
    raise last_exc


# ─────────────────────────────────────────────
#  EXTRACTION
# ─────────────────────────────────────────────

def _extract_jsonld(soup):
    schemas = []
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text()
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            schemas.append({"_parse_error": str(e), "_raw": raw[:200]})
            continue
        if isinstance(data, dict) and "@graph" in data:
            for item in data["@graph"]:
                item.setdefault("@context", data.get("@context", ""))
                schemas.append(item)
        elif isinstance(data, list):
            schemas.extend(data)
        else:
            schemas.append(data)
    return schemas


def _detect_microdata(soup):
    types = []
    for tag in soup.find_all(attrs={"itemscope": True}):
        itype = tag.get("itemtype", "")
        if itype:
            tname = itype.rstrip("/").split("/")[-1]
            if tname:
                types.append(tname)
    return list(set(types))


def _detect_rdfa(soup):
    types = []
    for tag in soup.find_all(attrs={"typeof": True}):
        for t in tag["typeof"].split():
            tname = t.rstrip("/").split("/")[-1].split(":")[-1]
            if tname:
                types.append(tname)
    return list(set(types))


# ─────────────────────────────────────────────
#  VALIDATION
# ─────────────────────────────────────────────

def _validate_schema(schema):
    """
    Validate a single JSON-LD schema dict.
    Returns {passed, failed, warnings, score, type, canonical_type}.
    """
    raw_type = _get_type(schema)
    ctype    = _canonical_type(raw_type) if raw_type else ""
    rules    = VALIDATION_RULES.get(ctype)

    passed   = []
    failed   = []
    warnings = []

    # Parse error
    if "_parse_error" in schema:
        failed.append(f"JSON-LD parse error: {schema['_parse_error']}")
        return {
            "type": "(parse error)", "canonical_type": "",
            "passed": passed, "failed": failed, "warnings": warnings,
            "score": 0
        }

    # @type
    if raw_type:
        passed.append(f"@type declared: {raw_type}")
    else:
        failed.append("Missing @type — schema.org type not declared")
        return {
            "type": "", "canonical_type": "",
            "passed": passed, "failed": failed, "warnings": warnings,
            "score": 0
        }

    # @context
    ctx = schema.get("@context", "")
    if ctx and "schema.org" in str(ctx):
        passed.append("@context references schema.org")
    else:
        warnings.append("@context missing or does not reference schema.org")

    # No rules defined — basic check only
    if not rules:
        warnings.append(f"No validation rules defined for type '{ctype}'")
        return {
            "type": raw_type, "canonical_type": ctype,
            "passed": passed, "failed": failed, "warnings": warnings,
            "score": 60
        }

    # Required fields
    for field in rules.get("required", []):
        if _has_value(schema.get(field)):
            passed.append(f"Required field present: {field}")
        else:
            failed.append(f"Missing required field: {field}")

    # Recommended fields
    for field in rules.get("recommended", []):
        if _has_value(schema.get(field)):
            passed.append(f"Recommended field present: {field}")
        else:
            warnings.append(f"Recommended field missing: {field}")

    # Child rules (e.g. FAQPage → Question → Answer)
    for field, crule in rules.get("child_rules", {}).items():
        children = schema.get(field, [])
        if not isinstance(children, list):
            children = [children]
        if not children:
            failed.append(f"'{field}' is empty or missing")
            continue
        passed.append(f"'{field}' contains {len(children)} item(s)")
        for i, child in enumerate(children[:10]):
            if not isinstance(child, dict):
                warnings.append(f"{field}[{i}] is not an object")
                continue
            child_type   = crule.get("type", "")
            actual_type  = _get_type(child)
            if child_type and actual_type.lower() != child_type.lower():
                warnings.append(
                    f"{field}[{i}] @type '{actual_type}' — expected '{child_type}'"
                )
            for req in crule.get("required", []):
                if _has_value(child.get(req)):
                    passed.append(f"{field}[{i}].{req} present")
                else:
                    failed.append(f"{field}[{i}] missing required '{req}'")
            for gc_field, gc_rule in crule.get("child_rules", {}).items():
                gc = child.get(gc_field)
                if not gc:
                    failed.append(f"{field}[{i}].{gc_field} missing")
                    continue
                if isinstance(gc, dict):
                    for req in gc_rule.get("required", []):
                        if _has_value(gc.get(req)):
                            passed.append(f"{field}[{i}].{gc_field}.{req} present")
                        else:
                            failed.append(
                                f"{field}[{i}].{gc_field} missing required '{req}'"
                            )

    # Score: 70 pts required, 30 pts recommended
    req_total  = len(rules.get("required", []))
    rec_total  = len(rules.get("recommended", []))
    req_passed = sum(1 for m in passed if "Required field" in m)
    rec_passed = sum(1 for m in passed if "Recommended field" in m)

    if req_total + rec_total == 0:
        score = 100
    else:
        req_score = (req_passed / max(req_total, 1)) * 70 if req_total else 70
        rec_score = (rec_passed / max(rec_total, 1)) * 30 if rec_total else 30
        score = max(0, min(100, int(req_score + rec_score)))

    return {
        "type": raw_type,
        "canonical_type": ctype,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "score": score,
    }


# ─────────────────────────────────────────────
#  FAQ / ARTICLE / PRODUCT DEEP INSPECTION
# ─────────────────────────────────────────────

def _inspect_faq(schemas):
    faq_schemas = [s for s in schemas
                   if _canonical_type(_get_type(s)) == "FAQPage"]
    if not faq_schemas:
        return None
    result = {"blocks": []}
    for s in faq_schemas:
        questions = s.get("mainEntity", [])
        if not isinstance(questions, list):
            questions = [questions]
        block = {
            "question_count": len(questions),
            "questions": []
        }
        for q in questions[:20]:
            if not isinstance(q, dict):
                continue
            answer_obj = q.get("acceptedAnswer", {})
            answer_text = (
                answer_obj.get("text", "")
                if isinstance(answer_obj, dict) else ""
            )
            block["questions"].append({
                "name":   (q.get("name", "") or "")[:120],
                "answer": (answer_text or "")[:200],
            })
        result["blocks"].append(block)
    return result


def _inspect_article(schemas):
    article_schemas = [s for s in schemas
                       if _canonical_type(_get_type(s)) in ARTICLE_TYPES]
    if not article_schemas:
        return None
    result = {"articles": []}
    for s in article_schemas:
        author = s.get("author", "")
        if isinstance(author, dict):
            author = author.get("name", "")
        elif isinstance(author, list):
            author = ", ".join(
                (a.get("name", str(a)) if isinstance(a, dict) else str(a))
                for a in author
            )
        publisher = s.get("publisher", {})
        if isinstance(publisher, dict):
            publisher = publisher.get("name", "")

        result["articles"].append({
            "type":           _get_type(s),
            "headline":       (s.get("headline", "") or "")[:120],
            "author":         str(author)[:80],
            "datePublished":  s.get("datePublished", ""),
            "dateModified":   s.get("dateModified", ""),
            "publisher":      str(publisher)[:80],
            "has_image":      _has_value(s.get("image")),
            "has_description":_has_value(s.get("description")),
        })
    return result


def _inspect_product(schemas):
    product_schemas = [s for s in schemas
                       if _canonical_type(_get_type(s)) == "Product"]
    if not product_schemas:
        return None
    result = {"products": []}
    for s in product_schemas:
        offers = s.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = ""
        currency = ""
        if isinstance(offers, dict):
            price    = str(offers.get("price", ""))
            currency = offers.get("priceCurrency", "")

        agg = s.get("aggregateRating", {})
        rating_value = ""
        review_count = ""
        if isinstance(agg, dict):
            rating_value = str(agg.get("ratingValue", ""))
            review_count = str(agg.get("reviewCount", agg.get("ratingCount", "")))

        brand = s.get("brand", "")
        if isinstance(brand, dict):
            brand = brand.get("name", "")

        result["products"].append({
            "name":         (s.get("name", "") or "")[:100],
            "sku":          s.get("sku", ""),
            "brand":        str(brand)[:60],
            "price":        price,
            "currency":     currency,
            "rating_value": rating_value,
            "review_count": review_count,
            "has_image":    _has_value(s.get("image")),
            "has_description": _has_value(s.get("description")),
        })
    return result


# ─────────────────────────────────────────────
#  RECOMMENDATIONS
# ─────────────────────────────────────────────

def _build_recommendations(all_types, jsonld_schemas, has_microdata,
                            has_rdfa, has_jsonld):
    recs = []

    if not has_jsonld and (has_microdata or has_rdfa):
        recs.append({
            "priority": "high",
            "message":  "Migrate to JSON-LD — Google's preferred format. "
                        "Easier to maintain without touching HTML markup.",
            "docs":     "https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data"
        })

    if not all_types:
        recs.append({
            "priority": "high",
            "message":  "No structured data found. Add JSON-LD schema markup "
                        "to enable rich results in Google Search.",
            "docs":     "https://schema.org/docs/gs.html"
        })
        return recs

    for s in jsonld_schemas:
        ctype  = _canonical_type(_get_type(s))
        result = _validate_schema(s)
        for msg in result["failed"]:
            if "Missing required field" in msg:
                field = msg.replace("Missing required field: ", "")
                recs.append({
                    "priority": "high",
                    "type":     ctype,
                    "message":  f"Add missing required field '{field}' to {ctype} schema.",
                    "docs":     f"https://developers.google.com/search/docs/appearance/structured-data/{ctype.lower()}"
                })
        for msg in result["warnings"]:
            if "Recommended field missing" in msg:
                field = msg.replace("Recommended field missing: ", "")
                recs.append({
                    "priority": "medium",
                    "type":     ctype,
                    "message":  f"Add recommended field '{field}' to {ctype} for better rich results.",
                })

    if "FAQPage" not in all_types:
        recs.append({
            "priority": "low",
            "message":  "Add FAQPage schema if your page contains Q&A content — "
                        "enables FAQ rich results in Google Search.",
            "docs":     "https://developers.google.com/search/docs/appearance/structured-data/faqpage"
        })

    if not any(t in all_types for t in ARTICLE_TYPES):
        recs.append({
            "priority": "low",
            "message":  "Add Article/BlogPosting schema for editorial/blog content.",
            "docs":     "https://developers.google.com/search/docs/appearance/structured-data/article"
        })

    if "BreadcrumbList" not in all_types:
        recs.append({
            "priority": "low",
            "message":  "Add BreadcrumbList schema to enable breadcrumb rich results.",
            "docs":     "https://developers.google.com/search/docs/appearance/structured-data/breadcrumb"
        })

    return recs


# ─────────────────────────────────────────────
#  MAIN PUBLIC FUNCTION
# ─────────────────────────────────────────────

def analyze_structured_data(url):
    """
    Fetch `url`, detect and validate all structured data.
    Returns a JSON-serialisable dict.
    """
    start = time.time()

    # ── Fetch ──
    try:
        html, status_code, final_url = _fetch(url)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code} — {e.reason}", "url": url}
    except urllib.error.URLError as e:
        return {"error": f"Connection error — {e.reason}", "url": url}
    except TimeoutError:
        return {"error": f"Request timed out after {REQUEST_TIMEOUT}s", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}

    soup = BeautifulSoup(html, "html.parser")

    # ── Warn if bot-blocked ──
    fetch_warning = None
    if status_code == 403:
        fetch_warning = "⚠️ Site returned HTTP 403 — bot protection may be blocking the crawl. Results may be incomplete."
    elif status_code == 429:
        fetch_warning = "⚠️ Rate limited (HTTP 429) — try again in a few seconds."
    elif status_code not in (200, 301, 302, 307, 308):
        fetch_warning = f"⚠️ Unexpected HTTP {status_code} — page may not have loaded correctly."
    jsonld_schemas  = _extract_jsonld(soup)
    microdata_types = _detect_microdata(soup)
    rdfa_types      = _detect_rdfa(soup)

    has_jsonld    = bool(jsonld_schemas)
    has_microdata = bool(microdata_types)
    has_rdfa      = bool(rdfa_types)
    has_any       = has_jsonld or has_microdata or has_rdfa

    # ── All types (canonical) ──
    valid_jsonld = [s for s in jsonld_schemas if "_parse_error" not in s]

    all_types = []
    for s in valid_jsonld:
        t = _get_type(s)
        if t:
            all_types.append(_canonical_type(t))
    all_types += [_canonical_type(t) for t in microdata_types]
    all_types += [_canonical_type(t) for t in rdfa_types]
    all_types = sorted(set(all_types))

    # ── Validate each JSON-LD block ──
    schema_results = []
    schema_scores  = []
    total_errors   = 0
    total_warnings = 0

    for s in valid_jsonld:
        v = _validate_schema(s)
        schema_results.append(v)
        schema_scores.append(v["score"])
        total_errors   += len(v["failed"])
        total_warnings += len(v["warnings"])

    # ── Overall score ──
    if schema_scores:
        overall_score = int(sum(schema_scores) / len(schema_scores))
    elif has_microdata or has_rdfa:
        overall_score = 50   # detected but no JSON-LD to score precisely
    else:
        overall_score = 0

    score_label = (
        "Good"        if overall_score >= 70 else
        "Needs Work"  if overall_score >= 40 else
        "Poor"
    )

    # ── Deep inspections ──
    faq_data     = _inspect_faq(jsonld_schemas)
    article_data = _inspect_article(jsonld_schemas)
    product_data = _inspect_product(jsonld_schemas)

    # ── Recommendations ──
    recommendations = _build_recommendations(
        all_types, jsonld_schemas, has_microdata, has_rdfa, has_jsonld
    )

    elapsed_ms = int((time.time() - start) * 1000)

    return {
        # ── Meta ──
        "url":           final_url,
        "status_code":   status_code,
        "elapsed_ms":    elapsed_ms,

        # ── Detection ──
        "has_any":       has_any,
        "has_jsonld":    has_jsonld,
        "has_microdata": has_microdata,
        "has_rdfa":      has_rdfa,

        # ── Types ──
        "schema_types":      all_types,
        "total_schemas":     len(valid_jsonld),
        "microdata_types":   microdata_types,
        "rdfa_types":        rdfa_types,

        # ── Flags ──
        "has_faq":     "FAQPage" in all_types,
        "has_article": any(t in all_types for t in ARTICLE_TYPES),
        "has_product": "Product" in all_types,

        # ── Validation ──
        "schema_results":  schema_results,
        "total_errors":    total_errors,
        "total_warnings":  total_warnings,

        # ── Score ──
        "overall_score": overall_score,
        "score_label":   score_label,

        # ── Deep inspections ──
        "faq":     faq_data,
        "article": article_data,
        "product": product_data,

        # ── Recommendations ──
        "recommendations": recommendations,

        # ── Fetch warning ──
        "fetch_warning": fetch_warning,
    }