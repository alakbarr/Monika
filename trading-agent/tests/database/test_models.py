import pytest
from datetime import datetime, timezone
from database.models import (
    _utcnow, NewsItem, EconomicCalendar, TreasuryYield, InterestRate,
    FedWatchProbability, COTReport, VIXData, DXYData, PriceOHLCV,
    TechnicalIndicator, SwingPoint, SRZone, LiquidityZone, FVGZone,
    OrderBlock, StructureBreak, FundamentalBrief, AssetAnalysis,
    TradeTrigger, Position, OrderLog, RiskState, TelegramConversation,
    ActivityLog, SystemConfig, Trade, TradeOutcome, PaperTradeRecord,
    OrderStatus, Order, OrderEvent
)

def test_utcnow():
    dt = _utcnow()
    assert dt.tzinfo == timezone.utc

def test_model_instantiation():
    # Just verifying that the models can be instantiated without errors
    
    news = NewsItem(source="Test", title="Title", url="http")
    assert news.source == "Test"
    
    cal = EconomicCalendar(event_name="NFP", currency="USD", impact="high")
    assert cal.currency == "USD"
    
    ty = TreasuryYield(tenor="10Y_INFLATION", yield_percent=2.34, date=datetime(2026,8,21, tzinfo=timezone.utc))
    assert ty.tenor == "10Y_INFLATION"
    assert ty.yield_percent == 2.34

    ty_real = TreasuryYield(tenor="10Y_REAL", yield_percent=1.95, date=datetime(2026,8,21, tzinfo=timezone.utc))
    assert ty_real.tenor == "10Y_REAL"
    
    ir = InterestRate(bank="FED", rate_percent=5.5, effective_date=datetime(2024,1,1, tzinfo=timezone.utc))
    assert ir.bank == "FED"
    
    fwp = FedWatchProbability(meeting_date="2024", probabilities_json="{}")
    assert fwp.meeting_date == "2024"
    
    cot = COTReport(report_date=datetime(2024,1,1, tzinfo=timezone.utc), market_code="GOLD", 
                    dealer_long=1, dealer_short=1, asset_mgr_long=1, asset_mgr_short=1, 
                    leveraged_long=1, leveraged_short=1)
    assert cot.market_code == "GOLD"
    
    vix = VIXData(date=datetime(2024,1,1, tzinfo=timezone.utc), close=15.0)
    assert vix.close == 15.0
    
    dxy = DXYData(date=datetime(2024,1,1, tzinfo=timezone.utc), close=100.0)
    assert dxy.close == 100.0
    
    ohlcv = PriceOHLCV(symbol="EURUSD", timeframe="H1", timestamp=datetime(2024,1,1, tzinfo=timezone.utc),
                       open=1.1, high=1.2, low=1.0, close=1.15, volume=100)
    assert ohlcv.symbol == "EURUSD"
    
    ti = TechnicalIndicator(symbol="XAUUSD", timeframe="H4", timestamp=datetime(2024,1,1, tzinfo=timezone.utc),
                            indicator_name="RSI", value_json="60")
    assert ti.indicator_name == "RSI"
    
    sp = SwingPoint(symbol="BTCUSD", timeframe="D1", timestamp=datetime(2024,1,1, tzinfo=timezone.utc),
                    type="high", price=50000)
    assert sp.type == "high"
    
    sr = SRZone(symbol="EURUSD", timeframe="H1", price_high=1.1, price_low=1.0, strength=3)
    assert sr.strength == 3
    
    lz = LiquidityZone(symbol="EURUSD", timeframe="H1", zone_high=1.2, zone_low=1.1, type="above_swing_high")
    assert lz.type == "above_swing_high"
    
    fvg = FVGZone(symbol="EURUSD", timeframe="H1", gap_high=1.1, gap_low=1.0, direction="bullish",
                  formed_at=datetime(2024,1,1, tzinfo=timezone.utc))
    assert fvg.direction == "bullish"
    
    ob = OrderBlock(symbol="EURUSD", timeframe="H1", direction="bullish", price_high=1.1, price_low=1.0,
                    formed_at=datetime(2024,1,1, tzinfo=timezone.utc))
    assert ob.direction == "bullish"
    
    sb = StructureBreak(symbol="EURUSD", timeframe="H1", type="BOS", direction="bullish", price=1.1,
                        formed_at=datetime(2024,1,1, tzinfo=timezone.utc))
    assert sb.type == "BOS"
    
    fb = FundamentalBrief(content_markdown="test")
    assert fb.content_markdown == "test"
    
    aa = AssetAnalysis(symbol="XAUUSD", decision="buy", confidence=0.8)
    assert aa.decision == "buy"
    
    tt = TradeTrigger(asset_analysis_id=1, trigger_type="price", condition_json="{}")
    assert tt.trigger_type == "price"
    
    pos = Position(symbol="XAUUSD", direction="buy", volume=1.0, entry_price=2000.0)
    assert pos.symbol == "XAUUSD"
    
    ol = OrderLog(action="place", symbol="XAUUSD", requested_by="claude")
    assert ol.action == "place"
    
    rs = RiskState(date=datetime(2024,1,1, tzinfo=timezone.utc))
    assert rs.date == datetime(2024,1,1, tzinfo=timezone.utc)
    
    tc = TelegramConversation(telegram_user_id="123", role="user", message="hi")
    assert tc.role == "user"
    
    al = ActivityLog(category="system", description="test", actor="system")
    assert al.actor == "system"
    assert al.related_id is None

    al_int = ActivityLog(category="system", description="test", actor="system", related_id=123)
    assert al_int.related_id == 123

    al_str_num = ActivityLog(category="system", description="test", actor="system", related_id="456")
    assert al_str_num.related_id == 456

    al_str_alpha = ActivityLog(category="strategy", description="test", actor="system", related_id="alpha_xauusd_b016b7")
    assert al_str_alpha.related_id is None
    
    sc = SystemConfig(key="test", value="123")
    assert sc.key == "test"
    
    t = Trade(symbol="XAUUSD", direction="BUY", entry_price=2000.0, volume=1.0, status="OPEN")
    assert t.direction == "BUY"

    to = TradeOutcome(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        exit_price=1.1050,
        pnl_usd=50.0,
        was_profitable=True,
        was_debate_modified=True,
        decision_source="llm_debate",
        exit_reason="tp_hit"
    )
    assert to.symbol == "EURUSD"
    assert to.was_debate_modified is True
    assert to.decision_source == "llm_debate"

    ptr = PaperTradeRecord(
        symbol="GBPUSD",
        direction="sell",
        entry_price=1.2500,
        stop_loss=1.2550,
        take_profit=1.2400,
        was_debate_modified=False,
        decision_source="llm_stage2",
        status="open"
    )
    assert ptr.symbol == "GBPUSD"
    assert ptr.was_debate_modified is False

    from database.models import (
        TokenUsageLog, NewsDigest, NewsDigestSlice, MarketChronicle,
        NewsClassificationOutcome, PrescreenLog, DecisionReflection,
        CandidateLesson, ConfluenceFactorOutcome, CyclePerformance,
        BacktestRun, BacktestTrade, DecisionMemory, MT5Signal
    )

    tul = TokenUsageLog(provider="anthropic", model_name="claude-3-5", task_name="stage2", thinking_tokens=150)
    assert tul.thinking_tokens == 150

    nd = NewsDigest(period_hours=6, digest_text="summary")
    assert nd.period_hours == 6

    nds = NewsDigestSlice(period_start=datetime(2026, 8, 29, tzinfo=timezone.utc), period_end=datetime(2026, 8, 29, 2, tzinfo=timezone.utc), period_hours=2.0)
    assert nds.period_hours == 2.0

    mc = MarketChronicle(event_date=datetime(2026, 8, 29, tzinfo=timezone.utc), category="policy_change", headline="Fed Cut")
    assert mc.category == "policy_change"

    nco = NewsClassificationOutcome(news_item_id=1, symbol_checked="EURUSD", classified_impact="HIGH")
    assert nco.classified_impact == "HIGH"

    psl = PrescreenLog(symbol="EURUSD", decision="skip", reason="Low ADX")
    assert psl.decision == "skip"

    drefl = DecisionReflection(
        analysis_id=1,
        symbol="EURUSD",
        decision="buy",
        confidence=0.8,
        context_cds_score=0.92,
        context_snapshot_id="snap_123",
        is_context_contaminated=False,
        contamination_reason=None
    )
    assert drefl.context_cds_score == 0.92

    cl = CandidateLesson(symbol="EURUSD", lesson_text="Wait for London open", status="shadow")
    assert cl.status == "shadow"

    cfo = ConfluenceFactorOutcome(symbol="EURUSD", factor_name="key_level_bounce", was_present=True)
    assert cfo.was_present is True

    cp = CyclePerformance(cycle_at=datetime(2026, 8, 29, tzinfo=timezone.utc), stage1_success=True)
    assert cp.stage1_success is True

    btr = BacktestRun(mode="full", start_date=datetime(2026, 1, 1, tzinfo=timezone.utc), end_date=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert btr.mode == "full"

    btt = BacktestTrade(run_id=1, symbol="EURUSD", direction="buy", entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc), entry_price=1.1, stop_loss=1.09, take_profit=1.12)
    assert btt.symbol == "EURUSD"

    dmb = DecisionMemory(symbol="EURUSD", decision_date=datetime(2026, 1, 1, tzinfo=timezone.utc), decision="buy")
    assert dmb.decision == "buy"

    sig = MT5Signal(asset_analysis_id=1, symbol="EURUSD", action="buy")
    assert sig.action == "buy"

    order = Order(
        id="ord_123",
        client_order_id="CLIENT_123",
        symbol="EURUSD",
        order_type="MARKET",
        direction="BUY",
        requested_price=1.1050,
        requested_volume=0.5,
        status=OrderStatus.PENDING_SUBMIT,
    )
    assert order.symbol == "EURUSD"
    assert order.status == OrderStatus.PENDING_SUBMIT
    assert order.status == "pending_submit"

    event = OrderEvent(
        order_id="ord_123",
        from_status=OrderStatus.PENDING_SUBMIT.value,
        to_status=OrderStatus.SUBMITTED.value,
        reason="Order submitted to broker",
    )
    assert event.from_status == "pending_submit"
    assert event.to_status == "submitted"
