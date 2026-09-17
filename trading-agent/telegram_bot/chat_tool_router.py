"""
Chat Tool Router — Progressive Tool Loading for Telegram Chat Agent.

Reduces 70-90% input token overhead by loading only the relevant tool subset matching
the user's query intent, backed by an automated fail-safe fallback bundle.
"""

import math
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("TradingAgent.ChatToolRouter")


class ChatToolRouter:
    """Routes Telegram queries to a precise tool subset."""

    TRADE_KEYWORDS = re.compile(
        r'\b(buy|sell|beli|jual|close|(?:buka|membuka)\s+(?:posisi|order|trade)|(?:tutup|menutup)\s+(?:semua\s+)?(?:posisi|order|trade)|pasang|order(?!\s*book)|eksekusi|lot|sl|tp|stop\s*loss|take\s*profit)\b',
        re.IGNORECASE
    )


    GREETING_PATTERNS = re.compile(
        r'^(halo|hai|hi|hello|hey|selamat\s+(pagi|siang|sore|malam)|assalamualaikum|tes|test|ping|p|siapa\s+kamu|terima\s*kasih|makasih|thanks|thank\s*you)\b',
        re.IGNORECASE
    )

    PORTFOLIO_PATTERNS = re.compile(
        r'\b(posisi|position|saldo|balance|equity|pnl|profit|rugi|loss|untung|margin|kinerja|performance|paper|history|riwayat|trigger|drawdown)\b',
        re.IGNORECASE
    )

    MACRO_PATTERNS = re.compile(
        r'\b(makro|macro|fundamental|berita|news|fomc|cpi|nfp|fed|fedwatch|kalender|calendar|dxy|dollar|vix|yield|treasury|suku\s*bunga|interest\s*rate|cot|sesi|session|eia|inventory|cadangan\s*minyak|dot\s*plot|sep|rate\s*cut|rate\s*hike|inflasi|inflation|pce|gdp|ppi|pengangguran|unemployment|payroll|hawkish|dovish|press\s*conference|konferensi\s*pers|bank\s*sentral|central\s*bank|kebijakan\s*moneter|monetary\s*policy)\b',
        re.IGNORECASE
    )

    TECHNICAL_PATTERNS = re.compile(
        r'\b(chart|grafik|teknikal|technical|indikator|indicator|rsi|macd|ema|sma|smc|ict|fvg|order\s*block|ob|swing|support|resistance|bos|choch|fibonacci|fibo|adr|range|level|regime|trend|momentum|harga|price|candle|analisis|setup|sinyal|signal)\b',
        re.IGNORECASE
    )

    SYMBOL_PATTERNS = re.compile(
        r'\b(eurusd|gbpusd|usdjpy|audusd|xauusd|gold|emas|btcusd|btc|bitcoin|xtiusd|wti|oil|minyak|xbrusd|brent|ethusd|eth)\b',
        re.IGNORECASE
    )

    SYSTEM_PATTERNS = re.compile(
        r'\b(status|health|server|token|biaya|cost|usage|log|aktivitas|activity|audit|koneksi|uptime)\b',
        re.IGNORECASE
    )

    RESEARCH_PATTERNS = re.compile(
        r'\b(deep-research|deep\s*research|riset\s*mendalam|investigasi|konsensus|whisper|saturasi|ekspektasi|skenario|intel|intelijen|pre-event|breaking|geopolitik|event\s*makro|macro\s*event|probabilitas\s*event|event\s*probability|web[- ]?search|search|cari|browsing)\b|^\s*/research\b',
        re.IGNORECASE
    )

    TIMESFM_PATTERNS = re.compile(
        r'\b(proyeksi|forecast|timesfm|prediksi|kuantil|quantile)\b',
        re.IGNORECASE
    )

    SENTIMENT_PATTERNS = re.compile(
        r'\b(sentimen|sentiment|mood|fear|greed|funding\s*rate|funding|retail|fxssi)\b',
        re.IGNORECASE
    )

    REPORT_PATTERNS = re.compile(
        r'\b(tearsheet|laporan|report|kinerja|performance|equity\s*curve|drawdown|stats|statistik|sharpe|sortino|expectancy)\b',
        re.IGNORECASE
    )

    DATABASE_PATTERNS = re.compile(
        r'\b(database|db|tabel|table|schema|skema|kolom|record|records|baris|row|rows|query|select|insert|update|delete|mutasi|mutation)\b',
        re.IGNORECASE
    )

    COMMAND_PATTERNS = {
        re.compile(r'^/(database|db|schema|tables|tabel)\b', re.IGNORECASE): [
            "inspect_database_schema", "read_database_records", "propose_action"
        ],
        re.compile(r'^/(trade|buy|sell|order|close|beli|jual|buka|tutup)\b', re.IGNORECASE): [
            "propose_action", "get_account_info", "get_open_positions",
            "get_spread_snapshot", "get_risk_state", "get_market_session",
            "get_price_history", "get_technical_indicators", "get_chart"
        ],
        re.compile(r'^/(status|health|ping|system)\b', re.IGNORECASE): [
            "get_system_health", "get_token_usage_and_costs", "get_recent_activity", "get_risk_state"
        ],
        re.compile(r'^/(positions|posisi|balance|saldo|equity|pnl|portfolio)\b', re.IGNORECASE): [
            "get_account_info", "get_open_positions", "get_paper_trading_performance",
            "get_trade_history", "get_active_triggers", "get_trade_details", "get_risk_state"
        ],
        re.compile(r'^/(chart|grafik|analisis|analysis|ta|teknikal)\b', re.IGNORECASE): [
            "get_chart", "get_price_history", "get_technical_indicators",
            "get_multi_timeframe_summary", "get_atr", "get_swing_points",
            "get_structure_breaks", "get_smc_zones", "get_fibonacci_levels",
            "get_price_momentum", "get_daily_range_context", "get_optimal_intraday_levels",
            "get_market_regime", "get_asset_analysis", "get_spread_snapshot",
            "get_timesfm_forecast"
        ],
        re.compile(r'^/(macro|makro|brief|calendar|kalender|news|berita|vix|dxy)\b', re.IGNORECASE): [
            "get_market_session", "get_fundamental_brief", "get_economic_calendar",
            "get_news_items", "get_news_digest", "get_vix", "get_dxy",
            "get_cot_report", "get_bond_yield_spreads", "get_spread_snapshot",
            "get_fedwatch_probabilities", "get_treasury_yields", "get_interest_rates",
            "get_eia_oil_inventory",
            "web_search", "save_market_intelligence", "list_active_intelligence"
        ],
        re.compile(r'^/(research|riset)\b', re.IGNORECASE): [
            "web_search", "get_economic_calendar", "get_news_items",
            "get_news_digest", "get_cot_report", "get_dxy", "get_vix",
            "get_retail_sentiment", "get_price_momentum", "get_price_history",
            "get_smc_zones", "save_market_intelligence", "list_active_intelligence",
            "archive_market_intelligence", "propose_action",
            "get_fedwatch_probabilities", "get_treasury_yields", "get_interest_rates",
            "get_eia_oil_inventory"
        ],
        re.compile(r'^/(forecast|timesfm|proyeksi)\b', re.IGNORECASE): [
            "get_timesfm_forecast", "get_price_history", "get_technical_indicators",
            "get_optimal_intraday_levels", "get_daily_range_context", "get_market_regime",
            "get_atr", "get_chart"
        ],
        re.compile(r'^/(sentiment|sentimen|mood)\b', re.IGNORECASE): [
            "get_fear_greed_index", "get_funding_rate", "get_retail_sentiment",
            "get_forex_sentiment", "get_fxssi_sentiment", "get_structured_sentiment"
        ],
        re.compile(r'^/(report|laporan|tearsheet|stats|kinerja|performance)\b', re.IGNORECASE): [
            "get_paper_trading_performance", "get_trade_history", "get_trade_details",
            "get_edge_tracker_status", "get_calibration_status", "get_risk_state"
        ],
        re.compile(r'^/(risk|risiko|exposure)\b', re.IGNORECASE): [
            "get_risk_state", "get_system_health", "get_account_info", "get_open_positions"
        ],
        re.compile(r'^/(calibration|kalibrasi)\b', re.IGNORECASE): [
            "get_calibration_status", "get_market_correlations"
        ],
        re.compile(r'^/(edge|alpha|strategi)\b', re.IGNORECASE): [
            "get_edge_tracker_status", "get_market_regime", "get_timesfm_forecast"
        ],
    }

    _STOPWORDS = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
        "between", "both", "but", "by", "can", "did", "do", "does", "doing", "don",
        "down", "during", "each", "few", "for", "from", "further", "had", "has", "have",
        "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how",
        "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more",
        "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
        "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "s",
        "same", "she", "should", "so", "some", "such", "t", "than", "that", "the", "their",
        "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those",
        "through", "to", "too", "under", "until", "up", "very", "was", "we", "were",
        "what", "when", "where", "which", "while", "who", "whom", "why", "will", "with",
        "dan", "di", "ke", "dari", "ini", "itu", "yang", "untuk", "pada", "adalah", "saya",
        "kamu", "bisa", "tolong", "apa", "apakah", "bagaimana", "coba", "mohon"
    }

    def __init__(self, all_tools: List[Dict[str, Any]]):
        self.all_tools = all_tools
        self.tool_map: Dict[str, Dict[str, Any]] = {t.get("name", ""): t for t in all_tools if t.get("name")}
        self._idf: Dict[str, float] = {}
        self._semantic_index: Dict[str, Dict[str, float]] = self._build_semantic_index()

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        tokens = re.findall(r'[a-zA-Z0-9_\-]+', text.lower())
        return [t for t in tokens if len(t) >= 2 and t not in self._STOPWORDS]

    def _build_semantic_index(self) -> Dict[str, Dict[str, float]]:
        """Membangun indeks vektor TF-IDF yang dinormalisasi untuk setiap tool."""
        raw_tool_tokens: Dict[str, List[str]] = {}
        df: Dict[str, int] = {}

        for tool in self.all_tools:
            name = tool.get("name", "")
            if not name:
                continue

            doc_text = f"{name} {name.replace('_', ' ')} "
            doc_text += f"{tool.get('description', '')} "

            schema = tool.get("input_schema", {})
            props = schema.get("properties", {})
            for p_name, p_meta in props.items():
                doc_text += f"{p_name} {p_name.replace('_', ' ')} {p_meta.get('description', '')} "
                enums = p_meta.get("enum", [])
                if enums:
                    doc_text += " ".join(str(e) for e in enums) + " "

            tokens = self._tokenize(doc_text)
            raw_tool_tokens[name] = tokens
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1

        num_docs = len(raw_tool_tokens)
        self._idf = {tok: math.log((num_docs + 1.0) / (cnt + 0.5)) + 1.0 for tok, cnt in df.items()}

        index: Dict[str, Dict[str, float]] = {}
        for name, tokens in raw_tool_tokens.items():
            tf: Dict[str, float] = {}
            for tok in tokens:
                weight = 3.0 if tok in name.lower() else 1.0
                tf[tok] = tf.get(tok, 0.0) + weight

            tfidf: Dict[str, float] = {}
            for tok, count in tf.items():
                tfidf[tok] = (1.0 + math.log(count)) * self._idf.get(tok, 1.0)

            norm = sum(w * w for w in tfidf.values()) ** 0.5
            if norm > 0:
                index[name] = {tok: w / norm for tok, w in tfidf.items()}
            else:
                index[name] = tfidf

        return index

    def _semantic_vector_search(self, query: str, top_k: int = 10, min_score: float = 0.04) -> List[str]:
        """
        Melakukan pencarian semantic vector / TF-IDF matching antara kueri dan profil tool.
        Mengembalikan list nama tool yang paling relevan secara semantik.
        """
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []

        q_tf: Dict[str, float] = {}
        for t in q_tokens:
            q_tf[t] = q_tf.get(t, 0.0) + 1.0

        q_tfidf: Dict[str, float] = {}
        for t, count in q_tf.items():
            q_tfidf[t] = (1.0 + math.log(count)) * self._idf.get(t, 2.0)

        q_norm = sum(v * v for v in q_tfidf.values()) ** 0.5
        if q_norm == 0:
            return []
        q_vec = {t: v / q_norm for t, v in q_tfidf.items()}

        scores: Dict[str, float] = {}
        for name, doc_vec in self._semantic_index.items():
            sim = 0.0
            for tok, q_val in q_vec.items():
                if tok in doc_vec:
                    sim += q_val * doc_vec[tok]
                elif len(tok) >= 4:
                    for d_tok, d_val in doc_vec.items():
                        if tok in d_tok or d_tok in tok:
                            sim += q_val * d_val * 0.75
                            break
            if sim >= min_score:
                scores[name] = sim

        sorted_tools = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_tools[:top_k]]


    def _get_tools_by_names(self, names: List[str]) -> List[Dict[str, Any]]:
        result = []
        for n in names:
            if n in self.tool_map:
                result.append(self.tool_map[n])
        return result

    def route_tools_for_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Hybrid Semantic Router:
        1. Fast Regex Matching untuk explicit bot commands (/trade, /status, dll).
        2. Fast Intent Matching untuk Greeting & Multi-domain fallback.
        3. Semantic Vector / Embedding Matching untuk kueri bahasa alami kontekstual.
        """
        if not query or not isinstance(query, str) or not query.strip():
            return self.all_tools

        q_clean = query.strip()

        # 1. Fast Regex Command Dispatch (0ms overhead untuk explicit commands)
        if q_clean.startswith('/'):
            for cmd_pattern, tool_names in self.COMMAND_PATTERNS.items():
                if cmd_pattern.search(q_clean):
                    selected = self._get_tools_by_names(tool_names)
                    if selected:
                        logger.info(f"ChatToolRouter: Command matched ({len(selected)} tools)")
                        return selected
            if re.match(r'^/help\b', q_clean, re.IGNORECASE):
                return []

        # 2. Greeting / Pure Conversational (Zero-Tool Mode: hemat 100% skema tool)
        if self.GREETING_PATTERNS.search(q_clean):
            has_functional_intent = (
                bool(self.SYMBOL_PATTERNS.search(q_clean))
                or bool(self.PORTFOLIO_PATTERNS.search(q_clean))
                or bool(self.MACRO_PATTERNS.search(q_clean))
                or bool(self.RESEARCH_PATTERNS.search(q_clean))
                or bool(self.TRADE_KEYWORDS.search(q_clean))
                or bool(self.TECHNICAL_PATTERNS.search(q_clean))
                or bool(self.SYSTEM_PATTERNS.search(q_clean))
                or bool(self.SENTIMENT_PATTERNS.search(q_clean))
                or bool(self.REPORT_PATTERNS.search(q_clean))
                or bool(self.TIMESFM_PATTERNS.search(q_clean))
            )
            if not has_functional_intent:
                logger.info("ChatToolRouter: Selected ZERO-TOOL mode for conversational query")
                return []

        # 3. Research & Ad-Hoc Market Intelligence Intent (Diprioritaskan sebelum Trade Intent)
        if self.RESEARCH_PATTERNS.search(q_clean):
            research_tool_names = [
                "web_search", "get_economic_calendar", "get_news_items",
                "get_news_digest", "get_cot_report", "get_dxy", "get_vix",
                "get_retail_sentiment", "get_price_momentum", "get_price_history",
                "get_smc_zones", "save_market_intelligence", "list_active_intelligence",
                "archive_market_intelligence", "propose_action",
                "get_fedwatch_probabilities", "get_treasury_yields", "get_interest_rates",
                "get_eia_oil_inventory"
            ]
            selected = self._get_tools_by_names(research_tool_names)
            logger.info(f"ChatToolRouter: Selected RESEARCH intent ({len(selected)} tools)")
            return selected

        # 4. Trade Execution Intent (Wajib sertakan propose_action & account tools)
        if self.TRADE_KEYWORDS.search(q_clean):
            trade_tool_names = [
                "propose_action", "get_account_info", "get_open_positions",
                "get_spread_snapshot", "get_risk_state", "get_market_session",
                "get_price_history", "get_technical_indicators", "get_chart"
            ]
            selected = self._get_tools_by_names(trade_tool_names)
            logger.info(f"ChatToolRouter: Selected TRADE intent ({len(selected)} tools)")
            return selected

        # 5. TimesFM Forecast & Quantitative Projection Intent (Hanya aktif jika bukan kueri makro / riset)
        if self.TIMESFM_PATTERNS.search(q_clean) and not (self.MACRO_PATTERNS.search(q_clean) or self.RESEARCH_PATTERNS.search(q_clean)):
            timesfm_tool_names = [
                "get_timesfm_forecast", "get_price_history", "get_technical_indicators",
                "get_optimal_intraday_levels", "get_daily_range_context", "get_market_regime",
                "get_atr", "get_chart"
            ]
            selected = self._get_tools_by_names(timesfm_tool_names)
            logger.info(f"ChatToolRouter: Selected TIMESFM intent ({len(selected)} tools)")
            return selected

        has_sentiment = bool(self.SENTIMENT_PATTERNS.search(q_clean))
        has_report = bool(self.REPORT_PATTERNS.search(q_clean))
        has_portfolio = bool(self.PORTFOLIO_PATTERNS.search(q_clean))
        has_macro = bool(self.MACRO_PATTERNS.search(q_clean))
        has_symbol = bool(self.SYMBOL_PATTERNS.search(q_clean))
        has_tech = bool(self.TECHNICAL_PATTERNS.search(q_clean)) or (has_symbol and not (has_sentiment or has_report or has_macro or has_portfolio))
        has_system = bool(self.SYSTEM_PATTERNS.search(q_clean))
        has_database = bool(self.DATABASE_PATTERNS.search(q_clean))

        domain_count = sum([has_sentiment, has_report, has_portfolio, has_macro, has_tech, has_system, has_database])

        # 6. Jika pertanyaan mencakup >=3 domain sekaligus, gunakan fallback full tools (fail-safe)
        if domain_count >= 3:
            logger.info(f"ChatToolRouter: Multi-domain complex query detected ({domain_count} domains). Using full toolset.")
            return self.all_tools

        # 7. Semantic Vector Search across all 50+ tools
        semantic_tool_names = self._semantic_vector_search(q_clean, top_k=8, min_score=0.10)

        # 8. Domain Spesifik Regex Matching
        selected_names = set()

        if has_database:
            selected_names.update([
                "inspect_database_schema", "read_database_records", "propose_action"
            ])

        if has_sentiment:
            selected_names.update([
                "get_fear_greed_index", "get_funding_rate", "get_retail_sentiment",
                "get_forex_sentiment", "get_fxssi_sentiment", "get_structured_sentiment"
            ])

        if has_report:
            selected_names.update([
                "get_paper_trading_performance", "get_trade_history", "get_trade_details",
                "get_edge_tracker_status", "get_calibration_status", "get_risk_state"
            ])

        if has_portfolio:
            selected_names.update([
                "get_account_info", "get_open_positions", "get_paper_trading_performance",
                "get_trade_history", "get_active_triggers", "get_trade_details", "get_risk_state"
            ])

        if has_macro:
            selected_names.update([
                "get_market_session", "get_fundamental_brief", "get_economic_calendar",
                "get_news_items", "get_news_digest", "get_vix", "get_dxy",
                "get_cot_report", "get_bond_yield_spreads", "get_spread_snapshot",
                "get_fedwatch_probabilities", "get_treasury_yields", "get_interest_rates",
                "get_eia_oil_inventory",
                "web_search", "save_market_intelligence", "list_active_intelligence"
            ])

        if has_tech:
            selected_names.update([
                "get_chart", "get_price_history", "get_technical_indicators",
                "get_multi_timeframe_summary", "get_atr", "get_swing_points",
                "get_structure_breaks", "get_smc_zones", "get_fibonacci_levels",
                "get_price_momentum", "get_daily_range_context", "get_optimal_intraday_levels",
                "get_market_regime", "get_asset_analysis", "get_spread_snapshot",
                "get_timesfm_forecast"
            ])

        if has_system:
            selected_names.update([
                "get_system_health", "get_token_usage_and_costs", "get_recent_activity", "get_risk_state"
            ])

        # Combine domain and high-scoring semantic tools
        if semantic_tool_names:
            selected_names.update(semantic_tool_names)

        if selected_names:
            selected = self._get_tools_by_names(list(selected_names))
            if len(selected) >= 1:
                logger.info(f"ChatToolRouter: Routed to tools ({len(selected)} tools)")
                return selected

        # 9. Default Fallback: Core Primitives Bundle
        # Returns 6 essential tools rather than spending ~5,000 tokens for all 50+ tools
        core_primitive_names = [
            "get_account_info",
            "get_open_positions",
            "get_asset_analysis",
            "get_market_session",
            "get_system_health",
            "propose_action"
        ]
        core_tools = self._get_tools_by_names(core_primitive_names)
        if core_tools:
            logger.info(f"ChatToolRouter: Defaulting to Core Primitives ({len(core_tools)} tools).")
            return core_tools

        logger.info("ChatToolRouter: Defaulting to full toolset.")
        return self.all_tools

