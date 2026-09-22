"""
Pydantic Schemas for strongly-typed configuration validation (H6, M-3, M-4).
"""
from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Optional, Any, Union


class SubscriptableConfig(BaseModel, extra="allow"):
    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item) and getattr(self, item) is not None

    def get(self, item: str, default: Any = None) -> Any:
        val = getattr(self, item, default)
        return val if val is not None else default

    def keys(self) -> List[str]:
        return [k for k, v in self if v is not None]

    def values(self) -> List[Any]:
        return [v for k, v in self if v is not None]

    def items(self) -> List[tuple[str, Any]]:
        return [(k, v) for k, v in self if v is not None]


class RiskConfig(SubscriptableConfig):
    max_daily_drawdown_percent: Optional[float] = Field(default=3.0, ge=0.5, le=15.0)
    max_weekly_drawdown_percent: Optional[float] = Field(default=6.0, ge=1.0, le=25.0)
    max_concurrent_positions: Optional[int] = Field(default=5, ge=1, le=50)
    max_portfolio_heat_pct: Optional[float] = Field(default=4.0, ge=0.5, le=20.0)
    max_daily_trades: Optional[int] = Field(default=10, ge=1, le=100)
    post_loss_cooldown_minutes: Optional[int] = Field(default=120, ge=0, le=1440)
    post_sl_cooldown_hours: Optional[float] = Field(default=2.0, ge=0.0, le=72.0)
    consecutive_loss_pause_threshold: Optional[int] = Field(default=3, ge=1, le=20)
    max_consecutive_losses_per_symbol: Optional[int] = Field(default=3, ge=1, le=20)
    min_rr_ratio: Optional[float] = Field(default=1.3, ge=0.5, le=10.0)


class PaperTradingConfig(SubscriptableConfig):
    enabled: Optional[bool] = True
    initial_balance: Optional[float] = Field(default=10000.0, ge=1.0)
    streak_loss_policy: Optional[str] = Field(default="warn_and_scale", pattern="^(warn_and_scale|disabled|strict)$")
    pause_system_on_daily_sl_limit: Optional[bool] = False
    streak_risk_scale_factor: Optional[float] = Field(default=0.5, ge=0.1, le=1.0)
    suspension_hours: Optional[int] = Field(default=12, ge=1, le=168)
    tp_detection_method: Optional[str] = Field(default="close_price")
    realistic_sl_tp_conflict: Optional[str] = Field(default="sl_wins")
    max_paper_trade_holding_hours: Optional[float] = Field(default=48.0, ge=1.0)
    spread_realistic_multiplier: Optional[float] = Field(default=2.0, ge=0.0)
    spread_multipliers: Optional[Dict[str, float]] = None


class TaskRoleConfig(BaseModel, extra="allow"):
    primary: str
    fallback_1: Optional[str] = None
    fallback_2: Optional[str] = None
    fallback_3: Optional[str] = None
    fallback: Optional[Union[List[str], str]] = None
    fallbacks: Optional[List[str]] = None
    max_cost_per_call: Optional[float] = None
    max_tokens: Optional[int] = Field(default=8192, ge=256, le=131072)
    max_tool_turns: Optional[int] = Field(default=15, ge=1, le=100)
    temperature: Optional[float] = Field(default=0.0, ge=0.0, le=2.0)
    thinking: Optional[Any] = None


class LLMConfig(SubscriptableConfig):
    task_roles: Optional[Dict[str, TaskRoleConfig]] = None
    providers: Optional[Dict[str, Any]] = None
    model_catalog: Optional[Dict[str, Any]] = None
    credential_pool: Optional[Dict[str, Any]] = None


class SchedulerConfig(SubscriptableConfig):
    cycle_interval_hours: Optional[float] = Field(default=8.0, ge=0.1, le=72.0)
    news_check_minutes: Optional[int] = Field(default=5, ge=1, le=120)
    trigger_check_minutes: Optional[int] = Field(default=2, ge=1, le=60)


class ExecutionConfig(SubscriptableConfig):
    max_price_staleness_seconds: Optional[int] = Field(default=120, ge=5, le=3600)
    max_analysis_age_for_execute_minutes: Optional[int] = Field(default=30, ge=1, le=1440)
    max_analysis_age_hours: Optional[float] = Field(default=0.5, ge=0.1, le=72.0)
    max_brief_age_hours: Optional[float] = Field(default=12.0, ge=0.5, le=168.0)
    adapter_type: Optional[str] = "live"
    remote_gateway_url: Optional[str] = "http://127.0.0.1:8080"
    remote_gateway_token: Optional[str] = ""
    mt5_common_dir: Optional[str] = ""
    max_spread_multiplier: Optional[Dict[str, Any]] = None


