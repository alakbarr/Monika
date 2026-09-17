import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { api } from '../../lib/api';
import { useDashboardStore } from '../../store/dashboardStore';
import {
  Shield,
  Clock,
  Cpu,
  Save,
  RotateCcw,
  AlertCircle,
  CheckCircle2,
  FileCode,
  ChevronRight,
  TrendingUp,
  FileText,
} from 'lucide-react';
import { ConfigDiffModal, type DiffItem } from './config/ConfigDiffModal';
import { ConfigSection, type ConfigSectionType } from './config/ConfigSection';

export const ConfigEditorPanel: React.FC = () => {
  const { userRole, fetchUserRole } = useDashboardStore();
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [activeSection, setActiveSection] = useState<ConfigSectionType>('risk');
  const [rawViewMode, setRawViewMode] = useState<'yaml' | 'schema'>('yaml');
  const [initialConfig, setInitialConfig] = useState<Record<string, unknown>>({});
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [rawYaml, setRawYaml] = useState<string>('');
  const [initialRawYaml, setInitialRawYaml] = useState<string>('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
  const [showDiffModal, setShowDiffModal] = useState<boolean>(false);

  const isAdmin = userRole === 'admin';

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setFeedback(null);
    try {
      await fetchUserRole();
      const [res, schemaRes] = await Promise.all([
        api.configSettings(),
        api.configSchema().catch(() => null),
      ]);
      const loaded = res.settings || {};
      setConfig(JSON.parse(JSON.stringify(loaded)));
      setInitialConfig(JSON.parse(JSON.stringify(loaded)));
      setRawYaml(res.raw_yaml || '');
      setInitialRawYaml(res.raw_yaml || '');
      if (schemaRes) setSchema(schemaRes);
    } catch (err) {
      setFeedback({ type: 'error', message: `Failed to load config: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setLoading(false);
    }
  }, [fetchUserRole]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // Check unsaved changes
  const hasChanges = useMemo(() => {
    if (activeSection === 'raw') {
      return rawYaml !== initialRawYaml;
    }
    return JSON.stringify(config) !== JSON.stringify(initialConfig);
  }, [activeSection, rawYaml, initialRawYaml, config, initialConfig]);

  // Unsaved changes beforeunload protection
  useEffect(() => {
    if (!hasChanges) return;
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasChanges]);

  // Compute key-by-key differences between initial and current config
  const diffItems = useMemo(() => {
    const diffs: DiffItem[] = [];
    const walk = (o1: any, o2: any, prefix = '') => {
      const keys = Array.from(new Set([...Object.keys(o1 || {}), ...Object.keys(o2 || {})]));
      for (const k of keys) {
        const p = prefix ? `${prefix}.${k}` : k;
        const v1 = o1?.[k];
        const v2 = o2?.[k];
        if (v1 === undefined && v2 !== undefined) {
          diffs.push({ path: p, oldVal: undefined, newVal: v2 });
        } else if (v1 !== undefined && v2 === undefined) {
          diffs.push({ path: p, oldVal: v1, newVal: undefined });
        } else if (
          typeof v1 === 'object' && v1 !== null &&
          typeof v2 === 'object' && v2 !== null &&
          !Array.isArray(v1) && !Array.isArray(v2)
        ) {
          walk(v1, v2, p);
        } else if (JSON.stringify(v1) !== JSON.stringify(v2)) {
          diffs.push({ path: p, oldVal: v1, newVal: v2 });
        }
      }
    };
    walk(initialConfig, config);
    return diffs;
  }, [initialConfig, config]);

  // Helper to get nested field value safely
  const getFieldValue = (path: string[], fallback: unknown = ''): unknown => {
    let curr: any = config;
    for (const key of path) {
      if (curr === undefined || curr === null) return fallback;
      curr = curr[key];
    }
    return curr !== undefined && curr !== null ? curr : fallback;
  };

  // Helper to mutate nested field in state immutably
  const updateField = (path: string[], val: unknown) => {
    setConfig((prev) => {
      const copy = JSON.parse(JSON.stringify(prev));
      let curr = copy;
      for (let i = 0; i < path.length - 1; i++) {
        const k = path[i];
        if (!curr[k] || typeof curr[k] !== 'object') curr[k] = {};
        curr = curr[k];
      }
      curr[path[path.length - 1]] = val;
      return copy;
    });
  };

  const handleReset = () => {
    setConfig(JSON.parse(JSON.stringify(initialConfig)));
    setRawYaml(initialRawYaml);
    setFeedback(null);
  };

  const handleSave = async () => {
    if (!isAdmin) {
      setFeedback({ type: 'error', message: 'Forbidden: Saving settings requires Admin privileges.' });
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      const payload = config;
      const res = await api.updateConfigSettings(payload, 'Updated via Dashboard Config Editor');
      setFeedback({
        type: 'success',
        message: `Success: Configuration persisted and backed up to ${res.backup_path || 'settings.yaml.bak'}. Hot-reloaded: ${res.reloaded ? 'YES' : 'NO'}.`,
      });
      setInitialConfig(JSON.parse(JSON.stringify(config)));
      setShowDiffModal(false);
      // Reload raw yaml from backend
      api.configSettings().then(r => {
        setRawYaml(r.raw_yaml || '');
        setInitialRawYaml(r.raw_yaml || '');
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: `Failed to save settings: ${err.message || String(err)}`,
      });
      setShowDiffModal(false);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <Skeleton height={80} />
        <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: '20px' }}>
          <Skeleton height={360} />
          <Skeleton height={500} />
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header Toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'var(--color-surface-card)',
        padding: '16px 20px',
        borderRadius: '2px',
        border: '1px solid var(--color-border)',
        flexWrap: 'wrap',
        gap: '12px',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: 'var(--color-text-white)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              System Configuration Manager
            </h2>
            <Badge variant={isAdmin ? 'profit' : 'neutral'} size="sm">
              ROLE: {userRole.toUpperCase()}
            </Badge>
            {hasChanges && (
              <Badge variant="warn" size="sm">
                UNSAVED CHANGES
              </Badge>
            )}
          </div>
          <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', margin: '4px 0 0 0', fontFamily: 'var(--font-precision)' }}>
            Real-time validation against TradingAgentConfig schema with automated backup (.bak) & hot-reload.
          </p>
        </div>

        {/* Global Toolbar Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={handleReset}
            disabled={!hasChanges || saving}
            className="typewriter-btn"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              background: 'transparent',
              border: '1px solid var(--color-border)',
              borderRadius: '2px',
              color: hasChanges ? 'var(--color-ink)' : 'var(--color-ink-muted)',
              cursor: hasChanges ? 'pointer' : 'not-allowed',
              fontSize: '11px',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              fontFamily: 'var(--font-precision)',
            }}
          >
            <RotateCcw size={12} />
            Reset Changes
          </button>

          <button
            onClick={() => setShowDiffModal(true)}
            disabled={!hasChanges || !isAdmin || saving}
            className="typewriter-btn"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              background: hasChanges && isAdmin ? 'var(--color-brass)' : 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '2px',
              color: hasChanges && isAdmin ? 'var(--color-paper-dark)' : 'var(--color-ink-muted)',
              fontWeight: 700,
              fontSize: '11px',
              cursor: hasChanges && isAdmin ? 'pointer' : 'not-allowed',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              fontFamily: 'var(--font-precision)',
            }}
          >
            <Save size={12} />
            {saving ? 'Saving...' : 'Review & Save'}
          </button>
        </div>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '12px 16px',
          borderRadius: '2px',
          border: `1px solid ${feedback.type === 'success' ? 'var(--color-profit)' : 'var(--color-loss)'}`,
          background: feedback.type === 'success' ? 'rgba(14,203,129,0.08)' : 'rgba(246,70,93,0.08)',
          color: feedback.type === 'success' ? 'var(--color-profit)' : 'var(--color-loss)',
          fontSize: '12px',
          fontFamily: 'var(--font-precision)',
        }}>
          {feedback.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Main Layout: Nav Sidebar + Form Body */}
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '16px', alignItems: 'start' }}>
        {/* Navigation Sidebar */}
        <Card className="ledger-card" padding="12px">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {[
              { id: 'risk', label: 'Risk Management', icon: Shield, desc: 'Drawdown, limits & sizing' },
              { id: 'symbols', label: 'Symbol Watchlist', icon: TrendingUp, desc: 'Monitored pairs & assets' },
              { id: 'llm', label: 'LLM Task Roles', icon: Cpu, desc: 'Model routing & fallbacks' },
              { id: 'scheduler', label: 'Scheduler Intervals', icon: Clock, desc: 'Cycle & news frequencies' },
              { id: 'paper', label: 'Paper Trading', icon: FileText, desc: 'Simulation guardrails' },
              { id: 'raw', label: 'Raw YAML Viewer', icon: FileCode, desc: 'Direct settings.yaml' },
            ].map((sec) => {
              const active = activeSection === sec.id;
              const Icon = sec.icon;
              return (
                <button
                  key={sec.id}
                  onClick={() => setActiveSection(sec.id as ConfigSectionType)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 12px',
                    borderRadius: '2px',
                    background: active ? 'var(--color-surface-card)' : 'transparent',
                    border: `1px solid ${active ? 'var(--color-brass)' : 'transparent'}`,
                    borderLeft: active ? '3px solid var(--color-brass)' : '1px solid transparent',
                    color: active ? 'var(--color-brass)' : 'var(--color-ink-muted)',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Icon size={16} />
                    <div>
                      <div style={{ fontWeight: active ? 700 : 500, fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{sec.label}</div>
                      <div style={{ fontSize: '10px', color: 'var(--color-ink-muted)', fontFamily: 'var(--font-precision)' }}>{sec.desc}</div>
                    </div>
                  </div>
                  <ChevronRight size={12} style={{ opacity: active ? 1 : 0.4 }} />
                </button>
              );
            })}
          </div>
        </Card>

        {/* Section Body Card */}
        <Card className="ledger-card" padding="20px">
          <ConfigSection
            activeSection={activeSection}
            isAdmin={isAdmin}
            getFieldValue={getFieldValue}
            updateField={updateField}
            rawViewMode={rawViewMode}
            setRawViewMode={setRawViewMode}
            rawYaml={rawYaml}
            schema={schema}
          />
        </Card>
      </div>

      {/* Confirmation Diff Modal */}
      <ConfigDiffModal
        isOpen={showDiffModal}
        onClose={() => setShowDiffModal(false)}
        onConfirm={handleSave}
        saving={saving}
        diffItems={diffItems}
        targetConfig={config}
      />
    </div>
  );
};
