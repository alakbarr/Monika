"""
Pydantic Schemas for strongly-typed configuration validation (H6, M-3, M-4).
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, SecretStr, model_validator


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

    def keys(self) -> list[str]:
        return [k for k, v in self if v is not None]

    def values(self) -> list[Any]:
        return [v for k, v in self if v is not None]

    def items(self) -> list[tuple[str, Any]]:
        return [(k, v) for k, v in self if v is not None]


class RiskConfig(SubscriptableConfig):
    max_daily_drawdown_percent: float | None = Field(default=3.0, ge=0.5, le=15.0)
    max_weekly_drawdown_percent: float | None = Field(default=6.0, ge=1.0, le=25.0)
    max_concurrent_positions: int | None = Field(default=5, ge=1, le=50)
    max_portfolio_heat_pct: float | None = Field(default=4.0, ge=0.5, le=20.0)
    max_daily_trades: int | None = Field(default=10, ge=1, le=100)
    post_loss_cooldown_minutes: int | None = Field(default=120, ge=0, le=1440)
    post_sl_cooldown_hours: float | None = Field(default=2.0, ge=0.0, le=72.0)
    consecutive_loss_pause_threshold: int | None = Field(default=3, ge=1, le=20)
    max_consecutive_losses_per_symbol: int | None = Field(default=3, ge=1, le=20)
    min_rr_ratio: float | None = Field(default=1.3, ge=0.5, le=10.0)
    daily_drawdown_limit: float | None = Field(default=None, ge=0.5, le=15.0)


class PaperTradingConfig(SubscriptableConfig):
    enabled: bool | None = True
    initial_balance: float | None = Field(default=10000.0, ge=1.0)
    streak_loss_policy: str | None = Field(default="warn_and_scale", pattern="^(warn_and_scale|disabled|strict)$")
    pause_system_on_daily_sl_limit: bool | None = False
    streak_risk_scale_factor: float | None = Field(default=0.5, ge=0.1, le=1.0)
    suspension_hours: int | None = Field(default=12, ge=1, le=168)
    tp_detection_method: str | None = Field(default="close_price")
    realistic_sl_tp_conflict: str | None = Field(default="sl_wins")
    max_paper_trade_holding_hours: float | None = Field(default=48.0, ge=1.0)
    spread_realistic_multiplier: float | None = Field(default=2.0, ge=0.0)
    spread_multipliers: dict[str, float] | None = None


class TaskRoleConfig(BaseModel, extra="allow"):
    primary: str
    fallback_1: str | None = None
    fallback_2: str | None = None
    fallback_3: str | None = None
    fallback_4: str | None = None
    fallback_5: str | None = None
    fallback_6: str | None = None
    fallback_7: str | None = None
    fallback_8: str | None = None
    fallback: Union[list[str], str] | None = None
    fallbacks: list[str] | None = None
    max_cost_per_call: float | None = None
    max_tokens: int | None = Field(default=8192, ge=256, le=131072)
    max_tool_turns: int | None = Field(default=15, ge=1, le=100)
    temperature: float | None = Field(default=0.0, ge=0.0, le=2.0)
    thinking: Any | None = None


class LLMConfig(SubscriptableConfig):
    task_roles: dict[str, TaskRoleConfig] | None = None
    providers: dict[str, Any] | None = None
    model_catalog: dict[str, Any] | None = None
    credential_pool: dict[str, Any] | None = None
    per_turn_timeout_seconds: float | None = Field(default=90.0, ge=5.0, le=600.0)


class SchedulerConfig(SubscriptableConfig):
    cycle_interval_hours: float | None = Field(default=8.0, ge=0.1, le=72.0)
    news_check_minutes: int | None = Field(default=5, ge=1, le=120)
    trigger_check_minutes: int | None = Field(default=2, ge=1, le=60)
    cron_expression: str | None = Field(default=None)


class ExecutionConfig(SubscriptableConfig):
    max_price_staleness_seconds: int | None = Field(default=120, ge=5, le=3600)
    max_analysis_age_for_execute_minutes: int | None = Field(default=30, ge=1, le=1440)
    max_analysis_age_hours: float | None = Field(default=0.5, ge=0.1, le=72.0)
    max_brief_age_hours: float | None = Field(default=12.0, ge=0.5, le=168.0)
    adapter_type: str | None = "live"
    remote_gateway_url: str | None = "http://127.0.0.1:8080"
    remote_gateway_token: SecretStr | None = None
    mt5_common_dir: str | None = ""
    mt5_linux_host: str | None = "127.0.0.1"
    mt5_linux_port: int | None = Field(default=18812, ge=1024, le=65535)
    max_spread_multiplier: dict[str, Any] | None = None


class IndicatorsConfig(SubscriptableConfig):
    ma_periods: list[int] | None = Field(default_factory=lambda: [20, 50, 200])
    rsi_period: int | None = Field(default=14, ge=2, le=100)
    stochastic_k: int | None = Field(default=14, ge=2, le=100)
    stochastic_d: int | None = Field(default=3, ge=1, le=50)
    macd_fast: int | None = Field(default=12, ge=1, le=100)
    macd_slow: int | None = Field(default=26, ge=1, le=200)
    macd_signal: int | None = Field(default=9, ge=1, le=100)
    bollinger_period: int | None = Field(default=20, ge=2, le=100)
    bollinger_std: float | None = Field(default=2.0, ge=0.5, le=5.0)
    swing_window: int | None = Field(default=5, ge=1, le=50)
    sr_tolerance: float | None = Field(default=0.002, ge=0.0001, le=0.05)
    sr_min_touches: int | None = Field(default=2, ge=1, le=10)


class TradingConfig(SubscriptableConfig):
    cost_mode: str | None = "standard"
    auto_execute: bool | None = False
    auto_execute_min_confluence: int | None = Field(default=7, ge=1, le=20)
    auto_execute_min_confidence: float | None = Field(default=0.60, ge=0.0, le=1.0)
    auto_execute_active_hours_utc_start: int | None = Field(default=6, ge=0, le=23)
    auto_execute_active_hours_utc_end: int | None = Field(default=22, ge=0, le=23)
    min_reanalysis_minutes: int | None = Field(default=30, ge=1, le=1440)
    min_paper_trades_before_live: int | None = Field(default=50, ge=0, le=1000)
    min_paper_win_rate_pct: float | None = Field(default=55.0, ge=0.0, le=100.0)
    asset_universe: list[str] | None = None
    symbols: list[str] | None = None
    lot_size: float | None = Field(default=None, ge=0.01, le=100.0)
    risk: RiskConfig | None = None
    paper_trading: PaperTradingConfig | None = None
    indicators: IndicatorsConfig | None = None


class UIConfig(SubscriptableConfig):
    theme: str | None = Field(default="retro_vintage")
    steer_mode: str | None = Field(default="one-at-a-time")


class HarnessConfig(SubscriptableConfig):
    compaction_cooldown_seconds: float | None = Field(default=120.0, ge=0.0)
    max_context_chars: int | None = Field(default=100000, ge=1000)
    retain_recent_turns: int | None = Field(default=2, ge=1)


class EvalsConfig(SubscriptableConfig):
    simulation_clock_enabled: bool | None = True


class BenchmarkCandidateConfig(BaseModel, extra="allow"):
    id: str
    name: str
    provider: str
    model_id: str
    input_cost_per_m: float | None = 0.0
    output_cost_per_m: float | None = 0.0
    latency_sla_ms: float | None = None
    tier: str | None = "cheap_smart"
    enabled: bool | None = True
    tags: list[str] | None = Field(default_factory=list)


class BenchmarkTierConfig(BaseModel, extra="allow"):
    name: str
    description: str | None = ""
    target_tasks: list[str] | None = Field(default_factory=list)
    models: list[str] | None = Field(default_factory=list)


class BenchmarkConfig(SubscriptableConfig):
    max_drift_pct: float | None = Field(default=15.0, ge=0.0)
    default_judge_model: str | None = "anthropic:claude-3-5-sonnet-20241022"
    default_reference_model: str | None = "anthropic:claude-3-5-sonnet-20241022"
    default_symbol: str | None = "EURUSD"
    use_fixtures: bool | None = False
    candidates: list[BenchmarkCandidateConfig] | None = Field(default_factory=list)
    tiers: dict[str, BenchmarkTierConfig] | None = Field(default_factory=dict)
    router_matrix: dict[str, list[str]] | None = Field(default_factory=dict)


class SecurityConfig(SubscriptableConfig):
    quarantine_days: int | None = Field(default=30, ge=0, le=365)
    prompt_injection_threshold: float | None = Field(default=0.85, ge=0.0, le=1.0)
    ssrf_allowed_ports: list[int] | None = Field(default_factory=lambda: [80, 443])
    denial_breaker_threshold: int | None = Field(default=5, ge=1, le=50)
    audit_logging: bool | None = True


class DatabaseConfig(SubscriptableConfig):
    url: SecretStr | None = None
    echo: bool | None = False
    pool_size: int | None = Field(default=5, ge=1, le=100)
    max_overflow: int | None = Field(default=10, ge=0, le=100)
    backup: dict[str, Any] | None = Field(default_factory=dict)


class TelegramConfig(SubscriptableConfig):
    bot_token: SecretStr | None = None
    chat_id: str | None = None
    enabled: bool | None = False


class TradingAgentConfig(SubscriptableConfig):
    installation_tier: str | None = Field(default="trial", pattern="^(trial|full|unconfigured)$")
    app_name: str | None = None
    environment: str | None = None
    trading: TradingConfig | None = None
    risk: RiskConfig | None = None
    paper_trading: PaperTradingConfig | None = None
    execution: ExecutionConfig | None = None
    indicators: IndicatorsConfig | None = None
    llm: LLMConfig | None = None
    scheduler: SchedulerConfig | None = None
    ui: UIConfig | None = None
    harness: HarnessConfig | None = None
    evals: EvalsConfig | None = None
    benchmark: BenchmarkConfig | None = None
    security: SecurityConfig | None = None
    database: DatabaseConfig | None = None
    telegram: TelegramConfig | None = None
    plugins: dict[str, Any] | None = Field(default_factory=dict)
    learning: dict[str, Any] | None = Field(default_factory=dict)
    adversarial_check: dict[str, Any] | None = Field(default_factory=dict)
    confidence_calibration: dict[str, Any] | None = Field(default_factory=dict)
    data_quality: dict[str, Any] | None = Field(default_factory=dict)
    ssvp: dict[str, Any] | None = Field(default_factory=dict)
    news_classification_control: dict[str, Any] | None = Field(default_factory=dict)
    scraping: dict[str, Any] | None = Field(default_factory=dict)
    data_sources: dict[str, Any] | None = Field(default_factory=dict)
    notifications: dict[str, Any] | None = Field(default_factory=dict)
    claude: dict[str, Any] | None = Field(default_factory=dict)
    cost_tracking: dict[str, Any] | None = Field(default_factory=dict)
    data_retention_days: int | dict[str, Any] | None = None
    backtest: dict[str, Any] | None = Field(default_factory=dict)
    analysis: dict[str, Any] | None = Field(default_factory=dict)
    agent_architecture: dict[str, Any] | None = Field(default_factory=dict)
    search: dict[str, Any] | None = Field(default_factory=dict)
    pattern_similarity: dict[str, Any] | None = Field(default_factory=dict)
    scenario_tree: dict[str, Any] | None = Field(default_factory=dict)
    context_compaction: dict[str, Any] | None = Field(default_factory=dict)
    progressive_tools: dict[str, Any] | None = Field(default_factory=dict)
    gepa_evolution: dict[str, Any] | None = Field(default_factory=dict)
    verification_engine: dict[str, Any] | None = Field(default_factory=dict)
    alpha_discovery: dict[str, Any] | None = Field(default_factory=dict)
    strategy_synthesis: dict[str, Any] | None = Field(default_factory=dict)
    news_classification: dict[str, Any] | None = Field(default_factory=dict)
    workspace: dict[str, Any] | None = Field(default_factory=dict)
    mcp: dict[str, Any] | None = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_all_sections(self) -> TradingAgentConfig:
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
        if self.security:
            SecurityConfig.model_validate(self.security)
        if self.database:
            DatabaseConfig.model_validate(self.database)
        if self.telegram:
            TelegramConfig.model_validate(self.telegram)
        return self
