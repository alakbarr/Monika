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
        r'\b(buy|sell|beli|jual|close|(?:buka|membuka)\s+(?:posisi|order|trade)|(?:tutup|menutup)\s+(?:semua\s+)?(?:posisi|order|trade)|pasang|order(?!\s*book)|eksekusi|lot|tp|take\s*profit|sizing|lot\s*size|hitung\s*lot|margin|alert|price\s*alert|(?:ingetin|ingatkan)\s*(?:soal\s*)?harga|trailing|trailing\s*stop|trigger\s*order|price\s*trigger)\b|(?<!optimasi\s)(?<!optimasi\s\s)\b(sl|stop\s*loss)\b',
        re.IGNORECASE
    )

    DIAGNOSTIC_PATTERNS = re.compile(
        r'\b(kenapa|mengapa|alasan|kok|investigasi|audit)\b.*\b(sl|stop\s*loss|loss|rugi|minus|floating|gak\s*(?:buka|open|ambil|entry)|tidak\s*(?:buka|open|ambil|entry)|(?:di)?tolak|reject|gagal|kalah|kena|lewatkan|skip|diam(?:\s*aja)?|nganggur|tidur|pasif|bengong|buy|sell|beli|jual|entry|posisi)\b|\b(kenapa\s+(?:bot|agent|monika)\s+(?:gak|tidak|belum)\s+(?:buka|open|ambil|trading|entry))\b',
        re.IGNORECASE
    )

    CONDITIONAL_ANALYSIS_PATTERNS = re.compile(
        r'\b(aman(?:\s*gak|\s*tidak|\s*kah)?|bisa\s+(?:buy|sell|beli|jual)|boleh\s+(?:buy|sell)|bagus(?:\s*gak|\s*an)?|apakah\s+(?:buy|sell|bagus)|rekomendasi|setup\s*(?:terbaik|bagus|hari\s*ini)|market\s*scan|peluang)\b',
        re.IGNORECASE
    )

    PRE_EVENT_PATTERNS = re.compile(
        r'\b(beberapa jam lagi|sebelum rilis|prediksi.*(?:rilis|data|ekspektasi|konsensus|pce|cpi|nfp|gdp|suku bunga|inflasi)|nowcast|kejutan.*pasar|pra-rilis|pre-event)\b',
        re.IGNORECASE
    )

    DAILY_PLAYBOOK_PATTERNS = re.compile(
        r'\b(hari ini ada berita apa|penggerak pasar|peluang.*(?:bagus|jelas|hari ini)|pair.*peluang|fokus trading hari ini|playbook.*hari ini|katalis.*hari ini)\b',
        re.IGNORECASE
    )

    SCRIPTING_PATTERNS = re.compile(
        r'\b(script|python|korelasi.*rolling|sandbox|code|kode|rumus|hurst|kelly|plateau|custom\s*indicator|otomatisasi|automation|tulis\s+kode|buatkan\s+script|jalankan\s+script|simpan\s+script|save\s+script|list\s+script|daftar\s+script|run\s+script)\b',
        re.IGNORECASE
    )

    GREETING_PATTERNS = re.compile(
        r'^(halo|hai|hi|hello|hey|selamat\s+(pagi|siang|sore|malam)|assalamualaikum|tes|test|ping|p|siapa\s+kamu|terima\s*kasih|makasih|thanks|thank\s*you)\b',
        re.IGNORECASE
    )

    PORTFOLIO_PATTERNS = re.compile(
        r'\b(posisi|position|saldo|balance|equity|pnl|profit|rugi|loss|minus|untung|margin|kinerja|performance|paper|history|riwayat|trigger|drawdown|korelasi|correlation|akun|kondisi\s*akun|rekap|floating|unrealized|modal|deposit|komisi|commission|swap|fee|biaya\s*broker|tick|tick\s*flow|delta\s*tick|export\s*tick|raw\s*tick)\b|(?:(?:minggu|hari)\s*ini.*(?:pnl|profit|rugi|transaksi|saldo|posisi|trade))|(?:(?:pnl|profit|rugi|transaksi|saldo|posisi|trade).*(?:minggu|hari)\s*ini)',
        re.IGNORECASE
    )

    MACRO_PATTERNS = re.compile(
        r'\b(makro|macro|fundamental|berita|news|fomc|cpi|nfp|fed|fedwatch|kalender|calendar|dxy|dollar|dolar|greenback|vix|yield|treasury|suku\s*bunga|interest\s*rate|cot|sesi|session|eia|inventory|cadangan\s*minyak|dot\s*plot|sep|rate\s*cut|rate\s*hike|inflasi|inflation|pce|gdp|ppi|pengangguran|unemployment|payroll|hawkish|dovish|press\s*conference|konferensi\s*pers|bank\s*sentral|central\s*bank|kebijakan\s*moneter|monetary\s*policy|market|pasar|kondisi\s*pasar|situasi\s*pasar|keadaan\s*pasar|event|events|agenda|volatil\w*|powell|lagarde|ueda|bailey|bi_rate|bank\s*indonesia|idr|usdidr|rupiah|jisdor|bps|earnings|laba\s*perusahaan|corporate\s*earnings|eps)\b|\b(kenapa|mengapa|alasan|penyebab)\b.*\b(naik|turun|rally|drop|lonjak|anjlok|menguat|melemah)\b',
        re.IGNORECASE
    )

    TECHNICAL_PATTERNS = re.compile(
        r'\b(chart|grafik|teknikal|technical|indikator|indicator|rsi|macd|ema|sma|smc|ict|fvg|order\s*block|ob|swing|support|resistance|bos|choch|fibonacci|fibo|adr|range|level|regime|trend|trending|ranging|momentum|harga|price|quote|(?:exchange\s*rate|rate\s*of\s*change|roc)|spread|candle|analisis|setup|sinyal|signal|sweep|liquidity\s*sweep|pattern|pattern\s*similarity|pola|smt|smt\s*divergence|divergence|divergensi|pivot|camarilla|woodie|ichimoku|tenkan|kijun|cloud|awan|harmoni|harmonic|gartley|bat|butterfly|crab|double\s*top|double\s*bottom|head\s*and\s*shoulders|h&s|ih&s|stochastic|seasonality|musiman)\b',
        re.IGNORECASE
    )

    SYMBOL_PATTERNS = re.compile(
        r'\b(eurusd|gbpusd|usdjpy|audusd|usdcad|usdchf|nzdusd|eurgbp|euraud|gbpjpy|cadjpy|chfjpy|audnzd|audjpy|eurchf|gbpaud|gbpcad|gbpchf|nzdjpy|xauusd|gold|emas|btcusd|btc|bitcoin|xtiusd|wti|oil|minyak|xbrusd|brent|ethusd|eth|eu|gu|uj|gj|au|uc|nu|ej|eg|us30|nasdaq|ustec|spx|dow|usdidr)\b',
        re.IGNORECASE
    )

    SYSTEM_PATTERNS = re.compile(
        r'\b(status|health|server|token|biaya|cost|usage|log|aktivitas|activity|audit|koneksi|konek|restart|uptime|risk|resiko|circuit\s*breaker|doctor|diagnostik|cron|tiap|setiap|jadwal|schedule|rutin|remind|ingat\w*|ingetin|ingatkan|notif\w*|konfigurasi|setting\w*|settings|atur\w*|screenshot|layar|tangkap\s*layar|cpu|ram|memory|memori|disk|resource|resources|telemetri|telemetry|terminal|cmd|powershell|bash|shell|gui|mouse|klik|click|ketik|type|latency|latensi|rtt|backup|ngapain|lagi\s*apa|sedang\s*apa|compile|mql5|expert\s*advisor|\bea\b|broker\s*logs?|algo\s*trading)\b|\b(?:cek\s+)?ping\s+(?:server|bot|host|ip|jaringan|koneksi)\b',
        re.IGNORECASE
    )

    RESEARCH_PATTERNS = re.compile(
        r'\b(deep-research|deep\s*research|riset\s*mendalam|investigasi|konsensus|whisper|saturasi|ekspektasi|skenario|intel|intelijen|pre-event|breaking|geopolitik|event\s*makro|macro\s*event|probabilitas\s*event|event\s*probability|web[- ]?search|search|cari(?!\s*setup)|browsing|(?:academic\s*paper|paper\s*akademik|research\s*paper|whitepaper)|akademik|academic|arxiv|browser|drission|cloudflare|paywall|twitter|tweet|reddit|forum|social\s*sentiment)\b|^\s*/research\b',
        re.IGNORECASE
    )

    INTEL_PATTERNS = re.compile(
        r'\b(ingat(?:kan)?\s+bahwa|catat\s+bahwa|simpan\s+(?:info|intel|informasi|catatan)|intelijen\s+pasar|market\s+intel)\b',
        re.IGNORECASE
    )

    SKILL_PATTERNS = re.compile(
        r'\b(buat\s+skill|tambah\s+skill|create\s+skill|generate\s+skill|bikin\s+skill|skill\s+baru|skill|plugin)\b',
        re.IGNORECASE
    )

    LEARNING_PATTERNS = re.compile(
        r'\b(belajar|learn|learning|refleksi|reflection|negative\s*constraint|lesson|crystalliz(?:e|er)|kesalahan)\b|\b(evaluasi|eval)\b(?!\s+(?:breakout|chart|setup|pair|indikator|teknikal|harga|candle|level|fvg|ob|sweep))',
        re.IGNORECASE
    )

    BACKTEST_PATTERNS = re.compile(
        r'\b(backtest|simulasi|monte\s*carlo|walk[- ]?forward|wfa|forward\s*test|harness|arena|plateau|curve[- ]?fitting|overfitting|optimasi\s*parameter)\b',
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
        r'\b(tearsheet|laporan|report|kinerja|performa|performance|equity\s*curve|drawdown|stats|statistik|sharpe|sortino|expectancy|excel|xlsx|docx|word|pptx|powerpoint|slide|deck|presentasi|pitch|pdf|export.*data|export.*transaksi|parquet|win\s*rate|pnl\s*per\s*pair|evaluasi\s*rugi)\b',
        re.IGNORECASE
    )

    DATABASE_PATTERNS = re.compile(
        r'\b(database|db|tabel|table|schema|skema|kolom|record|records|baris|row|rows|query|select|insert|update|delete|mutasi|mutation|debate\s*transcripts?)\b',
        re.IGNORECASE
    )

    WORKSPACE_PATTERNS = re.compile(
        r'\b(obsidian|notion|google|gdrive|drive|gsheet|gsheets|gdoc|gdocs|catatan|jurnal|journal|note|notes|excel|spreadsheet|sheet|sheets|csv|xlsx|xls|dokumen|doc|docx|vault|tulis|baca\s*file|simpan\s*ke|folder|direktori|directory|file)\b',
        re.IGNORECASE
    )

    COMMAND_PATTERNS = {
        re.compile(r'^/(note|notes|catatan|jurnal|journal|excel|sheet|doc|workspace|file|drive|gdrive|gsheet)\b', re.IGNORECASE): [
            "mcp_filesystem_workspace_fs_read_file", "mcp_filesystem_workspace_fs_write_file",
            "mcp_filesystem_workspace_fs_list_directory", "mcp_filesystem_workspace_fs_search_files",
            "mcp_excel_tabular_excel_read_sheet", "mcp_excel_tabular_excel_append_row",
            "mcp_excel_tabular_excel_list_sheets", "mcp_excel_tabular_excel_create_sheet"
        ],
        re.compile(r'^/(database|db|schema|tables|tabel|sql)\b', re.IGNORECASE): [
            "inspect_database_schema", "read_database_records", "query_database_sql", "propose_action"
        ],
        re.compile(r'^/(trade|buy|sell|order|close|beli|jual|buka|tutup)\b', re.IGNORECASE): [
            "propose_action", "get_account_info", "get_open_positions",
            "get_spread_snapshot", "get_risk_state", "get_market_session",
            "get_price_history", "get_technical_indicators", "get_chart",
            "calculate_position_size", "calculate_margin", "get_broker_expenses_summary"
        ],
        re.compile(r'^/(status|health|ping|system|telemetry)\b', re.IGNORECASE): [
            "get_system_health", "get_token_usage_and_costs", "get_recent_activity", "get_risk_state",
            "get_server_telemetry", "capture_terminal_screenshot", "read_system_logs"
        ],
        re.compile(r'^/(positions|posisi|balance|saldo|equity|pnl|portfolio)\b', re.IGNORECASE): [
            "get_account_info", "get_open_positions", "get_paper_trading_performance",
            "get_trade_history", "get_active_triggers", "get_trade_details", "get_risk_state",
            "get_broker_expenses_summary", "simulate_price_shock"
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
            "get_fedwatch_probabilities", "get_central_bank_expectations", "get_treasury_yields", "get_interest_rates",
            "get_eia_oil_inventory",
            "web_search", "save_market_intelligence", "list_active_intelligence"
        ],
        re.compile(r'^/(research|riset)\b', re.IGNORECASE): [
            "web_search", "get_economic_calendar", "get_news_items",
            "get_news_digest", "get_cot_report", "get_dxy", "get_vix",
            "get_retail_sentiment", "get_price_momentum", "get_price_history",
            "get_smc_zones", "save_market_intelligence", "list_active_intelligence",
            "archive_market_intelligence", "propose_action",
            "get_fedwatch_probabilities", "get_central_bank_expectations", "get_treasury_yields", "get_interest_rates",
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

        has_workspace_intent = bool(self.WORKSPACE_PATTERNS.search(query))
        scores: Dict[str, float] = {}
        for name, doc_vec in self._semantic_index.items():
            if name.startswith("mcp_") and not has_workspace_intent:
                continue
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


    def update_tools(self, tools: List[Dict[str, Any]]):
        """Update or add new tools (e.g. dynamically loaded MCP tools) to the router."""
        changed = False
        for t in tools:
            name = t.get("name")
            if name and name not in self.tool_map:
                self.all_tools.append(t)
                self.tool_map[name] = t
                changed = True
        if changed:
            self._semantic_index = self._build_semantic_index()

    def _get_tools_by_names(self, names: List[str]) -> List[Dict[str, Any]]:
        result = []
        for n in names:
            if n in self.tool_map:
                result.append(self.tool_map[n])
        return result

    def _finalize_selected(self, selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Always inject baseline bundle (search_tools, get_market_quote, get_system_health, get_account_info, web_search)."""
        if not selected:
            return []
        names = {t.get("name") for t in selected if isinstance(t, dict)}
        baseline = ("search_tools", "get_market_quote", "get_system_health", "get_account_info", "web_search")
        for inj in baseline:
            if inj in self.tool_map and inj not in names:
                selected.append(self.tool_map[inj])
                names.add(inj)
        return selected

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

        # 0. Translation bypass (0 tools, pure LLM turn)
        if re.search(r'^(translate|terjemahkan|artikan)\b', q_clean, re.IGNORECASE):
            if not any(k in q_clean.lower() for k in ("http", "www", "indicator", "chart", "pnl", "balance", "gold", "xau", "eur", "usd", "code", "script", "def ", "import ")):
                logger.info("ChatToolRouter: Selected ZERO-TOOL mode for translation request")
                return []

        # Config introspection check (route system health / settings instead of technical indicators)
        if re.search(r'\b(konfigurasi|setting|settings|parameter\s*risk|config|ubah\s+config|naikin\s+risk|turunin\s+risk)\b', q_clean, re.IGNORECASE) and not re.search(r'\b(chart|grafik|candle|indikator|indicator)\b', q_clean, re.IGNORECASE):
            config_tools = ["get_system_health", "get_risk_state", "run_system_doctor_check", "update_config_parameter", "propose_action"]
            selected = self._get_tools_by_names(config_tools)
            if selected:
                return self._finalize_selected(selected)

        # 1. Fast Regex Command Dispatch (0ms overhead untuk explicit commands)
        if q_clean.startswith('/'):
            for cmd_pattern, tool_names in self.COMMAND_PATTERNS.items():
                if cmd_pattern.search(q_clean):
                    selected = self._get_tools_by_names(tool_names)
                    if selected:
                        logger.info(f"ChatToolRouter: Command matched ({len(selected)} tools)")
                        return self._finalize_selected(selected)
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
                or bool(self.WORKSPACE_PATTERNS.search(q_clean))
                or bool(self.INTEL_PATTERNS.search(q_clean))
                or bool(self.SKILL_PATTERNS.search(q_clean))
            )
            if not has_functional_intent:
                logger.info("ChatToolRouter: Selected ZERO-TOOL mode for conversational query")
                return []

        # 3. Market Intelligence Direct Intent (P5.2 / Q62)
        if self.INTEL_PATTERNS.search(q_clean):
            intel_tool_names = [
                "save_market_intelligence", "list_active_intelligence", "archive_market_intelligence"
            ]
            selected = self._get_tools_by_names(intel_tool_names)
            logger.info(f"ChatToolRouter: Selected INTEL intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 4. Skill Authoring & Extension Intent (P5.3 / Q63)
        if self.SKILL_PATTERNS.search(q_clean):
            skill_tool_names = ["skill_view", "skills_list", "propose_action"]
            for t_name in self.tool_map:
                if "skill" in t_name.lower():
                    if t_name not in skill_tool_names:
                        skill_tool_names.append(t_name)
            selected = self._get_tools_by_names(skill_tool_names)
            logger.info(f"ChatToolRouter: Selected SKILL intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 5. Workspace & Second-Brain Intent (Obsidian, Excel, Notion, Files)
        if self.WORKSPACE_PATTERNS.search(q_clean):
            workspace_tool_names = [
                "mcp_filesystem_workspace_fs_read_file",
                "mcp_filesystem_workspace_fs_write_file",
                "mcp_filesystem_workspace_fs_list_directory",
                "mcp_filesystem_workspace_fs_search_files",
                "mcp_excel_tabular_excel_read_sheet",
                "mcp_excel_tabular_excel_append_row",
                "mcp_excel_tabular_excel_list_sheets",
                "mcp_excel_tabular_excel_create_sheet",
                "mcp_local_market_fs_fs_read_file",
                "mcp_local_market_fs_fs_write_file",
            ]
            for t_name in self.tool_map:
                if t_name.startswith("mcp_") and any(k in t_name for k in ("workspace", "fs", "excel", "notion", "file", "google", "sheets", "docs")):
                    if t_name not in workspace_tool_names:
                        workspace_tool_names.append(t_name)

            if self.TRADE_KEYWORDS.search(q_clean) or self.PORTFOLIO_PATTERNS.search(q_clean) or self.SYMBOL_PATTERNS.search(q_clean):
                workspace_tool_names.extend([
                    "get_account_info", "get_open_positions", "get_trade_history",
                    "get_trade_details", "get_journal_entries", "propose_action"
                ])

            if any(k in q_clean.lower() for k in ("jurnal", "journal", "catatan", "note")):
                workspace_tool_names.extend(["get_journal_entries", "get_trade_history", "get_account_info"])

            if any(k in q_clean.lower() for k in ("broker", "metatrader", "mt5", "log")):
                workspace_tool_names.extend(["get_mt5_broker_logs", "computer_use", "terminal", "read_system_logs"])

            if self.RESEARCH_PATTERNS.search(q_clean) or self.MACRO_PATTERNS.search(q_clean):
                workspace_tool_names.extend([
                    "web_search", "read_url", "get_economic_calendar", "get_fundamental_brief", "save_market_intelligence"
                ])

            selected = self._get_tools_by_names(workspace_tool_names)
            if selected:
                logger.info(f"ChatToolRouter: Selected WORKSPACE intent ({len(selected)} tools)")
                return self._finalize_selected(selected)

        # 4. Research & Ad-Hoc Market Intelligence Intent (Diprioritaskan sebelum Trade Intent)
        if self.RESEARCH_PATTERNS.search(q_clean):
            research_tool_names = [
                "web_search", "read_url", "browser", "search_academic", "search_social_sentiment",
                "get_economic_calendar", "get_earnings_calendar", "get_indonesia_macro", "get_news_items",
                "get_news_digest", "get_cot_report", "get_dxy", "get_vix",
                "get_retail_sentiment", "get_price_momentum", "get_price_history",
                "get_smc_zones", "save_market_intelligence", "list_active_intelligence",
                "archive_market_intelligence", "propose_action",
                "get_fedwatch_probabilities", "get_central_bank_expectations", "get_treasury_yields", "get_interest_rates",
                "get_eia_oil_inventory"
            ]
            selected = self._get_tools_by_names(research_tool_names)
            logger.info(f"ChatToolRouter: Selected RESEARCH intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 4. Learning & Continuous Improvement Intent (Refleksi, Lessons, Feedback Loop)
        if self.LEARNING_PATTERNS.search(q_clean):
            learning_tool_names = [
                "trigger_learning_cycle", "get_active_negative_constraints", "get_asset_analysis", "get_trade_details",
                "get_trade_history", "get_recent_activity", "get_risk_state",
                "get_paper_trading_performance", "propose_action"
            ]
            selected = self._get_tools_by_names(learning_tool_names)
            logger.info(f"ChatToolRouter: Selected LEARNING intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 5. Diagnostic / Post-Mortem Intent (Kenapa SL, kenapa bot gak buka posisi, dsb)
        if self.DIAGNOSTIC_PATTERNS.search(q_clean):
            diagnostic_tool_names = [
                "get_rejection_history", "get_latest_risk_verdict", "get_system_health",
                "read_system_logs", "get_trade_details", "get_trade_history", "get_risk_state",
                "search_historical_memories", "get_asset_analysis", "get_fundamental_brief",
                "get_recent_activity", "get_economic_calendar", "get_account_info", "get_spread_snapshot"
            ]
            if self.SYMBOL_PATTERNS.search(q_clean):
                diagnostic_tool_names.extend(["get_chart", "get_smc_zones", "get_technical_indicators", "get_market_quote"])
            selected = self._get_tools_by_names(diagnostic_tool_names)
            logger.info(f"ChatToolRouter: Selected DIAGNOSTIC intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 6. Python Scripting & Sandbox Calculation Intent
        if self.SCRIPTING_PATTERNS.search(q_clean):
            scripting_tool_names = [
                "execute_analysis_code", "execute_code", "save_script", "list_saved_scripts", "run_saved_script",
                "get_price_history", "get_technical_indicators", "get_market_quote", "get_spread_snapshot",
                "get_treasury_yields", "get_dxy", "get_vix", "get_market_correlations",
                "run_analytical_query"
            ]
            selected = self._get_tools_by_names(scripting_tool_names)
            logger.info(f"ChatToolRouter: Selected SCRIPTING intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 7. Quantitative Simulation & Backtesting Intent
        if self.BACKTEST_PATTERNS.search(q_clean):
            backtest_tool_names = [
                "run_strategy_backtest", "run_monte_carlo_simulation", "run_walk_forward_analysis",
                "run_parameter_plateau_optimization", "get_edge_tracker_status", "query_signal_performance",
                "get_active_negative_constraints", "export_historical_data_csv", "get_price_history",
                "get_technical_indicators", "get_market_regime", "get_seasonality", "save_script", "run_saved_script"
            ]
            selected = self._get_tools_by_names(backtest_tool_names)
            logger.info(f"ChatToolRouter: Selected BACKTEST intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 7.1 Pre-Event Macro Nowcasting & Transmission Intent (Q152)
        if self.PRE_EVENT_PATTERNS.search(q_clean):
            pre_event_tools = [
                "get_economic_calendar", "get_macro_priced_in_score", "get_fedwatch_probabilities",
                "get_treasury_yields", "get_dxy", "get_cot_report", "get_retail_sentiment",
                "get_smc_zones", "get_market_session", "get_fundamental_brief", "get_news_digest",
                "web_search", "get_market_correlations", "get_price_history"
            ]
            if self.SYMBOL_PATTERNS.search(q_clean):
                pre_event_tools.extend(["get_chart", "get_technical_indicators", "get_asset_analysis"])
            selected = self._get_tools_by_names(pre_event_tools)
            logger.info(f"ChatToolRouter: Selected PRE_EVENT intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 7.2 Daily Catalyst & Opportunity Playbook Intent (Q151)
        if self.DAILY_PLAYBOOK_PATTERNS.search(q_clean):
            daily_playbook_tools = [
                "get_economic_calendar", "get_news_digest", "get_news_items", "trigger_market_scan",
                "get_retail_sentiment", "get_cot_report", "get_market_session", "get_fundamental_brief",
                "get_smc_zones", "get_optimal_intraday_levels", "get_daily_range_context",
                "get_spread_snapshot", "get_dxy", "web_search"
            ]
            if self.SYMBOL_PATTERNS.search(q_clean):
                daily_playbook_tools.extend(["get_chart", "get_technical_indicators", "get_asset_analysis"])
            selected = self._get_tools_by_names(daily_playbook_tools)
            logger.info(f"ChatToolRouter: Selected DAILY_PLAYBOOK intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 8. Trade Execution / Setup Inquiry Intent
        if (self.TRADE_KEYWORDS.search(q_clean) or self.CONDITIONAL_ANALYSIS_PATTERNS.search(q_clean)) and not (self.MACRO_PATTERNS.search(q_clean) and not self.TRADE_KEYWORDS.search(q_clean)):
            is_conditional = bool(self.CONDITIONAL_ANALYSIS_PATTERNS.search(q_clean))
            trade_tool_names = [
                "propose_action", "calculate_position_size", "calculate_margin", "create_price_alert",
                "set_trailing_stop", "close_positions_batch",
                "get_account_info", "get_open_positions", "get_pending_orders", "get_spread_snapshot",
                "get_risk_state", "get_price_history", "get_chart"
            ]
            if is_conditional or self.SYMBOL_PATTERNS.search(q_clean):
                trade_tool_names.extend([
                    "get_atr", "get_smc_zones", "get_asset_analysis", "get_dxy", "get_economic_calendar"
                ])
            selected = self._get_tools_by_names(trade_tool_names)
            logger.info(f"ChatToolRouter: Selected TRADE/ANALYSIS intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        # 9. TimesFM Forecast & Quantitative Projection Intent (Hanya aktif jika bukan kueri makro / riset)
        if self.TIMESFM_PATTERNS.search(q_clean) and not (self.MACRO_PATTERNS.search(q_clean) or self.RESEARCH_PATTERNS.search(q_clean)):
            timesfm_tool_names = [
                "get_timesfm_forecast", "get_price_history", "get_technical_indicators",
                "get_optimal_intraday_levels", "get_daily_range_context", "get_market_regime",
                "get_atr", "get_chart"
            ]
            selected = self._get_tools_by_names(timesfm_tool_names)
            logger.info(f"ChatToolRouter: Selected TIMESFM intent ({len(selected)} tools)")
            return self._finalize_selected(selected)

        has_sentiment = bool(self.SENTIMENT_PATTERNS.search(q_clean))
        has_report = bool(self.REPORT_PATTERNS.search(q_clean))
        has_portfolio = bool(self.PORTFOLIO_PATTERNS.search(q_clean))
        has_macro = bool(self.MACRO_PATTERNS.search(q_clean))
        has_symbol = bool(self.SYMBOL_PATTERNS.search(q_clean))
        has_tech = bool(self.TECHNICAL_PATTERNS.search(q_clean)) or (has_symbol and not (has_sentiment or has_report or has_macro or has_portfolio))
        has_system = bool(self.SYSTEM_PATTERNS.search(q_clean))
        has_database = bool(self.DATABASE_PATTERNS.search(q_clean))
        has_workspace = bool(self.WORKSPACE_PATTERNS.search(q_clean))

        domain_count = sum([has_sentiment, has_report, has_portfolio, has_macro, has_tech, has_system, has_database, has_workspace])

        # 10. Jika pertanyaan mencakup >=3 domain sekaligus, gunakan fallback full tools (fail-safe)
        if domain_count >= 3:
            logger.info(f"ChatToolRouter: Multi-domain complex query detected ({domain_count} domains). Using full toolset.")
            return self.all_tools

        # 11. Semantic Vector Search across all tools
        semantic_tool_names = self._semantic_vector_search(q_clean, top_k=8, min_score=0.10)

        # 12. Domain Spesifik Regex Matching
        selected_names = set()

        if has_workspace:
            for t_name in self.tool_map:
                if t_name.startswith("mcp_") and any(k in t_name for k in ("workspace", "fs", "excel", "notion", "file")):
                    selected_names.add(t_name)

        if has_database:
            selected_names.update([
                "inspect_database_schema", "read_database_records", "query_database_sql", "query_signal_performance",
                "export_debate_transcripts", "export_dataset_file", "run_analytical_query", "propose_action"
            ])

        if has_sentiment:
            selected_names.update([
                "get_fear_greed_index", "get_funding_rate", "get_retail_sentiment",
                "get_forex_sentiment", "get_fxssi_sentiment", "get_structured_sentiment",
                "search_social_sentiment"
            ])

        if has_report:
            selected_names.update([
                "export_trades_to_excel", "generate_docx_report", "generate_pptx_deck", "generate_tearsheet_report",
                "export_dataset_file", "get_paper_trading_performance", "get_pnl_summary", "get_trade_history", "get_trade_details",
                "query_signal_performance", "get_edge_tracker_status", "get_calibration_status", "get_risk_state",
                "get_market_correlations", "run_analytical_query", "get_broker_expenses_summary"
            ])

        if has_portfolio:
            selected_names.update([
                "get_account_info", "get_open_positions", "get_pnl_summary", "get_risk_state", "propose_action"
            ])
            if re.search(r'\b(history|riwayat)\b', q_clean, re.I):
                selected_names.add("get_trade_history")
            if re.search(r'\b(paper)\b', q_clean, re.I):
                selected_names.add("get_paper_trading_performance")
            if re.search(r'\b(trigger)\b', q_clean, re.I):
                selected_names.add("get_active_triggers")
            if re.search(r'\b(tick|tick\s*flow|delta\s*tick|export\s*tick|raw\s*tick)\b', q_clean, re.I):
                selected_names.update(["get_recent_tick_flow", "export_tick_data"])
            if re.search(r'\b(shock|stress|simulasi)\b', q_clean, re.I):
                selected_names.add("simulate_price_shock")
            if re.search(r'\b(komisi|commission|fee|biaya\s*broker|swap)\b', q_clean, re.I):
                selected_names.add("get_broker_expenses_summary")

        if has_macro:
            selected_names.update([
                "get_market_session", "get_fundamental_brief", "get_economic_calendar",
                "get_news_items", "get_news_digest", "get_vix", "get_dxy",
                "get_cot_report", "get_bond_yield_spreads", "get_spread_snapshot",
                "get_fedwatch_probabilities", "get_central_bank_expectations", "get_treasury_yields", "get_interest_rates",
                "get_macro_priced_in_score", "get_eia_oil_inventory", "get_market_correlations",
                "get_indonesia_macro", "get_earnings_calendar", "browser",
                "get_atr", "get_market_regime",
                "web_search", "read_url", "search_academic", "save_market_intelligence", "list_active_intelligence"
            ])

        if has_tech:
            selected_names.update([
                "get_chart", "get_price_history", "get_market_quote", "get_technical_indicators",
                "get_multi_timeframe_summary", "get_atr", "get_swing_points",
                "get_structure_breaks", "get_smc_zones", "get_fibonacci_levels",
                "get_synthetic_cross_rate", "get_price_momentum", "get_daily_range_context", "get_optimal_intraday_levels",
                "get_market_regime", "get_volatility_regime", "scan_pattern_similarity", "get_timesfm_forecast", "trigger_market_scan"
            ])
            if re.search(r'\b(smt|divergence|divergensi)\b', q_clean, re.I):
                selected_names.update(["get_smt_divergence", "get_divergences"])
            if re.search(r'\b(breaker|judas|inducement|wick|equal|eqh|eql)\b', q_clean, re.I):
                selected_names.update(["get_breaker_blocks", "get_judas_swing", "get_inducements", "get_wick_to_wick_fvg", "get_inverted_fvg", "get_equal_highs_lows"])
            if re.search(r'\b(pivot|camarilla|woodie)\b', q_clean, re.I):
                selected_names.add("get_pivot_points")
            if re.search(r'\b(ichimoku|tenkan|kijun|cloud)\b', q_clean, re.I):
                selected_names.add("get_ichimoku")
            if re.search(r'\b(pattern|pola|harmonic)\b', q_clean, re.I):
                selected_names.add("scan_chart_patterns")
            if re.search(r'\b(seasonality|musiman)\b', q_clean, re.I):
                selected_names.add("get_seasonality")

        if has_system:
            selected_names.update([
                "get_system_health", "run_system_doctor_check", "manage_cron",
                "get_token_usage_and_costs", "get_recent_activity", "get_risk_state",
                "get_server_telemetry", "capture_terminal_screenshot", "read_system_logs",
                "restart_mt5_service", "update_config_parameter", "terminal", "computer_use", "process_manage",
                "get_latency_breakdown", "backup_database",
                "compile_mql5_ea", "get_mt5_broker_logs", "get_mt5_terminal_info"
            ])

        # Combine domain and high-scoring semantic tools within progressive budgets
        if semantic_tool_names:
            if has_portfolio and not (has_tech or has_macro or has_report):
                budget = 6
            elif has_tech or has_macro:
                budget = 19
            else:
                budget = 14
            for st in semantic_tool_names:
                if len(selected_names) >= budget:
                    break
                selected_names.add(st)

        if selected_names:
            selected = self._get_tools_by_names(list(selected_names))
            if len(selected) >= 1:
                logger.info(f"ChatToolRouter: Routed to tools ({len(selected)} tools)")
                return self._finalize_selected(selected)

        # 13. Default Fallback: Core Primitives Bundle (6 tools)
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

