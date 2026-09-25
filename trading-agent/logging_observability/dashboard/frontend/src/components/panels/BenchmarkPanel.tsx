import React, { useState, useEffect } from 'react';
import { api } from '../../lib/api';
import { sounds } from '../../lib/soundEffects';
import { StatusIndicator } from '../ui/StatusIndicator';
import { TypewriterButton } from '../ui/TypewriterButton';
import { EmptyState } from '../ui/EmptyState';

export const BenchmarkPanel: React.FC = () => {
  const [tasks, setTasks] = useState<any[]>([]);
  const [modelConfig, setModelConfig] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [runDetail, setRunDetail] = useState<any>(null);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Form state
  const [selectedTier, setSelectedTier] = useState<string>('');
  const [useFixtures, setUseFixtures] = useState(true);
  const [compareRouters, setCompareRouters] = useState(false);
  const [concurrency, setConcurrency] = useState(4);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  useEffect(() => {
    loadMetadata();
    loadRuns();
    loadLeaderboard();
  }, []);

  const loadMetadata = async () => {
    try {
      const [tRes, mRes] = await Promise.all([
        api.benchmarkTasks(),
        api.benchmarkModels(),
      ]);
      setTasks(tRes.tasks || []);
      setModelConfig(mRes || null);
    } catch (err: any) {
      console.error('Failed to load benchmark metadata', err);
    }
  };

  const loadRuns = async () => {
    try {
      const res = await api.benchmarkRuns(20, 0);
      setRuns(res.runs || []);
      if (res.runs && res.runs.length > 0 && !selectedRunId) {
        setSelectedRunId(res.runs[0].id);
        loadRunDetail(res.runs[0].id);
      }
    } catch (err) {
      console.error('Failed to load benchmark runs', err);
    }
  };

  const loadLeaderboard = async (runId?: number) => {
    try {
      const res = await api.benchmarkLeaderboard(runId);
      setLeaderboard(res.leaderboard || []);
    } catch (err) {
      console.error('Failed to load leaderboard', err);
    }
  };

  const loadRunDetail = async (runId: number) => {
    setLoading(true);
    try {
      const res = await api.benchmarkRunDetail(runId);
      setRunDetail(res);
      loadLeaderboard(runId);
    } catch (err) {
      console.error(`Failed to load run detail ${runId}`, err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunTrigger = async () => {
    setTriggering(true);
    sounds.playClick('typewriter');
    try {
      const req: any = {
        tier: selectedTier || undefined,
        use_fixtures: useFixtures,
        compare_routers: compareRouters,
        concurrency: concurrency,
      };
      const res = await api.benchmarkRunTrigger(req);
      setStatusMsg(res.message);
      sounds.playAlert();
      setTimeout(() => {
        loadRuns();
        setStatusMsg(null);
      }, 3000);
    } catch (err: any) {
      setStatusMsg(`Error: ${err.message}`);
    } finally {
      setTriggering(false);
    }
  };

  const filteredTasks = categoryFilter === 'all'
    ? tasks
    : tasks.filter((t) => t.category === categoryFilter);

  const categories = ['all', ...Array.from(new Set(tasks.map((t) => t.category)))];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* 1. Top Bar / Launch Controls */}
      <div
        className="win-window ledger-card"
        style={{
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
          padding: '16px 20px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 'var(--text-title-md)', fontFamily: 'var(--font-heading)', color: 'var(--color-ink)' }}>
              🧪 LLM Model Lab & Benchmark Suite
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-soft)' }}>
              Evaluasi komparatif akurasi reasoning, efisiensi token, dan latensi antar model provider & router.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <TypewriterButton
              variant="primary"
              onClick={handleRunTrigger}
              disabled={triggering}
            >
              {triggering ? '⚡ Dispatching...' : '▶ Run Evaluation Benchmark'}
            </TypewriterButton>
          </div>
        </div>

        {statusMsg && (
          <div
            style={{
              padding: '8px 14px',
              background: 'var(--color-accent-subtle)',
              border: '1px solid var(--color-rule)',
              borderRadius: '4px',
              marginBottom: '12px',
              fontSize: 'var(--text-body-sm)',
              fontWeight: 600,
            }}
          >
            {statusMsg}
          </div>
        )}

        {/* Tier Buttons and Controls */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
          <div>
            <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
              TARGET MODEL TIER
            </label>
            <select
              value={selectedTier}
              onChange={(e) => setSelectedTier(e.target.value)}
              style={{
                width: '100%',
                padding: '6px 10px',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '4px',
                background: 'var(--color-paper)',
                fontFamily: 'var(--font-precision)',
                fontSize: 'var(--text-body-sm)',
              }}
            >
              <option value="">Full Suite (All 45 Tasks & Models)</option>
              <option value="system_one">⚡ System One Fast Deciders (&lt;100ms)</option>
              <option value="cheap_efficient">💰 Cheap &amp; Token-Efficient (&lt;$0.001)</option>
              <option value="cheap_smart">🧠 Smart Balanced ($0.001 - $0.01)</option>
              <option value="high_intelligence">👑 Frontier High-Intelligence</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
              DATA SOURCE FIXTURE
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', height: '34px' }}>
              <input
                type="checkbox"
                checked={useFixtures}
                onChange={(e) => setUseFixtures(e.target.checked)}
              />
              <span style={{ fontSize: 'var(--text-body-sm)' }}>
                Synthetic Sept 2026 Fixtures ($106 Brent, Fed 3.75-4.00%)
              </span>
            </label>
          </div>

          <div>
            <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
              ROUTER COMPARISON
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', height: '34px' }}>
              <input
                type="checkbox"
                checked={compareRouters}
                onChange={(e) => setCompareRouters(e.target.checked)}
              />
              <span style={{ fontSize: 'var(--text-body-sm)' }}>
                Compare Direct vs OpenRouter vs 9router
              </span>
            </label>
          </div>

          <div>
            <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', display: 'block', marginBottom: '4px' }}>
              CONCURRENCY
            </label>
            <input
              type="number"
              min={1}
              max={16}
              value={concurrency}
              onChange={(e) => setConcurrency(parseInt(e.target.value) || 4)}
              style={{
                width: '100%',
                padding: '6px 10px',
                border: '1.5px solid var(--color-rule)',
                borderRadius: '4px',
                background: 'var(--color-paper)',
                fontFamily: 'var(--font-precision)',
                fontSize: 'var(--text-body-sm)',
              }}
            />
          </div>
        </div>
      </div>

      {/* 2. Main Split View: Leaderboard & Runs vs Task Explorer */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '16px' }}>
        {/* Left Column: Leaderboard & Run Details */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Leaderboard Table */}
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '2px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar win-titlebar--moss"
              style={{
                padding: '6px 12px',
                borderBottom: '2px solid var(--color-rule)',
                display: 'flex',
                justifyContent: 'space-between',
                fontWeight: 'bold',
              }}
            >
              <span>Model Leaderboard &amp; Cost-Quality Quadrant (Run #{selectedRunId || 'Latest'})</span>
              <span style={{ fontSize: 'var(--text-xs)' }}>{leaderboard.length} Candidates Evaluated</span>
            </div>

            {leaderboard.length === 0 ? (
              <EmptyState title="No Evaluation Data" description="Jalankan benchmark pertama untuk melihat peringkat model." />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-body-sm)', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ background: 'var(--color-table-header)', borderBottom: '1.5px solid var(--color-rule)' }}>
                      <th style={{ padding: '8px 12px' }}>Rank</th>
                      <th style={{ padding: '8px 12px' }}>Model</th>
                      <th style={{ padding: '8px 12px' }}>Score</th>
                      <th style={{ padding: '8px 12px' }}>Pass Rate</th>
                      <th style={{ padding: '8px 12px' }}>Avg Latency</th>
                      <th style={{ padding: '8px 12px' }}>Avg Cost</th>
                      <th style={{ padding: '8px 12px' }}>Tasks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.map((row, idx) => (
                      <tr key={row.model_name} style={{ borderBottom: '1px solid var(--color-rule-soft)' }}>
                        <td style={{ padding: '8px 12px', fontWeight: 'bold' }}>#{idx + 1}</td>
                        <td style={{ padding: '8px 12px', fontFamily: 'var(--font-precision)', fontWeight: 600 }}>
                          {row.model_name}
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <span
                            style={{
                              padding: '2px 6px',
                              borderRadius: '4px',
                              fontWeight: 'bold',
                              background: row.avg_score >= 0.8 ? 'var(--color-moss-subtle)' : row.avg_score >= 0.5 ? 'var(--color-ochre-subtle)' : 'var(--color-coral-subtle)',
                            }}
                          >
                            {(row.avg_score * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td style={{ padding: '8px 12px' }}>{row.pass_rate_pct}%</td>
                        <td style={{ padding: '8px 12px' }}>{row.avg_latency_s}s</td>
                        <td style={{ padding: '8px 12px' }}>${row.avg_cost_usd.toFixed(4)}</td>
                        <td style={{ padding: '8px 12px' }}>{row.total_tasks}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Markdown Report / Individual Results */}
          {runDetail && runDetail.report_markdown && (
            <div
              className="win-window ledger-card"
              style={{
                background: 'var(--color-paper-raised)',
                border: '2px solid var(--color-rule)',
                borderRadius: 'var(--radius-card)',
                boxShadow: 'var(--shadow-card)',
                overflow: 'hidden',
              }}
            >
              <div
                className="win-titlebar win-titlebar--salmon"
                style={{
                  padding: '6px 12px',
                  borderBottom: '2px solid var(--color-rule)',
                  fontWeight: 'bold',
                }}
              >
                <span>Executive Benchmark Report (Run #{selectedRunId})</span>
              </div>
              <pre
                style={{
                  padding: '16px',
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'var(--font-precision)',
                  fontSize: 'var(--text-body-sm)',
                  maxHeight: '400px',
                  overflowY: 'auto',
                }}
              >
                {runDetail.report_markdown}
              </pre>
            </div>
          )}
        </div>

        {/* Right Column: Run History & Task Catalog */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Past Runs */}
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '2px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar"
              style={{
                padding: '6px 12px',
                borderBottom: '2px solid var(--color-rule)',
                fontWeight: 'bold',
              }}
            >
              <span>Evaluation Run History</span>
            </div>
            <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
              {runs.map((r) => (
                <div
                  key={r.id}
                  onClick={() => {
                    setSelectedRunId(r.id);
                    loadRunDetail(r.id);
                  }}
                  style={{
                    padding: '10px 14px',
                    borderBottom: '1px solid var(--color-rule-soft)',
                    cursor: 'pointer',
                    background: selectedRunId === r.id ? 'var(--color-paper-highlight)' : 'transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 'bold', fontSize: 'var(--text-body-sm)' }}>
                    <span>Run #{r.id}</span>
                    <StatusIndicator status={r.is_running ? 'running' : 'completed'} />
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
                    {r.tasks_count} tasks · {r.models_count} models
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                    {r.started_at ? new Date(r.started_at).toLocaleString() : '-'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 45 Task Catalog */}
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '2px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar"
              style={{
                padding: '6px 12px',
                borderBottom: '2px solid var(--color-rule)',
                fontWeight: 'bold',
                display: 'flex',
                justifyContent: 'space-between',
              }}
            >
              <span>LLM Tasks ({filteredTasks.length}/45)</span>
            </div>

            <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--color-rule-soft)' }}>
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                style={{
                  width: '100%',
                  padding: '4px 8px',
                  fontSize: 'var(--text-xs)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '4px',
                }}
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    Category: {c.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ maxHeight: '350px', overflowY: 'auto', padding: '6px' }}>
              {filteredTasks.map((t) => (
                <div
                  key={t.id}
                  style={{
                    padding: '8px 10px',
                    margin: '4px 0',
                    border: '1px solid var(--color-rule-soft)',
                    borderRadius: '4px',
                    background: 'var(--color-paper)',
                    fontSize: 'var(--text-xs)',
                  }}
                >
                  <div style={{ fontWeight: 'bold', color: 'var(--color-ink)', display: 'flex', justifyContent: 'space-between' }}>
                    <span>{t.id}</span>
                    <span
                      style={{
                        fontSize: '9px',
                        padding: '1px 4px',
                        borderRadius: '3px',
                        background: t.is_system_one ? 'var(--color-coral-subtle)' : 'var(--color-rule-soft)',
                        fontWeight: 'bold',
                      }}
                    >
                      {t.mode.toUpperCase()}
                    </span>
                  </div>
                  <div style={{ color: 'var(--color-ink-soft)', marginTop: '2px' }}>
                    Category: <strong>{t.category}</strong>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
