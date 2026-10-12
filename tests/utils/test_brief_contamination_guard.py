import pytest
from utils.protocol.brief_contamination_guard import BriefContaminationGuard

@pytest.fixture
def mock_settings():
    return {
        "trading": {
            "ssvp": {
            }
        }
    }

class DummySession:
    async def execute(self, *args, **kwargs):
        class DummyResult:
            def scalars(self):
                class DummyScalars:
                    def all(self): return []
                return DummyScalars()
            def scalar_one_or_none(self):
                return None
        return DummyResult()

@pytest.mark.asyncio
async def test_brief_internal_consistency_eur(mock_settings):
    session = DummySession()

    # 1. Bullish EUR + Bullish USD
    brief_bull = {
        "currency_bias": {"USD": "bullish", "EUR": "bullish"},
        "risk_sentiment": "mixed",
        "confidence": 0.8
    }
    is_safe, issues, risk_score = await BriefContaminationGuard.validate_brief_integrity(session, brief_bull, mock_settings)
    assert risk_score >= 0.40
    assert any("Both USD and EUR labeled 'bullish'" in iss for iss in issues)

    # 2. Bearish EUR + Bearish USD
    brief_bear = {
        "currency_bias": {"USD": "bearish", "EUR": "bearish"},
        "risk_sentiment": "mixed",
        "confidence": 0.8
    }
    is_safe, issues, risk_score = await BriefContaminationGuard.validate_brief_integrity(session, brief_bear, mock_settings)
    assert risk_score >= 0.40
    assert any("Both USD and EUR labeled 'bearish'" in iss for iss in issues)


@pytest.mark.asyncio
async def test_brief_internal_consistency_aud(mock_settings):
    session = DummySession()

    # 1. Bullish AUD + Bullish USD
    brief_bull = {
        "currency_bias": {"USD": "bullish", "AUD": "bullish"},
        "risk_sentiment": "mixed",
        "confidence": 0.8
    }
    is_safe, issues, risk_score = await BriefContaminationGuard.validate_brief_integrity(session, brief_bull, mock_settings)
    assert risk_score >= 0.25
    assert any("Both USD and AUD labeled 'bullish'" in iss for iss in issues)

    # 2. Bearish AUD + Bearish USD
    brief_bear = {
        "currency_bias": {"USD": "bearish", "AUD": "bearish"},
        "risk_sentiment": "mixed",
        "confidence": 0.8
    }
    is_safe, issues, risk_score = await BriefContaminationGuard.validate_brief_integrity(session, brief_bear, mock_settings)
    assert risk_score >= 0.25
    assert any("Both USD and AUD labeled 'bearish'" in iss for iss in issues)


@pytest.mark.asyncio
async def test_brief_internal_consistency_gbp(mock_settings):
    session = DummySession()

    # 1. Bullish GBP + Bullish USD
    brief_bull = {
        "currency_bias": {"USD": "bullish", "GBP": "bullish"},
        "risk_sentiment": "mixed",
        "confidence": 0.8
    }
    is_safe, issues, risk_score = await BriefContaminationGuard.validate_brief_integrity(session, brief_bull, mock_settings)
    assert risk_score >= 0.30
    assert any("Both USD and GBP labeled 'bullish'" in iss for iss in issues)

    # 2. Bearish GBP + Bearish USD
    brief_bear = {
        "currency_bias": {"USD": "bearish", "GBP": "bearish"},
        "risk_sentiment": "mixed",
        "confidence": 0.8
    }
    is_safe, issues, risk_score = await BriefContaminationGuard.validate_brief_integrity(session, brief_bear, mock_settings)
    assert risk_score >= 0.30
    assert any("Both USD and GBP labeled 'bearish'" in iss for iss in issues)


@pytest.mark.asyncio
async def test_brief_clean_consistency(mock_settings):
    session = DummySession()

    # Clean consistent macro brief
    brief_clean = {
        "currency_bias": {"USD": "bullish", "EUR": "bearish", "GBP": "bearish", "AUD": "bearish", "JPY": "neutral"},
        "risk_sentiment": "risk-off",
        "confidence": 0.85
    }
    is_safe, issues, risk_score = await BriefContaminationGuard.validate_brief_integrity(session, brief_clean, mock_settings)
    assert is_safe is True
    assert risk_score == 0.0
    assert len(issues) == 0