class IndicatorsConfig(SubscriptableConfig):
    ma_periods: Optional[List[int]] = Field(default_factory=lambda: [20, 50, 200])
    rsi_period: Optional[int] = Field(default=14, ge=2, le=100)
    stochastic_k: Optional[int] = Field(default=14, ge=2, le=100)
    stochastic_d: Optional[int] = Field(default=3, ge=1, le=50)
    macd_fast: Optional[int] = Field(default=12, ge=1, le=100)
    macd_slow: Optional[int] = Field(default=26, ge=1, le=200)
    macd_signal: Optional[int] = Field(default=9, ge=1, le=100)
    bollinger_period: Optional[int] = Field(default=20, ge=2, le=100)
    bollinger_std: Optional[float] = Field(default=2.0, ge=0.5, le=5.0)
    swing_window: Optional[int] = Field(default=5, ge=1, le=50)
    sr_tolerance: Optional[float] = Field(default=0.002, ge=0.0001, le=0.05)
    sr_min_touches: Optional[int] = Field(default=2, ge=1, le=10)


class TradingConfig(SubscriptableConfig):
    cost_mode: Optional[str] = "standard"
    auto_execute: Optional[bool] = False
    auto_execute_min_confluence: Optional[int] = Field(default=7, ge=1, le=20)
    auto_execute_min_confidence: Optional[float] = Field(default=0.60, ge=0.0, le=1.0)
    auto_execute_active_hours_utc_start: Optional[int] = Field(default=6, ge=0, le=23)
    auto_execute_active_hours_utc_end: Optional[int] = Field(default=22, ge=0, le=23)
    min_reanalysis_minutes: Optional[int] = Field(default=30, ge=1, le=1440)
    min_paper_trades_before_live: Optional[int] = Field(default=50, ge=0, le=1000)
    min_paper_win_rate_pct: Optional[float] = Field(default=55.0, ge=0.0, le=100.0)
    asset_universe: Optional[List[str]] = None
    risk: Optional[RiskConfig] = None
    paper_trading: Optional[PaperTradingConfig] = None
    indicators: Optional[IndicatorsConfig] = None


class UIConfig(SubscriptableConfig):
    theme: Optional[str] = Field(default="retro_vintage")
    steer_mode: Optional[str] = Field(default="one-at-a-time")


class HarnessConfig(SubscriptableConfig):
    compaction_cooldown_seconds: Optional[float] = Field(default=120.0, ge=0.0)
    max_context_chars: Optional[int] = Field(default=100000, ge=1000)
    retain_recent_turns: Optional[int] = Field(default=2, ge=1)


class EvalsConfig(SubscriptableConfig):
    simulation_clock_enabled: Optional[bool] = True


class BenchmarkConfig(SubscriptableConfig):
    max_drift_pct: Optional[float] = Field(default=15.0, ge=0.0)


class TradingAgentConfig(SubscriptableConfig):
    app_name: Optional[str] = None
    environment: Optional[str] = None
    trading: Optional[TradingConfig] = None
    risk: Optional[RiskConfig] = None
    paper_trading: Optional[PaperTradingConfig] = None
    execution: Optional[ExecutionConfig] = None
    indicators: Optional[IndicatorsConfig] = None
    llm: Optional[LLMConfig] = None
    scheduler: Optional[SchedulerConfig] = None
    ui: Optional[UIConfig] = None
    harness: Optional[HarnessConfig] = None
    evals: Optional[EvalsConfig] = None
    benchmark: Optional[BenchmarkConfig] = None

    @model_validator(mode="after")
    def validate_all_sections(self) -> "TradingAgentConfig":
        if self.trading:
            if self.trading.risk:
                RiskConfig.model_validate(self.trading.risk)
            if self.trading.paper_trading:
                PaperTradingConfig.model_validate(self.trading.paper_trading)
            if self.trading.indicators:
                IndicatorsConfig.model_validate(self.trading.indicators)
        if self.risk:
            RiskConfig.model_validate(self.risk)
        if self.paper_trading:
            PaperTradingConfig.model_validate(self.paper_trading)
        if self.execution:
            ExecutionConfig.model_validate(self.execution)
        if self.indicators:
            IndicatorsConfig.model_validate(self.indicators)
        if self.harness:
            HarnessConfig.model_validate(self.harness)
        if self.evals:
            EvalsConfig.model_validate(self.evals)
        if self.benchmark:
            BenchmarkConfig.model_validate(self.benchmark)
        return self

