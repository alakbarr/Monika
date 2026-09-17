# ==============================================================================
# File: scrapers/social/twitter_watch.py
# ==============================================================================

import logging
import json
import random
import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.models import ScrapedTweet

logger = logging.getLogger("TradingAgent.TwitterScraper")

class TwitterWatchScraper(BaseScraper):
    def __init__(self, headless=True, list_url=None):
        # Gunakan profil sementara untuk memastikan kondisi bersih sebelum injeksi cookie
        super().__init__(headless=headless, profile_name=None)
        
        self.session_dir = Path(__file__).resolve().parent.parent.parent / "data" / "sessions"
        self.rotation_state_file = self.session_dir / "twitter_pool_state.json"
        self.quarantined_file = self.session_dir / "twitter_quarantined.json"
        self.target_list_url = list_url or "https://x.com/i/lists/2024453847716970688"
        self.max_fetch_limit = 200
        self.seen_urls = set()

    def _load_quarantined(self) -> List[str]:
        if self.quarantined_file.exists():
            try:
                with open(self.quarantined_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _mark_quarantined(self, session_file: str):
        quarantined = self._load_quarantined()
        if session_file not in quarantined:
            quarantined.append(session_file)
            with open(self.quarantined_file, "w", encoding="utf-8") as f:
                json.dump(quarantined, f, indent=4)
        logger.warning(f"Quarantined session: {session_file}")

    def _pick_session(self) -> Optional[str]:
        all_sessions = [str(p) for p in self.session_dir.glob("twitter_session*.json") if "poisoned" not in p.name]
        quarantined = self._load_quarantined()
        active = [s for s in all_sessions if s not in quarantined]
        
        if not active:
            logger.error("No active Twitter sessions available! ALL sessions are quarantined.")
            # Best-effort warning dispatch without creating competing event loops in worker threads
            try:
                import asyncio
                try:
                    running_loop = asyncio.get_running_loop()
                except RuntimeError:
                    running_loop = None

                async def _alert():
                    try:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_warning(
                            "⚠️ <b>Twitter Scraper Alert</b>\n"
                            "All Twitter sessions are quarantined! "
                            "Please refresh cookies in <code>data/sessions/</code>. "
                            "Twitter-sourced news will be missing from analysis."
                        )
                    except Exception:
                        pass

                if running_loop and running_loop.is_running():
                    running_loop.create_task(_alert())
            except Exception:
                pass
            return None
            
        rotation_state = {"available": active.copy(), "used": []}
        
        if self.rotation_state_file.exists():
            try:
                with open(self.rotation_state_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    rotation_state["available"] = [s for s in saved.get("available", []) if s in active]
                    rotation_state["used"] = [s for s in saved.get("used", []) if s in active]
            except Exception:
                pass
                
        if not rotation_state["available"]:
            logger.info("Session pool rotation complete. Resetting pool.")
            rotation_state = {"available": active.copy(), "used": []}
            
        chosen = random.choice(rotation_state["available"])
        rotation_state["available"].remove(chosen)
        rotation_state["used"].append(chosen)
        
        with open(self.rotation_state_file, "w", encoding="utf-8") as f:
            json.dump(rotation_state, f, indent=4)
            
        return chosen

    def _load_cookies(self, session_file: str) -> Optional[Union[List[Dict[str, Any]], Dict[str, Any]]]:
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Normalisasi dan penegakan bahasa Inggris (lang: en) di level memori runtime
            if isinstance(data, dict):
                data["lang"] = "en"
            elif isinstance(data, list):
                has_lang = False
                for item in data:
                    if isinstance(item, dict) and item.get("name") == "lang":
                        item["value"] = "en"
                        has_lang = True
                if not has_lang:
                    data.append({"name": "lang", "value": "en", "domain": ".x.com", "path": "/"})
            return data
        except Exception as e:
            logger.error(f"Error loading cookies from {session_file}: {e}")
            return None

    def _parse_iso(self, iso_string: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        except Exception:
            return None
            
    def _get_url_hash(self, url: str) -> str:
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def fetch_latest_tweets(self, max_age_minutes: int = 1440) -> List[ScrapedTweet]:
        session_file = self._pick_session()
        if not session_file:
            return []
            
        cookies = self._load_cookies(session_file)
        if not cookies:
            self._mark_quarantined(session_file)
            return []
            
        if not self.page:
            return []
        page_obj: Any = self.page

        logger.info(f"Injecting cookies from {Path(session_file).name}...")
        page_obj.get("https://x.com/robots.txt")
        page_obj.set.cookies(cookies)
        
        # Ekstra injeksi domain cookie lang=en secara eksplisit
        try:
            page_obj.set.cookies({"name": "lang", "value": "en", "domain": ".x.com", "path": "/"})
            page_obj.set.cookies({"name": "lang", "value": "en", "domain": "x.com", "path": "/"})
        except Exception:
            pass
        
        target_url = self.target_list_url
        if "lang=" not in target_url:
            separator = "&" if "?" in target_url else "?"
            target_url = f"{target_url}{separator}lang=en"

        logger.info(f"Navigating to {target_url}")
        page_obj.get(target_url)
        page_obj.wait.load_start()
        
        # Periksa status login
        if "login" in page_obj.url or page_obj.eles("text:Sign in to X", timeout=2):
            logger.error("Session expired/unauthorized. Quarantining...")
            self._mark_quarantined(session_file)
            return []
            
        if not page_obj.wait.ele_displayed("tag:article", timeout=15):
            logger.error("No articles rendered. Possible rate limit.")
            return []
            
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        collected_tweets = []
        scrolls = 0
        max_scrolls = 15
        consecutive_old = 0
        
        while scrolls < max_scrolls:
            if getattr(self, 'is_closed', False):
                break
            articles = page_obj.eles("tag:article")
            for article in articles:
                if getattr(self, 'is_closed', False):
                    break
                try:
                    html = article.html
                    import re
                    link_match = re.search(r'href="(/[^/]+/status/\d+)"', html)
                    if not link_match:
                        continue
                        
                    permalink = link_match.group(1)
                    full_url = permalink if permalink.startswith("http") else f"https://x.com{permalink}"
                    
                    try:
                        soup = BeautifulSoup(html, "lxml")
                    except Exception:
                        soup = BeautifulSoup(html, "html.parser")
                    
                    time_tag = soup.select_one("time")
                    if not time_tag or not time_tag.has_attr("datetime"):
                        continue
                        
                    dt_attr = time_tag.get("datetime")
                    if not dt_attr:
                        continue
                    dt_str = dt_attr if isinstance(dt_attr, str) else dt_attr[0] if dt_attr else ""
                    tweet_time = self._parse_iso(dt_str)
                    if not tweet_time or tweet_time < cutoff_time:
                        consecutive_old += 1
                        continue
                        
                    consecutive_old = 0
                    
                    # Handle pengguna
                    user_name_block = soup.select_one('div[data-testid="User-Name"]')
                    username = "unknown"
                    if user_name_block:
                        for text in user_name_block.stripped_strings:
                            if text.startswith("@"):
                                username = text.replace("@", "").lower()
                                break
                                
                    # Konteks Retweet
                    is_retweet = False
                    rt_context = None
                    social_ctx = soup.select_one('div[data-testid="socialContext"]')
                    if social_ctx:
                        ctx_text = social_ctx.get_text(strip=True).lower()
                        if any(kw in ctx_text for kw in ["reposted", "retweeted", "diposting ulang", "meretweet"]):
                            is_retweet = True
                            rt_context = social_ctx.get_text(strip=True)
                        elif any(kw in ctx_text for kw in ["pinned", "disematkan"]):
                            continue # lewati tweet yang disematkan
                            
                    text_div = soup.select_one('div[data-testid="tweetText"]')
                    content = text_div.get_text(separator="\n", strip=True) if text_div else ""
                    if content:
                        content = content.replace('[', '(').replace(']', ')')
                    
                    media_urls: List[str] = []
                    for photo in soup.select('div[data-testid="tweetPhoto"]'):
                        img = photo.select_one("img")
                        if img:
                            src_attr = img.get("src")
                            if src_attr:
                                src_str = src_attr if isinstance(src_attr, str) else src_attr[0] if src_attr else ""
                                if src_str:
                                    media_urls.append(src_str)
                    
                    if not content and not media_urls:
                        continue
                        
                    tweet = ScrapedTweet(
                        id=self._get_url_hash(full_url),
                        username=username,
                        content=content,
                        url=full_url,
                        timestamp=tweet_time.isoformat(),
                        is_retweet=is_retweet,
                        retweet_context=rt_context,
                        media_urls=media_urls
                    )
                    
                    collected_tweets.append(tweet)
                    self.seen_urls.add(full_url)
                    
                    if len(collected_tweets) >= self.max_fetch_limit:
                        break
                        
                except Exception as e:
                    logger.debug(f"Error parsing article: {e}")
                    
            if len(collected_tweets) >= self.max_fetch_limit:
                break
                
            if consecutive_old > 5:
                break
                
            # Scroll halaman dengan variasi seperti manusia
            page_obj.scroll.down(random.randint(400, 700))
            time.sleep(random.uniform(1.0, 2.5))
            scrolls += 1
            
        return collected_tweets
