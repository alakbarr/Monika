"""Centralized helper untuk normalisasi & perbandingan currency_bias.

Stage 1 brief bisa menghasilkan 5 label bias: strong_bullish, bullish,
bearish, strong_bearish, neutral (lihat SubmitFundamentalBriefSchema).
SETIAP kode yang membandingkan bias terhadap sinyal arah harga
('bullish'/'bearish') WAJIB melewati normalize_bias() dulu — kalau tidak,
'strong_bullish' akan gagal match 'bullish' secara diam-diam, membuat
seluruh deteksi kontradiksi (contamination guard, SSVP/CDS, coherence
check) tidak berfungsi dengan benar.
"""
from typing import Optional

_STRONG_MAP = {'strong_bullish': 'bullish', 'strong_bearish': 'bearish'}
_VALID_3STATE = ('bullish', 'bearish', 'neutral')


def normalize_bias(bias: Optional[str]) -> str:
    """Kolapskan enum 5-state ke enum 3-state yang dipakai di seluruh
    logika perbandingan/kontradiksi."""
    if not bias:
        return 'neutral'
    b = str(bias).strip().lower()
    if b in _STRONG_MAP:
        return _STRONG_MAP[b]
    return b if b in _VALID_3STATE else 'neutral'


def bias_strength(bias: Optional[str]) -> float:
    """Bobot keyakinan 0.0-1.0: 1.0 untuk strong_*, 0.6 untuk plain
    bullish/bearish, 0.0 untuk neutral. Dipakai untuk magnitude-aware
    scoring (mis. CDS lebih tinggi kalau kontradiksi melawan bias yang
    'strong')."""
    if not bias:
        return 0.0
    b = str(bias).strip().lower()
    if b in ('strong_bullish', 'strong_bearish'):
        return 1.0
    if b in ('bullish', 'bearish'):
        return 0.6
    return 0.0


def normalize_currency_bias_dict(currency_bias: dict) -> dict:
    return {k: normalize_bias(v) for k, v in (currency_bias or {}).items()}


def is_bullish(bias: Optional[str]) -> bool:
    return normalize_bias(bias) == 'bullish'


def is_bearish(bias: Optional[str]) -> bool:
    return normalize_bias(bias) == 'bearish'


def is_neutral(bias: Optional[str]) -> bool:
    return normalize_bias(bias) == 'neutral'
