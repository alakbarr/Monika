# ==============================================================================
# File: data_sources/web_reader.py
# ==============================================================================

"""
Web Reader Data Source.

Fetches and extracts clean, readable text content from full web pages,
stripping navigation, scripts, stylesheets, ads, and boilerplate elements.
Useful for deep research, earnings calls, economic reports, and news verification.
"""

import asyncio
import logging
import re
from typing import Dict, Any, Optional
import ipaddress
import socket
from urllib.parse import urlparse, urljoin
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger("TradingAgent.WebReader")

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB maximum response payload

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DISALLOWED_TAGS = [
    "script", "style", "nav", "header", "footer", "aside", "form",
    "noscript", "svg", "button", "iframe", "menu", "template",
]

CHALLENGE_PHRASES = [
    "just a moment",
    "attention required",
    "security check",
    "cf-turnstile",
    "challenges.cloudflare.com",
    "enable javascript and cookies to continue",
    "checking your browser",
    "verify you are human",
    "pemeriksaan keamanan",
    "tunggu sebentar",
]


def is_challenge_or_empty(status: int, content: str = "", html: str = "") -> bool:
    """Detects if response indicates a bot challenge, WAF block, or unrendered SPA."""
    if status in (403, 429, 503):
        return True
    content_lower = (content or "").lower()
    html_lower = (html or "").lower()
    if any(phrase in content_lower or phrase in html_lower for phrase in CHALLENGE_PHRASES):
        return True
    # Suspiciously empty text on rich JS/SPA document
    if len(content_lower.strip()) < 80 and (
        "<script" in html_lower
        or "id=\"root\"" in html_lower
        or "id=\"app\"" in html_lower
        or "cf-" in html_lower
    ):
        return True
    return False


