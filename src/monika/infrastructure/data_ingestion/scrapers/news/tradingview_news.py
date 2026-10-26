# ==============================================================================
# File: scrapers/news/tradingview_news.py
# ==============================================================================

import logging
import time
from typing import Any, List, Optional

from monika.infrastructure.data_ingestion.scrapers.base_scraper import BaseScraper
from monika.infrastructure.data_ingestion.scrapers.models import ScrapedNews

logger = logging.getLogger("TradingAgent.TradingViewNewsScraper")


class TradingViewNewsScraper(BaseScraper):
    def __init__(
        self,
        headless=True,
        profile_name="tradingview",
        watchlist_id: Optional[str] = None,
        settings: Optional[dict] = None,
    ):
        super().__init__(headless, profile_name=profile_name, load_mode="eager", no_imgs=True)
        wl_id = watchlist_id
        if not wl_id and settings:
            wl_id = settings.get("scraping", {}).get("tradingview_watchlist_id") or settings.get("scrapers", {}).get(
                "tradingview_watchlist_id"
            )
        if not wl_id:
            import os

            wl_id = os.getenv("TRADINGVIEW_WATCHLIST_ID", "336110995")

        self.watchlist_id = str(wl_id).strip() if wl_id else ""
        if self.watchlist_id:
            self.target_url = f"https://www.tradingview.com/news-flow/?watchlist={self.watchlist_id}"
        else:
            self.target_url = "https://www.tradingview.com/news-flow/"
        self._cookies_injected = False

    def _prepare_session(self) -> None:
        """Injeksi cookie TradingView sebelum navigasi ke halaman watchlist."""
        if self._cookies_injected:
            return
        if not self.page:
            return
        try:
            page_obj: Any = self.page
            import json
            import os
            from pathlib import Path

            from monika.core.paths import DATA_DIR

            candidate_paths = [
                str(DATA_DIR / "sessions" / "tv_session.json"),
                str(Path("data") / "sessions" / "tv_session.json"),
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "data",
                    "sessions",
                    "tv_session.json",
                ),
            ]
            session_file = next((p for p in candidate_paths if os.path.exists(p)), None)
            if session_file is not None:
                try:
                    with open(session_file, "r", encoding="utf-8") as f:
                        cookies = json.load(f)
                    page_obj.get("https://www.tradingview.com/robots.txt")
                    page_obj.set.cookies(cookies)
                    try:
                        page_obj.set.cookies(
                            [
                                {"name": "locale", "value": "en", "domain": ".tradingview.com", "path": "/"},
                                {"name": "lang", "value": "en", "domain": ".tradingview.com", "path": "/"},
                            ]
                        )
                    except Exception:
                        pass
                    self._cookies_injected = True
                    logger.info("TradingView cookies injected successfully (en enforced).")
                except Exception as e:
                    logger.warning(f"Failed to inject TradingView cookies: {e}")
        except Exception as e:
            logger.debug(f"Cookie prep exception: {e}")

    def _save_to_jsonl(self, news_items: list[dict[str, Any]]) -> None:
        """Menyimpan item berita ke file jsonl secara inkremental."""
        if not news_items:
            return
        try:
            import json
            from pathlib import Path

            out_dir = Path("data") / "news"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "tradingview.jsonl"
            with open(out_file, "a", encoding="utf-8") as f:
                for item in news_items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Failed to append TradingView news to jsonl: {e}")

    def _fetch_via_http_api(self) -> list[dict[str, Any]]:
        """Fallback fetching berita TradingView melalui HTTP REST API publik."""
        import json
        import urllib.request
        from datetime import datetime, timezone

        endpoints = [
            "https://news-mediator.tradingview.com/news-flow/v2/news?filter=lang:en&client=screener&streaming=false",
            "https://news-headlines.tradingview.com/v2/headlines?client=web&lang=en",
        ]
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        news_items: list[dict[str, Any]] = []
        for url in endpoints:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status_code = getattr(resp, "status", getattr(resp, "code", 200))
                    if status_code != 200:
                        continue
                    payload = json.loads(resp.read().decode("utf-8"))
                    raw_items = payload.get("items", []) if isinstance(payload, dict) else []
                    if not raw_items:
                        continue

                    for it in raw_items:
                        if not isinstance(it, dict):
                            continue
                        title = (it.get("title") or it.get("headline") or "").strip()
                        if not title:
                            continue
                        story_path = it.get("storyPath") or it.get("url") or ""
                        full_url = (
                            story_path if story_path.startswith("http") else f"https://www.tradingview.com{story_path}"
                        )
                        pub = it.get("published")
                        if isinstance(pub, (int, float)):
                            ts_str = datetime.fromtimestamp(pub, tz=timezone.utc).isoformat()
                        elif isinstance(pub, str) and pub:
                            ts_str = pub
                        else:
                            ts_str = datetime.now(timezone.utc).isoformat()

                        provider_val = it.get("provider") or it.get("source")
                        if isinstance(provider_val, dict):
                            source = str(provider_val.get("name") or "TradingView")
                        elif provider_val:
                            source = str(provider_val)
                        else:
                            source = "TradingView"

                        summary = it.get("summary") or it.get("description") or title
                        news_items.append(
                            {
                                "headline": title,
                                "url": full_url,
                                "source": source,
                                "timestamp": ts_str,
                                "summary": summary,
                                "scraped_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    if news_items:
                        break
            except Exception as ep_err:
                logger.debug(f"TradingView news API endpoint {url} failed: {ep_err}")
                continue

        if news_items:
            self._save_to_jsonl(news_items)
            logger.info(f"Fetched {len(news_items)} news items from TradingView public HTTP API.")

        return news_items

    def fetch_news(self, limit: int = 30, fetch_full_content: bool = False) -> List[ScrapedNews]:
        if getattr(self, "is_closed", False):
            return []

        news_list = []
        try:
            # 1. Siapkan sesi cookie bila target berupa watchlist privat
            if self.watchlist_id and "watchlist=" in self.target_url:
                self._prepare_session()
                if not self._cookies_injected:
                    logger.info("No TradingView session cookies found; using public news-flow.")
                    self.target_url = "https://www.tradingview.com/news-flow/"

            logger.info(f"Navigating to TradingView News: {self.target_url}")
            wait_sel = 'css:[data-qa-id="news-headline-card"], [data-name="news-headline-card"], a[href*="/news/"], article, [data-qa-id="empty-state-cards"]'
            success = self.navigate_with_fallback(self.target_url, wait_sel, timeout=15)
            if not success or not self.page:
                logger.warning(
                    "Failed to load TradingView news page or locate headline cards (anti-bot challenge or slow CDN)."
                )
            else:
                page_obj: Any = self.page
                # Deteksi jika watchlist kosong / unauthenticated (empty-state-cards)
                if "watchlist=" in self.target_url:
                    try:
                        empty_state = page_obj.ele('css:[data-qa-id="empty-state-cards"]', timeout=0.5)
                        if empty_state:
                            logger.info(
                                "Watchlist empty state rendered; falling back to public TradingView news flow..."
                            )
                            public_sel = wait_sel
                            self.navigate_with_fallback(
                                "https://www.tradingview.com/news-flow/", public_sel, timeout=12, disable_fallback=True
                            )
                    except Exception:
                        pass

                # Kumpulkan link dan metadata terlebih dahulu
                count = 0
                articles = page_obj.eles(
                    'css:[data-qa-id="news-headline-card"], [data-name="news-headline-card"], a[href*="/news/"], article',
                    timeout=1.5,
                )
                article_data_list = []

                for article in articles:
                    if getattr(self, "is_closed", False) or count >= limit:
                        break

                    try:
                        parent_a = article.parent("tag:a", timeout=0.5)
                        href = parent_a.attr("href") if parent_a else article.attr("href")

                        title_ele = article.ele('css:[data-qa-id="news-headline-title"]', timeout=0.5)
                        title = title_ele.text if title_ele else article.text

                        time_ele = article.ele("tag:relative-time", timeout=0.5)
                        from datetime import datetime, timezone

                        timestamp = time_ele.attr("event-time") if time_ele else datetime.now(timezone.utc).isoformat()

                        if not href or len(title) <= 15:
                            continue

                        full_url = href if href.startswith("http") else f"https://www.tradingview.com{href}"

                        # Extract snippet/description directly from overview card without subpage navigation (H-20)
                        body_ele = article.ele(
                            'css:[data-qa-id="news-headline-description"], [data-qa-id="news-headline-body"], p, span',
                            timeout=0.5,
                        )
                        snippet = body_ele.text.strip() if body_ele and body_ele.text else ""

                        article_data_list.append(
                            {
                                "title": title,
                                "url": full_url,
                                "timestamp": timestamp,
                                "snippet": snippet or title,
                            }
                        )
                        count += 1
                    except Exception as e:
                        logger.debug(f"Error parsing article headline: {e}")

                # Optionally visit each link if fetch_full_content is requested (default False to avoid 30 subpage navigations)
                if fetch_full_content:
                    for data in article_data_list:
                        if getattr(self, "is_closed", False):
                            break
                        try:
                            page_obj.get(data["url"], timeout=10)
                            time.sleep(0.5)
                            p_tags = page_obj.eles("tag:p", timeout=2)
                            paragraphs = [p.text.strip() for p in p_tags if p.text and len(p.text.strip()) > 20]
                            full_text = "\n\n".join(paragraphs) if paragraphs else data["snippet"]
                            news_list.append(
                                ScrapedNews(
                                    title=data["title"],
                                    url=data["url"],
                                    source="TradingView",
                                    timestamp=data["timestamp"],
                                    summary=full_text,
                                )
                            )
                        except Exception as e:
                            logger.debug(f"Error fetching full article {data['url']}: {e}")
                else:
                    for data in article_data_list:
                        news_list.append(
                            ScrapedNews(
                                title=data["title"],
                                url=data["url"],
                                source="TradingView",
                                timestamp=data["timestamp"],
                                summary=data["snippet"],
                            )
                        )

        except Exception as e:
            logger.warning(f"Error fetching TradingView news: {e}")

        # Fallback to public HTTP API if DOM extraction returned 0 items
        if not news_list and not getattr(self, "is_closed", False):
            logger.info("TradingView DOM extraction returned 0 items; attempting public HTTP API fallback...")
            try:
                api_items = self._fetch_via_http_api()
                for it in api_items[:limit]:
                    news_list.append(
                        ScrapedNews(
                            title=it.get("headline") or it.get("title", ""),
                            url=it.get("url", ""),
                            source=it.get("source", "TradingView"),
                            timestamp=it.get("timestamp", ""),
                            summary=it.get("summary") or it.get("headline", ""),
                        )
                    )
            except Exception as api_err:
                logger.warning(f"TradingView public HTTP API fallback also failed: {api_err}")

        logger.info(f"Fetched {len(news_list)} news from TradingView.")
        return news_list
