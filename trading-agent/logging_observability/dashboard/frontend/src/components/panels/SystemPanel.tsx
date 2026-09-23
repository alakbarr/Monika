import React, { useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { StatusIndicator } from '../ui/StatusIndicator';
import { Badge } from '../ui/Badge';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';
import { api } from '../../lib/api';
import type { SSVPHealthMetrics } from '../../types/api';
import { Database, Terminal, Cpu, Activity, AlertTriangle, ShieldCheck } from 'lucide-react';

export const SystemPanel: React.FC = () => {
  const { health, geminiQuota, analysisQuality } = useDashboardStore();
  const [ssvpHealth, setSsvpHealth] = useState<SSVPHealthMetrics | null>(null);

  useEffect(() => {
    api.ssvpHealth().then(setSsvpHealth).catch(() => {});
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* System Health */}
      <Card header={
        <div style={{
          fontSize: 'var(--text-caption)',
          fontWeight: 'var(--weight-bold)',
          color: 'var(--color-ink-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          fontFamily: 'var(--font-precision)'
        }}>
          [ SYSTEM HEALTH & DIAGNOSTICS ]
        </div>
      }>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '12px', 
            background: 'var(--color-surface)', 
            padding: '16px', 
            borderRadius: '2px', 
            border: '1px solid var(--color-rule)' 
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Database size={16} color="var(--color-ink-muted)" />
              <StatusIndicator status={health?.db_connected ? 'connected' : 'disconnected'} label="PostgreSQL Database" size="md" />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Terminal size={16} color="var(--color-ink-muted)" />
              <StatusIndicator status={health?.mt5_connected ? 'connected' : 'disconnected'} label="MetaTrader 5 Terminal" size="md" />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Cpu size={16} color="var(--color-ink-muted)" />
              <StatusIndicator status={health?.gemini_api_available ? 'connected' : 'disconnected'} label="Gemini API" size="md" />
            </div>
          </div>

          {health?.data_freshness && (
            <div style={{ marginTop: '8px' }}>
              <div style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--color-ink-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: '12px',
                fontWeight: 'var(--weight-bold)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontFamily: 'var(--font-precision)'
              }}>
                <Activity size={14} />
                <span>[ DATA FRESHNESS ]</span>
                <div style={{ flex: 1, height: '1px', background: 'var(--color-rule)' }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {[
                  { label: 'News', value: health.data_freshness.news_hours_old, unit: 'h', limit: 6 },
                  { label: 'Calendar', value: health.data_freshness.calendar_hours_old, unit: 'h', limit: 8 },
                  { label: 'VIX', value: health.data_freshness.vix_days_old, unit: 'd', limit: 5 },
                  { label: 'COT', value: health.data_freshness.cot_days_old, unit: 'd', limit: 7 },
                ].map(({ label, value, unit, limit }) => {
                  const isOld = value !== null && value > limit;
                  const isWarn = value !== null && value > limit * 0.6 && !isOld;
                  const pct = value !== null ? Math.min(100, (value / limit) * 100) : 0;
                  
                  return (
                    <div key={label} style={{
                      display: 'grid',
                      gridTemplateColumns: '80px 1fr 40px',
                      alignItems: 'center',
                      gap: '12px',
                    }}>
                      <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-muted)', fontWeight: 'var(--weight-medium)', fontFamily: 'var(--font-precision)' }}>
                        {label}
                      </span>
                      <div style={{ height: '4px', background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: '2px', overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          width: `${pct}%`,
                          background: isOld ? 'var(--color-loss)' : isWarn ? 'var(--color-brass)' : 'var(--color-profit)',
                          borderRadius: '1px',
                        }} />
                      </div>
                      <span style={{
                        fontFamily: 'var(--font-precision)',
                        fontVariantNumeric: 'tabular-nums',
                        fontSize: 'var(--text-xs)',
                        fontWeight: 'var(--weight-bold)',
                        textAlign: 'right',
                        color: value === null
                          ? 'var(--color-ink-muted)'
                          : isOld
                          ? 'var(--color-loss)'
                          : isWarn
                          ? 'var(--color-brass)'
                          : 'var(--color-ink)',
                      }}>
                        {value !== null ? `${value}${unit}` : '—'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {health?.uptime_seconds && (
            <div style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--color-ink-muted)',
              marginTop: '12px',
              paddingTop: '12px',
              borderTop: '1px dashed var(--color-rule)',
              display: 'flex',
              justifyContent: 'space-between',
              fontFamily: 'var(--font-precision)'
            }}>
              <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>SYSTEM UPTIME</span>
              <span style={{ color: 'var(--color-ink)', fontVariantNumeric: 'tabular-nums', fontWeight: 'var(--weight-bold)' }}>
                {fmt.hours(health.uptime_seconds / 3600)}
              </span>
            </div>
          )}
        </div>
      </Card>

      {/* Gemini Quota */}
      {geminiQuota && (
        <Card header={
          <div style={{
            fontSize: 'var(--text-caption)',
            fontWeight: 'var(--weight-bold)',
            color: 'var(--color-ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            fontFamily: 'var(--font-precision)'
          }}>
            [ GEMINI API QUOTA (DAILY METRICS) ]
          </div>
        }>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {[
              { label: 'Flash', data: geminiQuota.flash },
              { label: 'Flash Lite', data: geminiQuota.flash_lite },
            ].map(({ label, data }) => (
              <div key={label}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: '8px',
                  alignItems: 'baseline'
                }}>
                  <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', fontWeight: 'var(--weight-bold)', fontFamily: 'var(--font-precision)' }}>
                    {label}
                  </span>
                  <span style={{
                    fontFamily: 'var(--font-precision)',
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: 'var(--text-xs)',
                    fontWeight: 'var(--weight-bold)',
                    color: data.pct_used >= 90
                      ? 'var(--color-loss)'
                      : data.pct_used >= 70
                      ? 'var(--color-brass)'
                      : 'var(--color-ink-muted)',
                  }}>
                    {data.used.toLocaleString()} / {data.max_rpd.toLocaleString()} <span style={{ opacity: 0.7 }}>({data.pct_used.toFixed(1)}%)</span>
                  </span>
                </div>
                <div style={{
                  height: '6px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '2px',
                  overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%',
                    width: `${Math.min(data.pct_used, 100)}%`,
                    background: data.pct_used >= 90
                      ? 'var(--color-loss)'
                      : data.pct_used >= 70
                      ? 'var(--color-brass)'
                      : 'var(--color-profit)',
                    borderRadius: '1px',
                  }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* API Cost & Analysis Quality */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px' }}>
        
        {health?.api_cost_ytd_usd !== undefined && (
          <Card style={{ 
            background: 'var(--color-surface)',
            border: '1px solid var(--color-brass)',
            borderRadius: '2px',
          }}>
            <div style={{
              fontSize: 'var(--text-caption)',
              fontWeight: 'var(--weight-bold)',
              color: 'var(--color-brass)',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
              marginBottom: '8px',
              fontFamily: 'var(--font-precision)'
            }}>
              [ API COST ACCUMULATION (YTD) ]
            </div>
            <div style={{
              fontSize: '30px',
              fontFamily: 'var(--font-precision)',
              fontVariantNumeric: 'tabular-nums',
              fontWeight: 'var(--weight-bold)',
              color: 'var(--color-ink)',
              lineHeight: 1
            }}>
              {fmt.usd(health.api_cost_ytd_usd)}
            </div>
          </Card>
        )}

        {/* Analysis Quality */}
        {analysisQuality && (
          <Card header={
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', width: '100%' }}>
              <div style={{
                fontSize: 'var(--text-caption)',
                fontWeight: 'var(--weight-bold)',
                color: 'var(--color-ink-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                fontFamily: 'var(--font-precision)'
              }}>
                [ ANALYSIS QUALITY METRICS (7D) ]
              </div>
              {analysisQuality.alert && (
                <AlertTriangle size={16} color="var(--color-brass)" />
              )}
            </div>
          }>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: '1fr 1fr', 
                gap: '12px',
                background: 'var(--color-surface)',
                padding: '16px',
                borderRadius: '2px',
                border: '1px solid var(--color-rule)'
              }}>
                {[
                  {
                    label: 'Compliance',
                    value: fmt.pct(analysisQuality.compliance_rate_pct),
                    color: analysisQuality.compliance_rate_pct >= 90
                      ? 'var(--color-profit)'
                      : 'var(--color-brass)',
                  },
                  {
                    label: 'Win Rate',
                    value: analysisQuality.win_rate_pct !== null
                      ? fmt.pct(analysisQuality.win_rate_pct)
                      : '—',
                    color: (analysisQuality.win_rate_pct ?? 0) >= 45
                      ? 'var(--color-profit)'
                      : 'var(--color-loss)',
                  },
                  {
                    label: 'Confluence',
                    value: analysisQuality.avg_confluence_score?.toFixed(1) ?? '—',
                    color: 'var(--color-ink)',
                  },
                  {
                    label: 'Priced-In',
                    value: analysisQuality.avg_priced_in_score?.toFixed(1) ?? '—',
                    color: 'var(--color-ink)',
                  }
                ].map(({ label, value, color }) => (
                  <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-precision)' }}>
                      {label}
                    </span>
                    <span style={{
                      fontFamily: 'var(--font-precision)',
                      fontVariantNumeric: 'tabular-nums',
                      fontWeight: 'var(--weight-bold)',
                      fontSize: 'var(--text-title-sm)',
                      color,
                    }}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* Score distribution */}
              <div>
                <div style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-ink-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: '8px',
                  fontWeight: 'var(--weight-bold)',
                  fontFamily: 'var(--font-precision)'
                }}>
                  [ CONFLUENCE TIER DISTRIBUTION ]
                </div>
                <div style={{ display: 'flex', gap: '2px', alignItems: 'center', height: '8px', borderRadius: '2px', overflow: 'hidden', border: '1px solid var(--color-rule)' }}>
                  {(['high', 'medium', 'low'] as const).map(tier => {
                    const dist = analysisQuality.confluence_score_distribution;
                    const total = dist.high + dist.medium + dist.low;
                    const pct = total > 0 ? (dist[tier] / total * 100) : 0;
                    const colors = {
                      high: 'var(--color-profit)',
                      medium: 'var(--color-brass)',
                      low: 'var(--color-loss)',
                    };
                    return (
                      <div
                        key={tier}
                        style={{ width: `${pct || 1}%`, height: '100%', background: colors[tier] }}
                        title={`${tier}: ${dist[tier]} (${pct.toFixed(0)}%)`}
                      />
                    );
                  })}
                </div>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-ink-muted)',
                  marginTop: '8px',
                  fontFamily: 'var(--font-precision)',
                  fontVariantNumeric: 'tabular-nums',
                  fontWeight: 'var(--weight-bold)'
                }}>
                  <span style={{ color: 'var(--color-profit)' }}>High: {analysisQuality.confluence_score_distribution.high}</span>
                  <span style={{ color: 'var(--color-brass)' }}>Med: {analysisQuality.confluence_score_distribution.medium}</span>
                  <span style={{ color: 'var(--color-loss)' }}>Low: {analysisQuality.confluence_score_distribution.low}</span>
                </div>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* SSVP / CDS Health Telemetry */}
      {ssvpHealth && (
        <Card header={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
            <div style={{
              fontSize: 'var(--text-caption)',
              fontWeight: 'var(--weight-bold)',
              color: 'var(--color-ink-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
              fontFamily: 'var(--font-precision)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <ShieldCheck size={16} color="var(--color-profit)" />
              <span>[ SSVP & CDS CALIBRATION TELEMETRY ]</span>
            </div>
            <Badge variant={ssvpHealth.status === 'healthy' ? 'profit' : 'warn'}>
              {ssvpHealth.status.toUpperCase()}
            </Badge>
          </div>
        }>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '12px',
              background: 'var(--color-surface)',
              padding: '16px',
              borderRadius: '2px',
              border: '1px solid var(--color-rule)'
            }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-precision)' }}>
                  CDS Predictive Signal
                </span>
                <span style={{
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 'var(--weight-bold)',
                  fontSize: 'var(--text-body)',
                  color: ssvpHealth.status === 'healthy' ? 'var(--color-profit)' : 'var(--color-brass)'
                }}>
                  {ssvpHealth.calibration?.result?.is_cds_predictive !== false ? 'VALID / PREDICTIVE' : 'CALIBRATION DRIFT'}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-precision)' }}>
                  CDS Threshold
                </span>
                <span style={{ fontFamily: 'var(--font-precision)', fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-body)', color: 'var(--color-ink)' }}>
                  {ssvpHealth.calibration?.calibrated_threshold ? `${ssvpHealth.calibration.calibrated_threshold.toFixed(2)}` : 'DEFAULT (60.0)'}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-precision)' }}>
                  Score Inflation
                </span>
                <span style={{
                  fontFamily: 'var(--font-precision)',
                  fontWeight: 'var(--weight-bold)',
                  fontSize: 'var(--text-body)',
                  color: ssvpHealth.inflation?.detected ? 'var(--color-loss)' : 'var(--color-profit)'
                }}>
                  {ssvpHealth.inflation?.detected ? 'INFLATION DETECTED' : 'NORMAL / UNBIASED'}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', textTransform: 'uppercase', fontFamily: 'var(--font-precision)' }}>
                  Telemetry Updated
                </span>
                <span style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)' }}>
                  {new Date(ssvpHealth.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};