def is_prohibited_ip(ip_str: str) -> bool:
    """Check if IP address is loopback, private, link-local, multicast, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return True


async def validate_url_ip(url: str) -> Optional[str]:
    """
    Resolves hostname of URL and verifies it does not map to private,
    loopback, or cloud-metadata IPs. Returns None if safe, or error message string if prohibited.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return "Missing hostname in URL"

        loop = asyncio.get_running_loop()
        addr_info = await loop.getaddrinfo(
            hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
        if not addr_info:
            return f"Could not resolve host '{hostname}'"

        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = str(sockaddr[0])
            if is_prohibited_ip(ip_str):
                return f"SSRF blocked: Host '{hostname}' resolves to prohibited IP ({ip_str})"

        return None
    except Exception as e:
        return f"DNS resolution failed: {e}"


class WebReader:
    """Service to fetch full webpage content and extract clean text with headless browser fallback."""

    def __init__(
        self,
        max_chars: int = 12000,
        timeout_seconds: float = 12.0,
        max_body_bytes: int = MAX_BODY_BYTES,
        browser_fallback: bool = True,
        browser_timeout_seconds: float = 20.0,
    ):
        self.max_chars = max_chars
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_body_bytes = max_body_bytes
        self.browser_fallback = browser_fallback
        self.browser_timeout_seconds = browser_timeout_seconds

    def _read_url_with_browser_sync(self, url: str) -> Optional[Dict[str, Any]]:
        """Synchronously opens Chromium via BaseScraper, waits for load, and extracts HTML."""
        try:
            try:
                from scrapers.base_scraper import BaseScraper
            except ImportError:
                from trading_agent.scrapers.base_scraper import BaseScraper  # type: ignore[no-redef]
            scraper = BaseScraper(headless=True, profile_name=None)
        except Exception as e:
            logger.warning(f"WebReader browser fallback unavailable (BaseScraper error): {e}")
            return None

        try:
            logger.info(f"WebReader attempting headless browser fallback for: {url}")
            success = scraper.navigate_with_fallback(url, disable_fallback=True, timeout=15)
            if not success or not scraper.page:
                logger.warning(f"WebReader browser fallback failed to navigate: {url}")
                return None

            page_obj: Any = scraper.page
            if hasattr(page_obj, "wait"):
                page_obj.wait(2)

            html = getattr(page_obj, "html", "") or ""
            if not html:
                return None

            result = self._extract_content(url, html)
            result["engine"] = "browser"
            return result
        except Exception as e:
            logger.warning(f"WebReader browser fallback error for {url}: {e}")
            return None
        finally:
            try:
                scraper.close()
            except Exception:
                pass

    async def _read_url_with_browser(self, url: str) -> Optional[Dict[str, Any]]:
        """Asynchronously executes browser fallback in a worker thread with a timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._read_url_with_browser_sync, url),
                timeout=self.browser_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(f"WebReader browser fallback timed out for {url}")
            return None
        except Exception as e:
            logger.warning(f"WebReader browser fallback execution failed for {url}: {e}")
            return None

    async def read_url(self, url: str) -> Dict[str, Any]:
        """
        Fetches the given URL and parses readable article/document text.
        Returns dictionary with url, title, content, and metadata.
        """
        clean_url = (url or "").strip()
        if not clean_url or not clean_url.startswith(("http://", "https://")):
            return {
                "success": False,
                "url": clean_url,
                "error": f"Invalid URL: '{clean_url}'",
                "content": "",
                "title": "",
                "engine": "http",
            }

        try:
            current_url = clean_url
            max_redirects = 3

            for _ in range(max_redirects + 1):
                ssrf_error = await validate_url_ip(current_url)
                if ssrf_error:
                    logger.warning(f"WebReader SSRF check failed for {current_url}: {ssrf_error}")
                    return {
                        "success": False,
                        "url": clean_url,
                        "error": ssrf_error,
                        "content": "",
                        "title": "",
                        "engine": "http",
                    }

                async with aiohttp.ClientSession(timeout=self.timeout, headers=DEFAULT_HEADERS) as session:
                    async with session.get(current_url, allow_redirects=False) as response:
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location")
                            if not location:
                                break
                            current_url = urljoin(current_url, location)
                            continue

                        if response.status != 200:
                            http_err_res = {
                                "success": False,
                                "url": clean_url,
                                "status": response.status,
                                "error": f"HTTP {response.status}: {response.reason}",
                                "content": "",
                                "title": "",
                                "engine": "http",
                            }
                            if self.browser_fallback and is_challenge_or_empty(response.status, "", ""):
                                browser_res = await self._read_url_with_browser(current_url)
                                if browser_res and browser_res.get("success") and browser_res.get("content"):
                                    return browser_res
                            return http_err_res

                        chunks = []
                        total_bytes = 0
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            total_bytes += len(chunk)
                            if total_bytes > self.max_body_bytes:
                                logger.warning(f"WebReader response body exceeded {self.max_body_bytes} bytes limit for {current_url}")
                                return {
                                    "success": False,
                                    "url": clean_url,
                                    "error": f"Response size exceeded {self.max_body_bytes} bytes limit",
                                    "content": "",
                                    "title": "",
                                    "engine": "http",
                                }
                            chunks.append(chunk)

                        raw_bytes = b"".join(chunks)
                        encoding = response.get_encoding() or "utf-8"
                        try:
                            html = raw_bytes.decode(encoding, errors="replace")
                        except Exception:
                            html = raw_bytes.decode("utf-8", errors="replace")

                        content_res = self._extract_content(clean_url, html)
                        if self.browser_fallback and is_challenge_or_empty(response.status, content_res.get("content", ""), html):
                            logger.info(f"WebReader detected challenge or empty SPA in HTTP response for {clean_url}, trying browser fallback")
                            browser_res = await self._read_url_with_browser(current_url)
                            if browser_res and browser_res.get("success") and browser_res.get("content"):
                                return browser_res
                        return content_res

            return {
                "success": False,
                "url": clean_url,
                "error": "Too many redirects",
                "content": "",
                "title": "",
                "engine": "http",
            }

        except asyncio.TimeoutError:
            logger.warning(f"WebReader timeout for URL: {clean_url}")
            if self.browser_fallback:
                browser_res = await self._read_url_with_browser(clean_url)
                if browser_res and browser_res.get("success") and browser_res.get("content"):
                    return browser_res
            return {
                "success": False,
                "url": clean_url,
                "error": "Request timed out",
                "content": "",
                "title": "",
                "engine": "http",
            }
        except Exception as e:
            logger.warning(f"WebReader error fetching {clean_url}: {e}")
            return {
                "success": False,
                "url": clean_url,
                "error": str(e),
                "content": "",
                "title": "",
                "engine": "http",
            }

    def _extract_content(self, url: str, html: str) -> Dict[str, Any]:
        """Extracts title, meta description, and clean paragraphs from raw HTML."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        else:
            h1 = soup.find("h1")
            if h1 is not None:
                title = h1.get_text().strip()

        # Remove boilerplate tags
        for tag in soup.find_all(DISALLOWED_TAGS):
            tag.decompose()

        # Prefer main article container if available
        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find(id=re.compile(r"content|main|article|body", re.I))
            or soup.find(class_=re.compile(r"content|main|article|post", re.I))
            or soup.body
            or soup
        )

        # Extract text blocks
        lines = []
        for elem in article.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote"]):
            text = elem.get_text().strip()
            if text and len(text) > 20:
                lines.append(text)

        extracted_text = "\n\n".join(lines)
        if not extracted_text:
            extracted_text = article.get_text(separator=" ", strip=True)
            extracted_text = re.sub(r"\s+", " ", extracted_text)

        # Truncate to max_chars
        is_truncated = len(extracted_text) > self.max_chars
        if is_truncated:
            extracted_text = extracted_text[:self.max_chars] + "\n\n... [Content Truncated]"

        return {
            "success": True,
            "url": url,
            "title": title,
            "content": extracted_text,
            "length": len(extracted_text),
            "truncated": is_truncated,
            "engine": "http",
        }
