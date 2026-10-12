# ==============================================================================
# File: scrapers/news/kitco_news.py
# ==============================================================================

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Any

from scrapers.base_scraper import BaseScraper
from scrapers.models import ScrapedNews

logger = logging.getLogger("TradingAgent.KitcoNewsScraper")

class KitcoNewsScraper(BaseScraper):
    def __init__(self, headless=True):
        super().__init__(headless)
        self.target_url = "https://www.kitco.com/news/category/commodities"
        
    def fetch_news(self, limit: int = 30) -> List[ScrapedNews]:
        news_list = []
        try:
            logger.info(f"Navigating to Kitco News: {self.target_url}")
            success = self.navigate_with_fallback(self.target_url, 'css:a[href*="/news/article/"]')
            if not success or not self.page:
                logger.warning("Failed to load Kitco news page or locate articles (anti-bot challenge or slow CDN).")
                return news_list
                
            page_obj: Any = self.page
            count = 0
            articles = page_obj.eles('css:a[href*="/news/article/"]')
            
            seen_urls = set()
            
            for link in articles:
                if getattr(self, 'is_closed', False) or count >= limit:
                    break
                    
                try:
                    href = link.attr("href")
                    title = link.text
                    
                    if not href or len(title) <= 20:
                        continue
                        
                    full_url = href if href.startswith("http") else f"https://www.kitco.com{href}"
                    
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)
                    
                    parts = [p.strip() for p in title.split('\n') if p.strip()]
                    actual_title = parts[0] if parts else title
                    summary = parts[1] if len(parts) > 1 else ""
                    raw_time_str = parts[-1] if len(parts) > 2 else ""
                    
                    import re
                    now_utc = datetime.now(timezone.utc)
                    time_str = now_utc.isoformat()
                    if raw_time_str:
                        match = re.search(r'(\d+)\s*(hour|min|minute|day|sec|second)s?\s*ago', raw_time_str, re.IGNORECASE)
                        if match:
                            val, unit = int(match.group(1)), match.group(2).lower()
                            if 'min' in unit:
                                time_str = (now_utc - timedelta(minutes=val)).isoformat()
                            elif 'hour' in unit:
                                time_str = (now_utc - timedelta(hours=val)).isoformat()
                            elif 'day' in unit:
                                time_str = (now_utc - timedelta(days=val)).isoformat()
                        else:
                            try:
                                from dateutil import parser as dateutil_parser
                                parsed = dateutil_parser.parse(raw_time_str)
                                if parsed.tzinfo is None:
                                    parsed = parsed.replace(tzinfo=timezone.utc)
                                time_str = parsed.isoformat()
                            except Exception:
                                time_str = now_utc.isoformat()

                    news_list.append(ScrapedNews(
                        title=actual_title.strip(),
                        url=full_url,
                        source="Kitco News",
                        timestamp=time_str,
                        summary=summary
                    ))
                    count += 1
                except Exception as e:
                    logger.debug(f"Error parsing article: {e}")
                    
        except Exception as e:
            logger.warning(f"Error fetching Kitco news: {e}")
            
        logger.info(f"Fetched {len(news_list)} news from Kitco.")
        return news_list
