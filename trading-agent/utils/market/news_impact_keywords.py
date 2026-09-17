"""Sumber tunggal untuk taksonomi shock/high-impact keywords — dipakai oleh
news_watcher.py (regex fallback) DAN news_digest.py (AI classification guard),
supaya tidak divergen."""

SHOCK_KEYWORDS = [
    # Geopolitical — frasa spesifik (bukan single words seperti 'war', 'attack')
    'missile attack', 'missile strikes', 'military strikes', 'military strikes on', 'airstrike on',
    'war declared', 'declares war', 'war breaks out',
    'coup attempt', 'coup d\'etat', 'martial law declared', 'state of emergency declared',
    'assassination of', 'targeted assassination',
    'nuclear threat', 'nuclear strike', 'nuclear missile', 'nuclear attack',
    'terrorist attack on', 'terror attack kills',
    # Financial system shocks — frasa spesifik
    'bank run', 'bank collapse', 'bank failure', 'banking crisis',
    'circuit breaker activated', 'trading halt activated', 'trading suspended',
    'flash crash', 'black swan event',
    'sanctions imposed on', 'new sanctions on', 'sweeping sanctions',
    'oil embargo declared', 'oil embargo against',
    'capital controls imposed', 'capital controls enacted',
    'debt ceiling breached', 'debt ceiling crisis',
    'credit rating downgraded', 'sovereign downgrade',
    'sovereign default', 'nation defaults', 'debt default',
    # Monetary intervention — spesifik
    'yen intervention', 'boj currency intervention', 'emergency currency intervention',
    'emergency rate cut', 'emergency rate hike', 'unscheduled rate',
    # Crypto & Bitcoin Shocks — spesifik
    'crypto exchange collapse', 'crypto exchange bankrupt', 'exchange insolvent',
    'sec sues crypto', 'sec charges crypto', 'sec crypto lawsuit',
    'spot bitcoin etf approved', 'bitcoin etf rejected',
    'bitcoin flash crash', 'btc flash crash',
    'crypto ban enacted', 'crypto ban imposed',
    'stablecoin depeg', 'usdt depeg', 'usdc depeg', 'tether depeg',
    # Energy Shocks — spesifik
    'opec emergency meeting', 'opec surprise output cut', 'opec surprise cut',
    'strait of hormuz', 'oil supply disruption', 'pipeline explosion',
    'major pipeline explosion',
]

HIGH_IMPACT_KEYWORDS = [
    'fomc', 'federal reserve', 'fed rate', 'rate hike', 'rate cut', 'emergency cut',
    'powell', 'rate decision', 'monetary policy', 'quantitative tightening', 'qt',
    'recession', 'financial crisis', 'nfp', 'non-farm payroll', 'cpi surprise',
    'inflation surge', 'gdp contraction', 'unemployment spike', 'ecb rate', 'boe rate',
    'boj', 'bank of japan intervention', 'rba rate', 'reserve bank australia',
    'bitcoin halving', 'sec etf decision', 'crypto market structure',
] + SHOCK_KEYWORDS

DEESCALATION_KEYWORDS = [
    'ceasefire', 'truce', 'peace talks', 'tariff exemption', 'sanctions waiver',
    'dispute resolved', 'diplomatic accord', 'easing tensions', 'postpone tariff',
    'tariff delay', 'de-escalation', 'peace agreement', 'hostage deal',
    'trade deal agreed', 'sanctions relief', 'border agreement',
]

REHASH_KEYWORDS = [
    'reiterates stance', 'repeats comments', 'unchanged outlook', 'previous remarks',
    'as widely expected', 'in line with prior', 'no new signals', 'reaffirms guidance',
    'largely priced in', 'rehashes', 'reiterates commitment',
]
