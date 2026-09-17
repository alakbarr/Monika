# ==============================================================================
# File: scrapers/news/tradingview_news.py
# ==============================================================================

import logging
import time
from typing import List, Optional, Any

from scrapers.base_scraper import BaseScraper
from scrapers.models import ScrapedNews

logger = logging.getLogger("TradingAgent.TradingViewNewsScraper")

class TradingViewNewsScraper(BaseScraper):
    def __init__(self, headless=True, profile_name="tradingview", watchlist_id: Optional[str] = None, settings: Optional[dict] = None):
        super().__init__(headless, profile_name=profile_name)
        wl_id = watchlist_id
        if not wl_id and settings:
            wl_id = settings.get("scraping", {}).get("tradingview_watchlist_id") or settings.get("scrapers", {}).get("tradingview_watchlist_id")
        if not wl_id:
            import os
            wl_id = os.getenv("TRADINGVIEW_WATCHLIST_ID", "336110995")

        self.watchlist_id = str(wl_id).strip() if wl_id else ""
        if self.watchlist_id:
            self.target_url = f"https://www.tradingview.com/news-flow/?watchlist={self.watchlist_id}"
        else:
            self.target_url = "https://www.tradingview.com/news-flow/"
        self._cookies_injected = False

    def _prepare_session(self):
        """Injeksi cookie TradingView sebelum navigasi ke halaman watchlist."""
        if self._cookies_injected or not self.page:
            return
        try:
            page_obj: Any = self.page
            import json, os
            session_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "sessions", "tv_session.json")
            if os.path.exists(session_path):
                try:
                    with open(session_path, "r", encoding="utf-8") as f:
                        cookies = json.load(f)
                    page_obj.get("https://www.tradingview.com/robots.txt")
                    page_obj.set.cookies(cookies)
                    try:
                        page_obj.set.cookies([
                            {"name": "locale", "value": "en", "domain": ".tradingview.com", "path": "/"},
                            {"name": "lang", "value": "en", "domain": ".tradingview.com", "path": "/"}
                        ])
                    except Exception:
                        pass
                    self._cookies_injected = True
                    logger.info("TradingView cookies injected successfully (en enforced).")
                except Exception as e:
                    logger.warning(f"Failed to inject TradingView cookies: {e}")
        except Exception as e:
            logger.debug(f"Cookie prep exception: {e}")

    def fetch_news(self, limit: int = 30, fetch_full_content: bool = False) -> List[ScrapedNews]:
        news_list = []
        try:
            logger.info(f"Navigating to TradingView News: {self.target_url}")
            wait_sel = 'css:article[data-qa-id="news-headline-card"], article[data-name="news-headline-card"], article'
            success = self.navigate_with_fallback(self.target_url, wait_sel, timeout=30)
            if not success or not self.page:
                logger.warning("Failed to load TradingView news page or locate headline cards (anti-bot challenge or slow CDN).")
                return news_list
                
            page_obj: Any = self.page
            # Kumpulkan link dan metadata terlebih dahulu
            count = 0
            articles = page_obj.eles('css:article[data-qa-id="news-headline-card"]')
            article_data_list = []
            
            for article in articles:
                if getattr(self, 'is_closed', False) or count >= limit:
                    break
                    
                try:
                    parent_a = article.parent("tag:a", timeout=0.5)
                    href = parent_a.attr("href") if parent_a else None
                    
                    title_ele = article.ele('css:[data-qa-id="news-headline-title"]', timeout=0.5)
                    title = title_ele.text if title_ele else article.text
                    
                    time_ele = article.ele("tag:relative-time", timeout=0.5)
                    from datetime import datetime, timezone
                    timestamp = time_ele.attr("event-time") if time_ele else datetime.now(timezone.utc).isoformat()
                    
                    if not href or len(title) <= 15:
                        continue
                        
                    full_url = href if href.startswith("http") else f"https://www.tradingview.com{href}"

                    # Extract snippet/description directly from overview card without subpage navigation (H-20)
                    body_ele = article.ele('css:[data-qa-id="news-headline-description"], [data-qa-id="news-headline-body"], p, span', timeout=0.5)
                    snippet = body_ele.text.strip() if body_ele and body_ele.text else ""
                    
                    article_data_list.append({
                        "title": title,
                        "url": full_url,
                        "timestamp": timestamp,
                        "snippet": snippet or title,
                    })
                    count += 1
                except Exception as e:
                    logger.debug(f"Error parsing article headline: {e}")
            
            # Optionally visit each link if fetch_full_content is requested (default False to avoid 30 subpage navigations)
            if fetch_full_content:
                for data in article_data_list:
                    if getattr(self, 'is_closed', False):
                        break
                    try:
                        page_obj.get(data["url"], timeout=10)
                        time.sleep(0.5)
                        p_tags = page_obj.eles('tag:p', timeout=2)
                        paragraphs = [p.text.strip() for p in p_tags if p.text and len(p.text.strip()) > 20]
                        full_text = "\n\n".join(paragraphs) if paragraphs else data["snippet"]
                        news_list.append(ScrapedNews(
                            title=data["title"],
                            url=data["url"],
                            source="TradingView",
                            timestamp=data["timestamp"],
                            summary=full_text,
                        ))
                    except Exception as e:
                        logger.debug(f"Error fetching full article {data['url']}: {e}")
            else:
                for data in article_data_list:
                    news_list.append(ScrapedNews(
                        title=data["title"],
                        url=data["url"],
                        source="TradingView",
                        timestamp=data["timestamp"],
                        summary=data["snippet"],
                    ))
                    
        except Exception as e:
            logger.warning(f"Error fetching TradingView news: {e}")
            
        logger.info(f"Fetched {len(news_list)} news from TradingView.")
        return news_list
