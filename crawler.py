import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import xml.etree.ElementTree as ET
from onpage import analyze_onpage
from linkanalysis import analyze_links

# Try to import Playwright — fall back to requests if not installed
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class WebCrawler:
    def __init__(self, base_url, scan_type="single", depth=2, device="desktop", socketio=None, sid=None):
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc
        self.scan_type = scan_type
        self.depth = depth if scan_type == "full" else 1
        self.device = device
        self.socketio = socketio
        self.sid = sid
        self.visited = set()
        self.all_pages = []
        self.running = True
        self.start_time = None
        self.seen_titles = set()
        self.seen_fingerprints = set()
        self._playwright = None
        self._browser = None
        self._context = None

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
                if device == "mobile"
                else
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        self.viewport = {"width": 390, "height": 844} if device == "mobile" else {"width": 1280, "height": 900}

    def _start_browser(self):
        if not PLAYWRIGHT_AVAILABLE:
            self.emit("log", {"msg": "⚠️ Playwright not installed — using requests (JS not rendered)", "type": "warn"})
            return
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context(
                user_agent=self.headers["User-Agent"],
                viewport=self.viewport,
                ignore_https_errors=True,
            )
            self.emit("log", {"msg": "🌐 Playwright browser started — JS rendering ON", "type": "info"})
        except Exception as e:
            self._browser = None
            self.emit("log", {"msg": f"⚠️ Playwright failed: {e} — falling back to requests", "type": "warn"})

    def _stop_browser(self):
        try:
            if self._context: self._context.close()
            if self._browser: self._browser.close()
            if self._playwright: self._playwright.stop()
        except Exception:
            pass

    def emit(self, event, data):
        if self.socketio and self.sid:
            self.socketio.emit(event, data, room=self.sid)

    def stop(self):
        self.running = False

    def fetch(self, url):
        if PLAYWRIGHT_AVAILABLE and self._browser:
            return self._fetch_playwright(url)
        return self._fetch_requests(url)

    def _fetch_playwright(self, url):
        page = None
        try:
            page = self._context.new_page()
            # Block images/fonts to speed up — HTML+CSS+JS still loads
            page.route("**/*", lambda route: route.abort()
                if route.request.resource_type in ("image", "media", "font")
                else route.continue_()
            )
            resp = page.goto(url, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)   # let JS render
            final_url = page.url
            status = resp.status if resp else 200
            html = page.content()
            redirect = final_url.rstrip("/") != url.rstrip("/")
            page.close()
            return {
                "url": url,
                "status": status,
                "redirect": redirect,
                "redirect_to": final_url if redirect else None,
                "content": html,
                "content_type": "text/html",
            }
        except Exception as e:
            if page:
                try: page.close()
                except: pass
            return self._fetch_requests(url)

    def _fetch_requests(self, url, max_retries=3):
        import time
        last_error = None
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=self.headers, timeout=10, allow_redirects=True)
                final_url = resp.url
                redirect = final_url.rstrip("/") != url.rstrip("/")
                return {
                    "url": url,
                    "status": resp.status_code,
                    "redirect": redirect,
                    "redirect_to": final_url if redirect else None,
                    "content": resp.text if resp.status_code == 200 else "",
                    "content_type": resp.headers.get("Content-Type", ""),
                }
            except requests.exceptions.RequestException as e:
                last_error = e
                # Transient DNS/connection glitches (common on free hosting tiers)
                # get a short backoff before retrying instead of failing immediately.
                if attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
        return {"url": url, "status": "error", "error": str(last_error), "content": ""}

    def parse_links(self, html, current_url):
        soup = BeautifulSoup(html, "lxml")
        links = set()
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                continue
            full_url = urljoin(current_url, href).split("#")[0].rstrip("/")
            parsed = urlparse(full_url)
            if parsed.netloc == self.domain and parsed.scheme in ("http", "https"):
                links.add(full_url)
        return links

    def fetch_sitemap(self):
        candidates = [
            self.base_url + "/sitemap.xml",
            self.base_url + "/sitemap_index.xml",
            self.base_url + "/wp-sitemap.xml",
            self.base_url + "/post-sitemap.xml",
            self.base_url + "/page-sitemap.xml",
        ]
        all_urls = []
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        for sitemap_url in candidates:
            try:
                resp = requests.get(sitemap_url, headers=self.headers, timeout=8)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.text)
                child_sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
                if child_sitemaps:
                    for loc in child_sitemaps:
                        try:
                            cr = requests.get(loc.text.strip(), headers=self.headers, timeout=8)
                            if cr.status_code == 200:
                                cr_root = ET.fromstring(cr.text)
                                for u in cr_root.findall(".//sm:loc", ns):
                                    url = u.text.strip().rstrip("/")
                                    if url not in all_urls:
                                        all_urls.append(url)
                        except Exception:
                            continue
                else:
                    for u in root.findall(".//sm:loc", ns):
                        url = u.text.strip().rstrip("/")
                        if url not in all_urls:
                            all_urls.append(url)
            except Exception:
                continue

        if all_urls:
            self.emit("log", {"msg": f"📄 Sitemap: {len(all_urls)} URLs found", "type": "info"})
        else:
            self.emit("log", {"msg": "⚠️ No sitemap found — crawling from homepage only", "type": "warn"})
        return all_urls

    def run_onpage(self, url, content, content_type="text/html"):
        if content and "text/html" in content_type:
            self.emit("log", {"msg": f"🔎 Analysing: {url}", "type": "info"})
            try:
                seo = analyze_onpage(url, content, self.headers, self.seen_titles, self.seen_fingerprints)
                score = seo.get("seo_score", 0)
                self.emit("log", {
                    "msg": f"✅ SEO Score {score}/100 — {url}",
                    "type": "success" if score >= 70 else "warn"
                })
                self.emit("seo_result", seo)
                return seo
            except Exception as e:
                self.emit("log", {"msg": f"⚠️ SEO analysis error: {e}", "type": "warn"})
        return None

    def crawl(self):
        self.start_time = time.time()
        self._start_browser()
        self._all_linked_urls = set()  # orphan detection ke liye
        self.emit("status", {"state": "started"})
        self.emit("log", {"msg": f"🚀 Starting crawl: {self.base_url}", "type": "info"})

        sitemap_urls = self.fetch_sitemap()
        queue = [(self.base_url, 0)]
        queued_set = {self.base_url}
        for u in sitemap_urls:
            if u not in queued_set:
                queue.append((u, 0))  # Fix: depth 0 se shuru
                queued_set.add(u)

        total_estimated = len(queue)

        while queue and self.running:
            url, current_depth = queue.pop(0)
            if url in self.visited:
                continue
            self.visited.add(url)

            self.emit("log", {"msg": f"🔍 Crawling: {url}", "type": "crawl"})
            result = self.fetch(url)

            page_data = {
                "url": url,
                "status": result["status"],
                "redirect": result.get("redirect", False),
                "redirect_to": result.get("redirect_to"),
                "error": result.get("error"),
                "depth": current_depth,
                # content yahan save NAHI karte — memory bachane ke liye
                # sirf analysis ke liye temporarily use karenge
            }

            if result["status"] == 404:
                page_data["category"] = "broken"
                self.emit("log", {"msg": f"❌ 404 Broken: {url}", "type": "error"})

            elif result["status"] == "error":
                page_data["category"] = "error"
                self.emit("log", {"msg": f"⚠️ Error: {url} — {result.get('error')}", "type": "error"})

            elif str(result["status"]).startswith("5"):
                page_data["category"] = "server_error"
                self.emit("log", {"msg": f"🔥 Server Error {result['status']}: {url}", "type": "error"})

            else:
                redirect_to = result.get("redirect_to", "")
                redirect_domain = urlparse(redirect_to).netloc if redirect_to else ""
                is_external = redirect_domain and redirect_domain != self.domain

                if is_external:
                    page_data["category"] = "redirect"
                    self.emit("log", {"msg": f"↪️ External Redirect: {url} → {redirect_to}", "type": "warn"})
                else:
                    page_data["category"] = "ok"
                    if result.get("redirect"):
                        self.emit("log", {"msg": f"↪️ Internal redirect followed: {url} → {redirect_to}", "type": "info"})
                    # Run on-page on the fully JS-rendered content
                    seo = self.run_onpage(url, result["content"], result.get("content_type", "text/html"))
                    if seo:
                        page_data["seo"] = seo

                    # Run link analysis per page
                    if result["content"] and "text/html" in result.get("content_type", "text/html"):
                        try:
                            depth_map = {p["url"]: p["depth"] for p in self.all_pages}
                            links = analyze_links(url, result["content"], self.domain, self.headers,
                                                  all_page_depths=depth_map, check_broken=False)
                            page_data["links"] = links
                            self.emit("link_result", {
                                "url": url,
                                "internal": links["internal_count"],
                                "external": links["external_count"],
                                "broken":   links["broken_count"],
                            })
                        except Exception as e:
                            self.emit("log", {"msg": f"⚠️ Link analysis error: {e}", "type": "warn"})

            self.all_pages.append(page_data)

            # Discover child links from rendered HTML
            if (
                result["content"]
                and "text/html" in result.get("content_type", "text/html")
            ):
                child_links = self.parse_links(result["content"], url)
                # Orphan detection ke liye track karo
                self._all_linked_urls.update(child_links)

                # Full crawl mein queue mein add karo
                if self.scan_type == "full" and current_depth < self.depth:
                    for link in child_links:
                        if link not in queued_set:
                            queue.append((link, current_depth + 1))
                            queued_set.add(link)

            total_estimated = max(total_estimated, len(queued_set))
            progress = int((len(self.visited) / total_estimated) * 100) if total_estimated else 0
            elapsed = round(time.time() - self.start_time, 1)
            self.emit("progress", {
                "visited": len(self.visited),
                "total": total_estimated,
                "percent": min(progress, 99),
                "elapsed": elapsed,
            })

        # Orphan detection — pages jinhe koi link nahi karta
        # linked_urls crawl ke dauran track kiya tha
        for p in self.all_pages:
            if p["url"] != self.base_url and p["url"] not in self._all_linked_urls:
                p["orphan"] = True

        self._stop_browser()

        elapsed = round(time.time() - self.start_time, 1)
        summary = {
            "total": len(self.all_pages),
            "ok": sum(1 for p in self.all_pages if p.get("category") == "ok"),
            "broken": sum(1 for p in self.all_pages if p.get("category") == "broken"),
            "redirects": sum(1 for p in self.all_pages if p.get("category") == "redirect"),
            "errors": sum(1 for p in self.all_pages if p.get("category") in ("error", "server_error")),
            "orphans": sum(1 for p in self.all_pages if p.get("orphan")),
            "elapsed": elapsed,
            "pages": self.all_pages,
        }

        self.emit("progress", {"visited": len(self.visited), "total": len(self.visited), "percent": 100, "elapsed": elapsed})
        self.emit("done", summary)
        self.emit("log", {"msg": f"✅ Scan complete in {elapsed}s — {len(self.all_pages)} pages found", "type": "success"})
        return summary
