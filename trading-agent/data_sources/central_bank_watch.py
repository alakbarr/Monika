# ==============================================================================
# File: data_sources/central_bank_watch.py
# ==============================================================================

"""
Fetcher Ekspektasi Keputusan Suku Bunga & Kurva Yield Bank Sentral Global (Async).

Mengambil probabilitas perubahan suku bunga masa depan (Hike %, Hold %, Cut %),
suku bunga saat ini, dan jadwal rapat bank sentral berikutnya dari:
  - https://centralbank.watch/ (Fed, ECB, BoE, BoJ, RBA)
  - https://centralbank.watch/tools/yield-curve/ (Sovereign curves 2Y & 10Y)

Sumber data agregat ini tidak memerlukan browser headless (pure HTTP aiohttp).
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.safe_ops import safe_commit

from database.models import BondYieldData, CentralBankRateExpectation, InterestRate
from utils.api.http_retry import fetch_with_retry
from utils import clock

logger = logging.getLogger("TradingAgent.CentralBankWatch")

CBW_BASE_URL = "https://centralbank.watch/"
CBW_YIELD_URL = "https://centralbank.watch/tools/yield-curve/"

# Pemetaan class HTML kartu ke kode bank sentral standar
CARD_CLASS_TO_BANK = {
    "fed": "FED",
    "ecb": "ECB",
    "boe": "BOE",
    "boj": "BOJ",
    "rba": "RBA",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class CentralBankWatchFetcher:
    """
    Fetcher ekspektasi suku bunga & sovereign bond yields untuk 5 bank sentral utama.
    Berjalan cepat tanpa browser headless via HTTP async retry.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def fetch_expectations(self) -> Dict[str, Dict[str, Any]]:
        """
        Mengambil probabilitas suku bunga (Hike, Hold, Cut) & tanggal rapat berikutnya.
        Menyimpan ke CentralBankRateExpectation dan mengupdate InterestRate.next_meeting_date.
        """
        html = await fetch_with_retry(
            CBW_BASE_URL,
            headers=DEFAULT_HEADERS,
            response_type="text",
            timeout=20,
        )
        if not html or not isinstance(html, str):
            logger.warning("CentralBankWatch: Gagal mengambil HTML ekspektasi suku bunga")
            return {}

        soup = BeautifulSoup(html, "html.parser")
        extracted: Dict[str, Dict[str, Any]] = {}
        now_utc = clock.now()

        for cls_key, bank_code in CARD_CLASS_TO_BANK.items():
            try:
                card = soup.find(
                    "div",
                    class_=lambda c: bool(c and "cb-card" in c and cls_key in c),
                )
                if not card:
                    continue

                # 1. Next Meeting Date
                m_date_el = card.find("p", class_="cb-meeting-date")
                m_date_str = m_date_el.get_text(strip=True) if m_date_el else "N/A"

                # 2. Current Rate
                rate_el = card.find("p", class_="current-rate")
                cur_rate = 0.0
                if rate_el:
                    rate_m = re.search(r"([\d\.]+)%", rate_el.get_text())
                    if rate_m:
                        cur_rate = float(rate_m.group(1))

                # 3. Probabilities (Hike, Hold, Cut)
                prob_disp = card.find("div", class_="prob-display")
                probs = {"hike": 0.0, "hold": 0.0, "cut": 0.0}
                if prob_disp:
                    for item in prob_disp.find_all("div", class_="prob-item"):
                        text = item.get_text(strip=True)
                        val_m = re.search(r"([\d\.]+)%", text)
                        val = float(val_m.group(1)) if val_m else 0.0
                        if "Hike" in text:
                            probs["hike"] = val
                        elif "No Change" in text or "Hold" in text:
                            probs["hold"] = val
                        elif "Cut" in text:
                            probs["cut"] = val

                bank_data = {
                    "bank": bank_code,
                    "meeting_date": m_date_str,
                    "current_rate": cur_rate,
                    "prob_hike": probs["hike"],
                    "prob_hold": probs["hold"],
                    "prob_cut": probs["cut"],
                }
                extracted[bank_code] = bank_data

                # Simpan ke tabel CentralBankRateExpectation (dengan deduplikasi untuk mencegah bloat)
                latest_exp = (await self.session.execute(
                    select(CentralBankRateExpectation)
                    .where(CentralBankRateExpectation.bank == bank_code)
                    .order_by(CentralBankRateExpectation.fetched_at.desc(), CentralBankRateExpectation.id.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if (latest_exp and latest_exp.meeting_date == m_date_str and
                        abs((latest_exp.current_rate or 0.0) - cur_rate) < 1e-4 and
                        abs((latest_exp.prob_hike or 0.0) - probs["hike"]) < 1e-4 and
                        abs((latest_exp.prob_hold or 0.0) - probs["hold"]) < 1e-4 and
                        abs((latest_exp.prob_cut or 0.0) - probs["cut"]) < 1e-4):
                    latest_exp.fetched_at = now_utc
                else:
                    record = CentralBankRateExpectation(
                        bank=bank_code,
                        meeting_date=m_date_str,
                        current_rate=cur_rate,
                        prob_hike=probs["hike"],
                        prob_hold=probs["hold"],
                        prob_cut=probs["cut"],
                        source="centralbank.watch",
                        fetched_at=now_utc,
                    )
                    self.session.add(record)

                # Update next_meeting_date pada InterestRate jika ada
                if m_date_str and m_date_str != "N/A":
                    try:
                        parsed_dt = date_parser.parse(m_date_str)
                        if parsed_dt.tzinfo is None:
                            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

                        latest_rate_res = await self.session.execute(
                            select(InterestRate)
                            .where(InterestRate.bank == bank_code)
                            .order_by(InterestRate.effective_date.desc(), InterestRate.id.desc())
                            .limit(1)
                        )
                        rate_row = latest_rate_res.scalar_one_or_none()
                        if rate_row:
                            rate_row.next_meeting_date = parsed_dt
                    except Exception as parse_err:
                        logger.debug(f"Gagal parse tanggal rapat {m_date_str} untuk {bank_code}: {parse_err}")

            except Exception as bank_err:
                logger.warning(f"Error parsing card {cls_key} ({bank_code}): {bank_err}")

        if extracted:
            await safe_commit(self.session, label="CentralBankWatch.expectations")
            logger.info(f"CentralBankWatch: Berhasil simpan ekspektasi untuk {list(extracted.keys())}")

        return extracted

    async def fetch_sovereign_yields(self) -> Dict[str, float]:
        """
        Mengambil yield obligasi sovereign 2Y & 10Y dari tabel Sovereign Yield Curve Monitor.
        Menyimpan record DE_2Y, DE_10Y, UK_2Y, UK_10Y, AU_2Y, AU_10Y, JP_2Y, JP_10Y, US_2Y, US_10Y ke BondYieldData.
        """
        html = await fetch_with_retry(
            CBW_YIELD_URL,
            headers=DEFAULT_HEADERS,
            response_type="text",
            timeout=20,
        )
        if not html or not isinstance(html, str):
            logger.warning("CentralBankWatch: Gagal mengambil HTML kurva yield sovereign")
            return {}

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            logger.warning("CentralBankWatch: Tabel yield tidak ditemukan di halaman yield-curve")
            return {}

        yields_found: Dict[str, float] = {}
        now_utc = clock.now()
        today_date = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        tbody = table.find("tbody") or table
        for row in tbody.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 5:
                continue

            country_text = tds[0].get_text().lower()
            try:
                # Kolom 3 = 2Y yield, Kolom 4 = 10Y yield
                y2_str = tds[3].get_text(strip=True)
                y10_str = tds[4].get_text(strip=True)
                y2 = float(y2_str) if y2_str and y2_str != "-" else None
                y10 = float(y10_str) if y10_str and y10_str != "-" else None

                mapping = {}
                if "united states" in country_text:
                    if y2 is not None: mapping["US_2Y"] = y2
                    if y10 is not None: mapping["US_10Y"] = y10
                elif "eurozone" in country_text or "germany" in country_text:
                    if y2 is not None: mapping["DE_2Y"] = y2
                    if y10 is not None: mapping["DE_10Y"] = y10
                elif "united kingdom" in country_text:
                    if y2 is not None: mapping["UK_2Y"] = y2
                    if y10 is not None: mapping["UK_10Y"] = y10
                elif "australia" in country_text:
                    if y2 is not None: mapping["AU_2Y"] = y2
                    if y10 is not None: mapping["AU_10Y"] = y10
                elif "japan" in country_text:
                    if y2 is not None: mapping["JP_2Y"] = y2
                    if y10 is not None: mapping["JP_10Y"] = y10

                for ct, y_val in mapping.items():
                    yields_found[ct] = y_val
                    # Upsert ke BondYieldData
                    exists_q = await self.session.execute(
                        select(BondYieldData)
                        .where(BondYieldData.country_tenor == ct)
                        .where(BondYieldData.date == today_date)
                        .limit(1)
                    )
                    existing_rec = exists_q.scalar_one_or_none()
                    if existing_rec:
                        existing_rec.yield_percent = y_val
                    else:
                        self.session.add(
                            BondYieldData(
                                country_tenor=ct,
                                date=today_date,
                                yield_percent=y_val,
                            )
                        )
            except Exception as row_err:
                logger.debug(f"CentralBankWatch: Lewati baris yield {country_text}: {row_err}")

        if yields_found:
            await safe_commit(self.session, label="CentralBankWatch.yields")
            logger.info(f"CentralBankWatch: Berhasil simpan kurva yield: {yields_found}")

        return yields_found

    async def fetch_all(self) -> Dict[str, Any]:
        """Menjalankan pengambilan ekspektasi suku bunga dan sovereign yield sekaligus."""
        exp = await self.fetch_expectations()
        yld = await self.fetch_sovereign_yields()
        return {
            "expectations": exp,
            "yields": yld,
        }
