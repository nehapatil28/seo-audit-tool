import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import Counter


# ─────────────────────────────────────────
#  READABILITY  (Flesch Reading Ease)
# ─────────────────────────────────────────
def count_syllables(word):
    word = word.lower().strip(".,!?;:\"'")
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def flesch_reading_ease(text):
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r'\b\w+\b', text)
    if not sentences or not words:
        return 0
    syllable_count = sum(count_syllables(w) for w in words)
    asl = len(words) / len(sentences)          # avg sentence length
    asw = syllable_count / len(words)           # avg syllables per word
    score = 206.835 - 1.015 * asl - 84.6 * asw
    return round(max(0, min(100, score)), 1)


def readability_label(score):
    if score >= 70:
        return "Easy"
    elif score >= 50:
        return "Moderate"
    elif score >= 30:
        return "Difficult"
    else:
        return "Very Difficult"


# ─────────────────────────────────────────
#  KEYWORD EXTRACTION  (top N by TF)
# ─────────────────────────────────────────
STOPWORDS = set("""
a an the and or but in on at to for of with is was are were be been
being have has had do does did will would could should may might shall
not no nor so yet both either neither this that these those it its
i you he she we they me him her us them my your his our their what
which who whom when where how all any each few more most other some
such than then there through under until up very while as by from
into after before between during though since because if unless
""".split())


def extract_keywords(text, top_n=10):
    words = re.findall(r'\b[a-z]{4,}\b', text.lower())
    words = [w for w in words if w not in STOPWORDS]
    freq = Counter(words)
    total = len(words) if words else 1
    return [
        {"word": w, "count": c, "density": round(c / total * 100, 2)}
        for w, c in freq.most_common(top_n)
    ]


# ─────────────────────────────────────────
#  IMAGE ANALYSIS
# ─────────────────────────────────────────
def analyze_images(soup, base_url, headers):
    imgs = soup.find_all("img")
    total = len(imgs)
    missing_alt = []
    broken = []
    large = []

    for img in imgs:
        src = img.get("src", "").strip()
        alt = img.get("alt", "").strip()

        if not src:
            continue

        full_src = urljoin(base_url, src)

        # Missing alt
        if not alt:
            missing_alt.append(full_src)

        # Check if image is broken + get size
        try:
            r = requests.head(full_src, headers=headers, timeout=6, allow_redirects=True)
            if r.status_code >= 400:
                broken.append(full_src)
            else:
                content_length = int(r.headers.get("Content-Length", 0))
                if content_length > 200 * 1024:   # > 200 KB
                    large.append({"url": full_src, "size_kb": round(content_length / 1024, 1)})
        except Exception:
            broken.append(full_src)

    return {
        "total": total,
        "missing_alt": missing_alt,
        "missing_alt_count": len(missing_alt),
        "broken": broken,
        "broken_count": len(broken),
        "large_images": large,
        "large_count": len(large),
    }


# ─────────────────────────────────────────
#  DUPLICATE DETECTION  (simple hash)
# ─────────────────────────────────────────
def content_fingerprint(text):
    words = re.findall(r'\b\w+\b', text.lower())
    sample = " ".join(words[:200])
    return hash(sample)


# ─────────────────────────────────────────
#  MAIN ON-PAGE ANALYSER
# ─────────────────────────────────────────
def analyze_onpage(url, html, headers, seen_titles=None, seen_fingerprints=None):
    """
    Returns a dict with full on-page SEO data for one page.
    seen_titles / seen_fingerprints are sets passed in from the crawler
    to detect duplicates across pages.
    """
    if seen_titles is None:
        seen_titles = set()
    if seen_fingerprints is None:
        seen_fingerprints = set()

    soup = BeautifulSoup(html, "lxml")
    result = {"url": url}

    # ── TITLE ──────────────────────────────
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    title_len = len(title_text)
    result["title"] = {
        "text": title_text,
        "present": bool(title_text),
        "length": title_len,
        "length_ok": 30 <= title_len <= 60,
        "duplicate": title_text in seen_titles if title_text else False,
    }
    if title_text:
        seen_titles.add(title_text)

    # ── META DESCRIPTION ───────────────────
    meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    desc_text = meta_desc.get("content", "").strip() if meta_desc else ""
    desc_len = len(desc_text)
    result["meta_description"] = {
        "text": desc_text,
        "present": bool(desc_text),
        "length": desc_len,
        "length_ok": 120 <= desc_len <= 160,
    }

    # ── HEADINGS ───────────────────────────
    h1_tags = soup.find_all("h1")
    h2_tags = soup.find_all("h2")
    h3_tags = soup.find_all("h3")

    h1_texts = [h.get_text(strip=True) for h in h1_tags]
    result["headings"] = {
        "h1_count": len(h1_tags),
        "h1_present": len(h1_tags) > 0,
        "single_h1": len(h1_tags) == 1,
        "h1_texts": h1_texts,
        "h2_count": len(h2_tags),
        "h3_count": len(h3_tags),
        "structure_ok": len(h1_tags) == 1 and len(h2_tags) >= 1,
    }

    # ── CONTENT ────────────────────────────
    # Remove script/style tags for clean text
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    body_text = soup.get_text(separator=" ")
    body_text = re.sub(r'\s+', ' ', body_text).strip()
    words = re.findall(r'\b\w+\b', body_text)
    word_count = len(words)

    keywords = extract_keywords(body_text, top_n=10)
    flesch = flesch_reading_ease(body_text)

    # Duplicate content check
    fp = content_fingerprint(body_text)
    is_duplicate = fp in seen_fingerprints
    seen_fingerprints.add(fp)

    result["content"] = {
        "word_count": word_count,
        "word_count_ok": word_count >= 300,
        "keywords": keywords,
        "readability_score": flesch,
        "readability_label": readability_label(flesch),
        "duplicate_content": is_duplicate,
    }

    # ── IMAGES ─────────────────────────────
    result["images"] = analyze_images(soup, url, headers)

    # ── IMAGE TO TEXT RATIO ─────────────────
    img_count = result["images"]["total"]
    ratio = round(img_count / word_count * 100, 1) if word_count > 0 else 0
    result["images"]["img_to_text_ratio"] = ratio

    # ── OVERALL SCORE (0–100) ───────────────
    score = 0
    checks = [
        result["title"]["present"],
        result["title"]["length_ok"],
        not result["title"]["duplicate"],
        result["meta_description"]["present"],
        result["meta_description"]["length_ok"],
        result["headings"]["h1_present"],
        result["headings"]["single_h1"],
        result["headings"]["structure_ok"],
        result["content"]["word_count_ok"],
        not result["content"]["duplicate_content"],
        result["content"]["readability_score"] >= 50,
        result["images"]["missing_alt_count"] == 0,
        result["images"]["broken_count"] == 0,
        result["images"]["large_count"] == 0,
    ]
    score = round(sum(checks) / len(checks) * 100)
    result["seo_score"] = score
    result["passed"] = sum(checks)
    result["total_checks"] = len(checks)

    return result