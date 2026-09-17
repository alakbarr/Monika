# ==============================================================================
# File: scrapers/macro/cme_fedwatch.py
# ==============================================================================

import logging
import os
import time
from bs4 import BeautifulSoup
from typing import List, Optional, Any

from scrapers.base_scraper import BaseScraper
from scrapers.models import FedProbability, FedMeeting

logger = logging.getLogger("TradingAgent.FedWatchScraper")

class FedWatchScraper(BaseScraper):
    def __init__(self, headless=True):
        super().__init__(headless)
        self.cme_url = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"
        self.max_meetings = 4

    def _locate_quikstrike_iframe(self, max_wait_seconds: int = 30):
        """Mencari iframe QuikStrike secara adaptif dengan polling loop dan fallback ke headed jika perlu."""
        if not self.page:
            return None
        page_obj: Any = self.page
        start_time = time.time()
        iframe = None
        
        while time.time() - start_time < max_wait_seconds:
            if getattr(self, 'is_closed', False):
                return None
            try:
                iframe = page_obj.get_frame('xpath://iframe[contains(@src, "quikstrike")]')
                if iframe:
                    tab_0 = iframe.ele('xpath://a[contains(@id, "ctrl0_lbMeeting")] | //a[contains(@id, "ctrl0")]', timeout=1.5)
                    if tab_0:
                        logger.info(f"QuikStrike iframe detected and ready ({round(time.time() - start_time, 1)}s)")
                        return iframe
            except Exception:
                pass
            time.sleep(2)

        # Fallback ke headed HANYA jika eksplisit diizinkan via environment SCRAPER_ALLOW_GUI_FALLBACK
        allow_gui = os.getenv("SCRAPER_ALLOW_GUI_FALLBACK", "false").lower() == "true"
        if self.headless and allow_gui and not getattr(self, 'is_closed', False):
            logger.info("QuikStrike iframe not ready in headless mode. Attempting fallback to headed mode (SCRAPER_ALLOW_GUI_FALLBACK=true)...")
            try:
                self.close()
                self.headless = False
                self.page = self._initialize_browser(self.headless)
                if not self.page:
                    return None
                page_obj = self.page
                page_obj.get(self.cme_url)
                
                fallback_start = time.time()
                while time.time() - fallback_start < 25:
                    if getattr(self, 'is_closed', False):
                        return None
                    try:
                        iframe = page_obj.get_frame('xpath://iframe[contains(@src, "quikstrike")]')
                        if iframe:
                            tab_0 = iframe.ele('xpath://a[contains(@id, "lbMeeting")]', timeout=1.5)
                            if tab_0:
                                logger.info(f"QuikStrike iframe ready in headed fallback mode ({round(time.time() - fallback_start, 1)}s)")
                                return iframe
                    except Exception:
                        pass
                    time.sleep(2)
            except Exception as fallback_err:
                logger.warning(f"Headed fallback for CME FedWatch encountered error: {fallback_err}")

        return iframe

    def _find_probability_table(self, soup: BeautifulSoup) -> Optional[Any]:
        """Dynamically detect CME FedWatch probability table by inspecting headers and content."""
        tables = soup.find_all("table")
        if not tables:
            return None

        # 1. Primary: Scan table headers for TARGET RATE and PROBABILITY
        for t in tables:
            headers = [th.get_text(strip=True).upper() for th in t.find_all(["th", "td"])]
            header_str = " ".join(headers)
            if "TARGET RATE" in header_str and ("PROBABILITY" in header_str or "PROB" in header_str):
                return t

        # 2. Secondary: Scan full table text for TARGET RATE and PROBABILITY
        for t in tables:
            t_text = t.get_text().upper()
            if "TARGET RATE" in t_text and ("PROBABILITY" in t_text or "PROB" in t_text):
                return t

        # 3. Tertiary: Table containing '(Current)' marker
        for t in tables:
            t_text = t.get_text()
            if "(Current)" in t_text or "(CURRENT)" in t_text.upper():
                return t

        # 4. Quaternary: Table with rows containing target range and percentage
        for t in tables:
            rows = t.find_all("tr")
            matching_rows = 0
            for r in rows:
                row_text = r.get_text()
                if "-" in row_text and "%" in row_text:
                    matching_rows += 1
            if matching_rows >= 2:
                return t

        # 5. Fallback to index 4 if available
        if len(tables) > 4:
            return tables[4]

        return tables[0] if tables else None

    def _get_fallback_policy_rate(self) -> float:
        """Fetch dynamic policy rate from DB (InterestRate/SystemConfig), config, or env."""
        import asyncio
        # 1. Try DB
        try:
            from database.db import get_session
            from database.models import InterestRate, SystemConfig
            from sqlalchemy import select, desc
            
            async def _query():
                async with get_session() as session:
                    stmt = select(InterestRate.rate_percent).where(
                        InterestRate.bank.ilike("%FED%")
                    ).order_by(desc(InterestRate.effective_date)).limit(1)
                    res = await session.execute(stmt)
                    val = res.scalar_one_or_none()
                    if val is not None:
                        return float(val)
                    
                    stmt_cfg = select(SystemConfig.value).where(
                        SystemConfig.key.in_(["fed_funds_rate", "fed_policy_rate", "policy_rate_fed"])
                    ).limit(1)
                    res_cfg = await session.execute(stmt_cfg)
                    val_cfg = res_cfg.scalar_one_or_none()
                    if val_cfg is not None:
                        return float(val_cfg)
                    return None
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    val = pool.submit(asyncio.run, _query()).result(timeout=5)
            else:
                val = asyncio.run(_query())

            if val is not None:
                rate = float(val)
                return rate / 100.0 if rate > 1.0 else rate
        except Exception as e:
            logger.debug(f"[FedWatch] Could not fetch policy rate from DB: {e}")

        # 2. Try settings
        try:
            from config.settings import get_settings
            settings = get_settings()
            macro_cfg = settings.get("macro") if isinstance(settings, dict) else getattr(settings, "macro", None)
            if macro_cfg:
                cfg_rate = macro_cfg.get("fed_funds_rate") if isinstance(macro_cfg, dict) else getattr(macro_cfg, "fed_funds_rate", None)
                if isinstance(cfg_rate, (int, float)):
                    rate = float(cfg_rate)
                    return rate / 100.0 if rate > 1.0 else rate
        except Exception:
            pass

        # 3. Try Environment variable
        env_rate = os.getenv("DEFAULT_FED_FUNDS_RATE") or os.getenv("FED_FUNDS_RATE") or os.getenv("POLICY_RATE_FED")
        if env_rate:
            try:
                rate = float(env_rate)
                return rate / 100.0 if rate > 1.0 else rate
            except ValueError:
                pass

        # 4. Default fallback (5.25% in decimal form)
        return 0.0525

    def fetch_probabilities(self) -> List[FedMeeting]:
        meetings = []
        if getattr(self, 'is_closed', False) or not self.page:
            return meetings
        page_obj: Any = self.page
        try:
            logger.info("Navigating to CME FedWatch Tool...")
            page_obj.get(self.cme_url)
            
            iframe = self._locate_quikstrike_iframe(max_wait_seconds=30)
            if not iframe or getattr(self, 'is_closed', False):
                if not iframe:
                    logger.warning("Could not find QuikStrike iframe after adaptive wait — skipping CME FedWatch scrape")
                return meetings
                
            for i in range(self.max_meetings):
                if getattr(self, 'is_closed', False):
                    break
                tab_id = f"ctl00_MainContent_ucViewControl_IntegratedFedWatchTool_uccv_lvMeetings_ctrl{i}_lbMeeting"
                tab_ele = iframe.ele(f'xpath://a[@id="{tab_id}"]', timeout=3)
                
                if not tab_ele:
                    logger.info(f"Meeting tab {i} not found, stopping pagination.")
                    break
                    
                meeting_date = tab_ele.text
                logger.info(f"Scraping meeting: {meeting_date}")
                
                # Klik tab (meskipun itu tab pertama)
                tab_ele.click()
                time.sleep(1.5) # Tunggu postback QuikStrike
                
                html = iframe.html
                try:
                    soup = BeautifulSoup(html, "lxml")
                except Exception:
                    soup = BeautifulSoup(html, "html.parser")
                
                table = self._find_probability_table(soup)
                
                if table:
                    rows = table.find_all("tr")
                    
                    probs_raw = []
                    current_rate = None
                    
                    # Cari tingkat suku bunga saat ini
                    for row in rows:
                        cols = row.find_all(["th", "td"])
                        texts = [c.get_text(strip=True) for c in cols]
                        if len(texts) >= 5 and "(Current)" in texts[0]:
                            current_rate_str = texts[0].replace(" (Current)", "").split("-")[1]
                            current_rate = float(current_rate_str) / 100.0
                            break
                            
                    if current_rate is None:
                        current_rate = self._get_fallback_policy_rate()
                        logger.warning(f"[FedWatch] Target rate marker not found in table, using rate {current_rate * 100:.2f}%")
                        
                    for row in rows:
                        cols = row.find_all(["th", "td"])
                        texts = [c.get_text(strip=True) for c in cols]
                        
                        if len(texts) >= 5 and "-" in texts[0]:
                            target_range = texts[0].replace(" (Current)", "")
                            prob_str = texts[1].replace(",", ".").replace("%", "")
                            
                            try:
                                prob_val = float(prob_str)
                                if prob_val > 0:
                                    probs_raw.append({"target": target_range, "prob": prob_val})
                            except ValueError:
                                pass
                                
                    # Hitung probabilitas tindakan Fed
                    final_probs = []
                    for p in probs_raw:
                        upper_bound = float(p["target"].split("-")[1]) / 100.0
                        diff = upper_bound - current_rate
                        
                        action = "N/A"
                        if abs(diff) < 0.005:
                            action = "HOLD"
                        elif diff < 0:
                            bps = round(int(abs(diff) * 100) / 25) * 25
                            action = f"CUT {bps} bps"
                        else:
                            bps = round(int(diff * 100) / 25) * 25
                            action = f"HIKE {bps} bps"
                            
                        final_probs.append(FedProbability(target_range=p["target"], probability=p["prob"], action=action))
                        
                    if final_probs:
                        top = sorted(final_probs, key=lambda x: x.probability, reverse=True)[0]
                        most_likely = f"{top.action} ({top.probability}%)"
                        meetings.append(FedMeeting(
                            meeting_date=meeting_date,
                            current_rate_ref=round(current_rate, 2),
                            probabilities=final_probs,
                            most_likely=most_likely
                        ))
                else:
                    logger.warning(f"Could not find probability table for {meeting_date}")
                    
        except Exception as e:
            logger.error(f"Error fetching CME FedWatch: {e}")
            
        return meetings
