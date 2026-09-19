import React from 'react';

export type ConfigSectionType = 'risk' | 'symbols' | 'llm' | 'scheduler' | 'paper' | 'raw';

const inputStyle = (enabled: boolean): React.CSSProperties => ({
  width: '100%',
  padding: '8px 12px',
  borderRadius: '2px',
  background: enabled ? 'var(--color-surface)' : 'var(--color-surface-card)',
  border: `1px solid ${enabled ? 'var(--color-border)' : 'var(--color-rule)'}`,
  color: enabled ? 'var(--color-ink)' : 'var(--color-ink-muted)',
  fontFamily: 'var(--font-precision)',
  fontSize: '12px',
  outline: 'none',
  cursor: enabled ? 'text' : 'not-allowed',
});

interface ConfigSectionProps {
  activeSection: ConfigSectionType;
  isAdmin: boolean;
  getFieldValue: (path: string[], fallback?: unknown) => unknown;
  updateField: (path: string[], val: unknown) => void;
  rawViewMode: 'yaml' | 'schema';
  setRawViewMode: (mode: 'yaml' | 'schema') => void;
  rawYaml: string;
  schema: Record<string, unknown> | null;
}

interface RiskParamConfig {
  key: string[];
  label: string;
  description: string;
  step: number;
  min: number;
  max: number;
  defaultVal: number;
  unit: string;
  rangeText: string;
  isInteger?: boolean;
}

const RISK_PARAMS: RiskParamConfig[] = [
  {
    key: ['trading', 'risk', 'max_daily_drawdown_percent'],
    label: 'Max Daily Drawdown',
    description: 'Intraday loss threshold halting autonomous execution for the session',
    step: 0.1,
    min: 0.5,
    max: 15.0,
    defaultVal: 3.0,
    unit: '%',
    rangeText: '0.5% – 15.0%',
  },
  {
    key: ['trading', 'risk', 'max_weekly_drawdown_percent'],
    label: 'Max Weekly Drawdown',
    description: 'Cumulative 5-day rolling capital defense ceiling before circuit break',
    step: 0.1,
    min: 1.0,
    max: 25.0,
    defaultVal: 6.0,
    unit: '%',
    rangeText: '1.0% – 25.0%',
  },
  {
    key: ['trading', 'risk', 'max_concurrent_positions'],
    label: 'Max Concurrent Positions',
    description: 'Ceiling on simultaneous open market tickets across all asset books',
    step: 1,
    min: 1,
    max: 50,
    defaultVal: 5,
    unit: 'POS',
    rangeText: '1 – 50',
    isInteger: true,
  },
  {
    key: ['trading', 'risk', 'max_portfolio_heat_pct'],
    label: 'Max Portfolio Heat',
    description: 'Maximum aggregate margin and open risk exposure across active pairs',
    step: 0.5,
    min: 0.5,
    max: 20.0,
    defaultVal: 4.0,
    unit: '%',
    rangeText: '0.5% – 20.0%',
  },
  {
    key: ['trading', 'risk', 'min_rr_ratio'],
    label: 'Minimum Risk-Reward Ratio',
    description: 'Required probabilistic reward-to-risk multiple to clear RiskGate',
    step: 0.1,
    min: 0.5,
    max: 10.0,
    defaultVal: 1.3,
    unit: 'R',
    rangeText: '0.5 – 10.0',
  },
  {
    key: ['trading', 'risk', 'consecutive_loss_pause_threshold'],
    label: 'Consecutive Loss Pause',
    description: 'Sequence of consecutive stopped trades triggering cooling suspension',
    step: 1,
    min: 1,
    max: 20,
    defaultVal: 3,
    unit: 'LOSSES',
    rangeText: '1 – 20',
    isInteger: true,
  },
];

interface SchedulerParamConfig {
  key: string[];
  label: string;
  description: string;
  step: number;
  min: number;
  max: number;
  defaultVal: number;
  unit: string;
  rangeText: string;
  isInteger?: boolean;
}

const SCHEDULER_PARAMS: SchedulerParamConfig[] = [
  {
    key: ['scheduler', 'cycle_interval_hours'],
    label: 'Cycle Interval',
    description: 'Cadence of full multi-asset LangGraph research and debate cycles',
    step: 0.5,
    min: 0.1,
    max: 72,
    defaultVal: 8.0,
    unit: 'HRS',
    rangeText: '0.1 – 72.0 hrs',
    isInteger: false,
  },
  {
    key: ['scheduler', 'news_check_minutes'],
    label: 'News Check Frequency',
    description: 'Polling interval for macroeconomic breaking news and alerts',
    step: 1,
    min: 1,
    max: 120,
    defaultVal: 5,
    unit: 'MIN',
    rangeText: '1 – 120 min',
    isInteger: true,
  },
  {
    key: ['scheduler', 'trigger_check_minutes'],
    label: 'Trigger Check Frequency',
    description: 'Evaluation cadence for pending price triggers and entry gates',
    step: 1,
    min: 1,
    max: 60,
    defaultVal: 2,
    unit: 'MIN',
    rangeText: '1 – 60 min',
    isInteger: true,
  },
];

export const ConfigSection: React.FC<ConfigSectionProps> = ({
  activeSection,
  isAdmin,
  getFieldValue,
  updateField,
  rawViewMode,
  setRawViewMode,
  rawYaml,
  schema,
}) => {
  return (
    <>
      {/* 1. Risk Management */}
      {activeSection === 'risk' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, color: 'var(--color-ink)', margin: '0 0 6px 0', letterSpacing: '0.02em' }}>
              Risk Parameters (settings.yaml: trading.risk)
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--color-ink-muted)', margin: 0 }}>
              Hard quantitative guardrails enforced by RiskGate before order authorization and trigger execution.
            </p>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '16px',
            }}
          >
            {RISK_PARAMS.map((param) => {
              const rawVal = getFieldValue(param.key, param.defaultVal);
              const val = Number(rawVal);
              return (
                <div
                  key={param.key.join('.')}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    padding: '14px 16px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: '2px',
                    gap: '12px',
                    boxShadow: 'var(--shadow-card)',
                  }}
                >
                  <div>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px',
                        marginBottom: '6px',
                      }}
                    >
                      <label
                        style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          color: 'var(--color-ink)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                          fontFamily: 'var(--font-precision)',
                        }}
                      >
                        {param.label}
                      </label>
                      <span
                        style={{
                          fontSize: '10px',
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 600,
                          color: 'var(--color-ink-muted)',
                          background: 'var(--color-desktop)',
                          padding: '2px 6px',
                          borderRadius: '2px',
                          border: '1px solid var(--color-rule)',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {param.rangeText}
                      </span>
                    </div>
                    <p
                      style={{
                        fontSize: '11px',
                        color: 'var(--color-ink-muted)',
                        margin: 0,
                        lineHeight: 1.4,
                      }}
                    >
                      {param.description}
                    </p>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      marginTop: 'auto',
                    }}
                  >
                    <input
                      type="number"
                      step={param.step}
                      min={param.min}
                      max={param.max}
                      disabled={!isAdmin}
                      value={isNaN(val) ? param.defaultVal : val}
                      onChange={(e) => {
                        const parsed = param.isInteger ? parseInt(e.target.value, 10) : parseFloat(e.target.value);
                        updateField(param.key, isNaN(parsed) ? param.defaultVal : parsed);
                      }}
                      style={{
                        width: '120px',
                        height: '32px',
                        padding: '4px 10px',
                        borderRadius: '2px',
                        background: isAdmin ? 'var(--color-paper)' : 'var(--color-paper-raised)',
                        border: '1px solid var(--color-rule)',
                        color: isAdmin ? 'var(--color-ink)' : 'var(--color-ink-muted)',
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '13px',
                        fontWeight: 600,
                        textAlign: 'right',
                        fontVariantNumeric: 'tabular-nums',
                        outline: 'none',
                        boxSizing: 'border-box',
                        cursor: isAdmin ? 'text' : 'not-allowed',
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        height: '32px',
                        minWidth: '46px',
                        padding: '0 8px',
                        boxSizing: 'border-box',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: 'var(--color-desktop)',
                        border: '1px solid var(--color-rule)',
                        borderRadius: '2px',
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '11px',
                        fontWeight: 700,
                        color: 'var(--color-brass)',
                        letterSpacing: '0.04em',
                        userSelect: 'none',
                        flexShrink: 0,
                      }}
                    >
                      {param.unit}
                    </span>
                    <span
                      style={{
                        fontSize: '10px',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--color-ink-muted)',
                        marginLeft: 'auto',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      def: {param.defaultVal}{param.unit === '%' ? '%' : ''}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 2. Symbols */}
      {activeSection === 'symbols' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: '16px' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--color-text-white)', margin: '0 0 6px 0' }}>
              Symbol Watchlist & Targets
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', margin: 0 }}>
              Active instruments evaluated in multi-asset LangGraph cycles.
            </p>
          </div>

          {(() => {
            const syms = (getFieldValue(['trading', 'asset_universe'], ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']) as string[]) || [];
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                  {syms.map((s, idx) => (
                    <div
                      key={s + idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        padding: '8px 14px',
                        background: 'rgba(255,255,255,0.06)',
                        border: '1px solid var(--color-border)',
                        borderRadius: 'var(--radius-pill)',
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 700,
                        color: 'var(--color-text-white)',
                      }}
                    >
                      <span>{s}</span>
                    </div>
                  ))}
                </div>
                <p style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                  Symbol modifications are synchronized across the Stage 1 Macro and Stage 2 Per-Asset nodes.
                </p>
              </div>
            );
          })()}
        </div>
      )}

      {/* 3. LLM Task Roles */}
      {activeSection === 'llm' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: '16px' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--color-text-white)', margin: '0 0 6px 0' }}>
              LLM Task Role Routing (settings.yaml: llm.task_roles)
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', margin: 0 }}>
              30+ specialized roles mapped to primary providers with automated fallback ladders.
            </p>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border)', textAlign: 'left' }}>
                  <th style={{ padding: '10px', color: 'var(--color-text-muted)' }}>Role Name</th>
                  <th style={{ padding: '10px', color: 'var(--color-text-muted)' }}>Primary Model</th>
                  <th style={{ padding: '10px', color: 'var(--color-text-muted)' }}>Fallback 1</th>
                  <th style={{ padding: '10px', color: 'var(--color-text-muted)' }}>Temperature</th>
                  <th style={{ padding: '10px', color: 'var(--color-text-muted)' }}>Max Tokens</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries((getFieldValue(['llm', 'task_roles'], {}) as Record<string, Record<string, unknown>>)).map(([roleName, roleCfg]) => (
                  <tr key={roleName} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '10px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--color-primary)' }}>
                      {roleName}
                    </td>
                    <td style={{ padding: '10px', color: 'var(--color-text-white)' }}>
                      {String(roleCfg.primary || '-')}
                    </td>
                    <td style={{ padding: '10px', color: 'var(--color-text-secondary)' }}>
                      {String(roleCfg.fallback_1 || '-')}
                    </td>
                    <td style={{ padding: '10px', fontFamily: 'var(--font-mono)' }}>
                      {String(roleCfg.temperature ?? 0.0)}
                    </td>
                    <td style={{ padding: '10px', fontFamily: 'var(--font-mono)' }}>
                      {String(roleCfg.max_tokens ?? 8192)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 4. Scheduler */}
      {activeSection === 'scheduler' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: '16px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, color: 'var(--color-ink)', margin: '0 0 6px 0', letterSpacing: '0.02em' }}>
              Scheduler & Background Tasks (settings.yaml: scheduler)
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--color-ink-muted)', margin: 0 }}>
              Execution frequency for graph analysis cycles, news monitoring, and trigger evaluators.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
            {SCHEDULER_PARAMS.map((param) => {
              const rawVal = getFieldValue(param.key, param.defaultVal);
              const val = Number(rawVal);
              return (
                <div
                  key={param.key.join('.')}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    padding: '14px 16px',
                    background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: '2px',
                    gap: '12px',
                    boxShadow: 'var(--shadow-card)',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '6px' }}>
                      <label style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-ink)', textTransform: 'uppercase', letterSpacing: '0.04em', fontFamily: 'var(--font-precision)' }}>
                        {param.label}
                      </label>
                      <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--color-ink-muted)', background: 'var(--color-desktop)', padding: '2px 6px', borderRadius: '2px', border: '1px solid var(--color-rule)', whiteSpace: 'nowrap' }}>
                        {param.rangeText}
                      </span>
                    </div>
                    <p style={{ fontSize: '11px', color: 'var(--color-ink-muted)', margin: 0, lineHeight: 1.4 }}>
                      {param.description}
                    </p>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: 'auto' }}>
                    <input
                      type="number"
                      step={param.step}
                      min={param.min}
                      max={param.max}
                      disabled={!isAdmin}
                      value={isNaN(val) ? param.defaultVal : val}
                      onChange={(e) => {
                        const parsed = param.isInteger ? parseInt(e.target.value, 10) : parseFloat(e.target.value);
                        updateField(param.key, isNaN(parsed) ? param.defaultVal : parsed);
                      }}
                      style={{
                        width: '120px',
                        height: '32px',
                        padding: '4px 10px',
                        borderRadius: '2px',
                        background: isAdmin ? 'var(--color-paper)' : 'var(--color-paper-raised)',
                        border: '1px solid var(--color-rule)',
                        color: isAdmin ? 'var(--color-ink)' : 'var(--color-ink-muted)',
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '13px',
                        fontWeight: 600,
                        textAlign: 'right',
                        fontVariantNumeric: 'tabular-nums',
                        outline: 'none',
                        boxSizing: 'border-box',
                        cursor: isAdmin ? 'text' : 'not-allowed',
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        height: '32px',
                        minWidth: '46px',
                        padding: '0 8px',
                        boxSizing: 'border-box',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: 'var(--color-desktop)',
                        border: '1px solid var(--color-rule)',
                        borderRadius: '2px',
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '11px',
                        fontWeight: 700,
                        color: 'var(--color-brass)',
                        letterSpacing: '0.04em',
                        userSelect: 'none',
                        flexShrink: 0,
                      }}
                    >
                      {param.unit}
                    </span>
                    <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--color-ink-muted)', marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                      def: {param.defaultVal} {param.unit}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 5. Paper Trading */}
      {activeSection === 'paper' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: '16px' }}>
            <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--color-text-white)', margin: '0 0 6px 0' }}>
              Paper Trading Policy
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', margin: 0 }}>
              Controls synthetic forward testing and edge metrics accumulation.
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <input
                type="checkbox"
                id="paper_enabled"
                disabled={!isAdmin}
                checked={Boolean(getFieldValue(['trading', 'paper_trading', 'enabled'], true))}
                onChange={(e) => updateField(['trading', 'paper_trading', 'enabled'], e.target.checked)}
                style={{ width: 18, height: 18, accentColor: 'var(--color-primary)' }}
              />
              <label htmlFor="paper_enabled" style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-white)', cursor: 'pointer' }}>
                Enable Paper Trading (Mandatory Safety Layer)
              </label>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '300px' }}>
              <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>
                Streak Loss Policy
              </label>
              <select
                disabled={!isAdmin}
                value={String(getFieldValue(['trading', 'paper_trading', 'streak_loss_policy'], 'warn_and_scale'))}
                onChange={(e) => updateField(['trading', 'paper_trading', 'streak_loss_policy'], e.target.value)}
                style={{
                  ...inputStyle(isAdmin),
                  cursor: 'pointer',
                }}
              >
                <option value="warn_and_scale">warn_and_scale</option>
                <option value="strict">strict</option>
                <option value="disabled">disabled</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* 6. Raw YAML / Schema Viewer */}
      {activeSection === 'raw' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <h3 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--color-text-white)', margin: '0 0 6px 0' }}>
                {rawViewMode === 'yaml' ? 'settings.yaml (Raw Text)' : 'TradingAgentConfig (JSON Schema)'}
              </h3>
              <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', margin: 0 }}>
                {rawViewMode === 'yaml'
                  ? 'Direct read-only inspection of the active configuration file.'
                  : 'Pydantic JSON schema used for runtime validation and form constraints.'}
              </p>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => setRawViewMode('yaml')}
                style={{
                  padding: '6px 14px',
                  borderRadius: 'var(--radius-pill)',
                  border: '1px solid var(--color-border)',
                  background: rawViewMode === 'yaml' ? 'var(--color-primary)' : 'rgba(255,255,255,0.04)',
                  color: rawViewMode === 'yaml' ? '#000' : 'var(--color-text-secondary)',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Raw YAML
              </button>
              <button
                onClick={() => setRawViewMode('schema')}
                style={{
                  padding: '6px 14px',
                  borderRadius: 'var(--radius-pill)',
                  border: '1px solid var(--color-border)',
                  background: rawViewMode === 'schema' ? 'var(--color-primary)' : 'rgba(255,255,255,0.04)',
                  color: rawViewMode === 'schema' ? '#000' : 'var(--color-text-secondary)',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                JSON Schema
              </button>
            </div>
          </div>

          <textarea
            readOnly
            value={rawViewMode === 'yaml' ? rawYaml : JSON.stringify(schema || {}, null, 2)}
            rows={24}
            style={{
              width: '100%',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '2px',
              color: 'var(--color-ink)',
              fontFamily: 'var(--font-precision)',
              fontSize: '12px',
              lineHeight: 1.5,
              padding: '14px',
              outline: 'none',
              resize: 'vertical',
            }}
          />
        </div>
      )}
    </>
  );
};
