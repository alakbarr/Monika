import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../../lib/api';
import { sounds } from '../../lib/soundEffects';
import { StatusIndicator } from '../ui/StatusIndicator';
import { TypewriterButton } from '../ui/TypewriterButton';
import { EmptyState } from '../ui/EmptyState';

// Pre-curated model families for quick 1-click selection
const MODEL_FAMILIES: Record<string, string[]> = {
  'Google Gemini': [
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.5-flash',
    'gemini-3.1-pro-preview',
    'gemini-3.5-flash-lite',
  ],
  'OpenAI': [
    'gpt-sol-6.1',
    'gpt-6.1-sol',
    'gpt-sol-5.6',
    'gpt-5.6-sol',
    'gpt-5.6-terra',
    'gpt-5.6-luna',
    'gpt-4o',
  ],
  'Anthropic': [
    'claude-sonnet-5',
    'claude-opus-5',
    'claude-sonnet-4-6',
    'claude-haiku-4-5-20251001',
  ],
  'DeepSeek': [
    'deepseek-v4-pro',
    'deepseek-v4-flash',
    'deepseek-chat',
  ],
  'Groq / Fast': [
    'groq-compound',
    'groq-qwen3.8-27b',
    'groq-gpt-oss-120b',
  ],
  'Free Tier': [
    'ox-alpha',
    'z-ai/glm-5.2:free',
    'google/gemma-4-31b:free',
    'nvidia/nemotron-3-ultra:free',
  ],
};

const PROVIDER_ROUTERS = [
  { id: 'direct', label: 'Direct Provider', desc: 'Direct native API (Gemini/OpenAI/Anthropic)' },
  { id: 'openrouter', label: 'OpenRouter', desc: 'Proxy router via OpenRouter.ai' },
  { id: '9router', label: '9Router', desc: 'Low-latency proxy gateway' },
  { id: 'groq', label: 'Groq Cloud', desc: 'Ultra-fast LPU inference' },
];

export const BenchmarkPanel: React.FC = () => {
  // Navigation & View tabs
  const [activeTab, setActiveTab] = useState<'task_compare' | 'global_leaderboard' | 'run_history'>('task_compare');

  // Metadata
  const [tasks, setTasks] = useState<any[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [candidateList, setCandidateList] = useState<string[]>([]);

  // Wizard state (Step 1: Role, Step 2: Models, Step 3: Provider/Router)
  const [selectedTask, setSelectedTask] = useState<string>('stage1_fundamental');
  const [selectedCategory, setSelectedCategory] = useState<string>('macro');
  const [selectedModels, setSelectedModels] = useState<string[]>(['gemini-3.8-flash']);
  const [customModelInput, setCustomModelInput] = useState<string>('');
  const [selectedProvider, setSelectedProvider] = useState<string>('direct');
  const [useFixtures, setUseFixtures] = useState<boolean>(true);
  const [concurrency, setConcurrency] = useState<number>(4);

  // Execution state
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [liveProgress, setLiveProgress] = useState<{ activeModel?: string; completed: number; total: number } | null>(null);

  // Per-task comparisons
  const [taskComparisons, setTaskComparisons] = useState<any[]>([]);
  const [loadingComparisons, setLoadingComparisons] = useState<boolean>(false);
  const [viewDetailModal, setViewDetailModal] = useState<any | null>(null);

  // Global Leaderboard & Runs
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [runDetail, setRunDetail] = useState<any>(null);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [loadingRun, setLoadingRun] = useState<boolean>(false);

  const pollIntervalRef = useRef<any>(null);

  // Metadata loaders
  const loadMetadata = useCallback(async () => {
    try {
      const [tRes, mRes] = await Promise.all([
        api.benchmarkTasks(),
        api.benchmarkModels(),
      ]);
      setTasks(tRes.tasks || []);
      setCategories(tRes.categories || []);
      setCandidateList(mRes.candidates || []);
    } catch (err) {
      console.error('Failed to load benchmark metadata', err);
    }
  }, []);

  const loadLeaderboard = useCallback(async (runId?: number) => {
    try {
      const res = await api.benchmarkLeaderboard(runId);
      setLeaderboard(res.leaderboard || []);
    } catch (err) {
      console.error('Failed to load leaderboard', err);
    }
  }, []);

  const loadRunDetail = useCallback(async (runId: number) => {
    setLoadingRun(true);
    try {
      const res = await api.benchmarkRunDetail(runId);
      setRunDetail(res);
      loadLeaderboard(runId);
    } catch (err) {
      console.error(`Failed to load run detail ${runId}`, err);
    } finally {
      setLoadingRun(false);
    }
  }, [loadLeaderboard]);

  const loadRuns = useCallback(async () => {
    try {
      const res = await api.benchmarkRuns(20, 0);
      setRuns(res.runs || []);
      if (res.runs && res.runs.length > 0 && !selectedRunId) {
        setSelectedRunId(res.runs[0].id);
        loadRunDetail(res.runs[0].id);
      }
    } catch (err) {
      console.error('Failed to load runs', err);
    }
  }, [selectedRunId, loadRunDetail]);

  const loadTaskComparisons = useCallback(async (taskId: string) => {
    setLoadingComparisons(true);
    try {
      const res = await api.benchmarkCompare(taskId);
      setTaskComparisons(res.comparisons || []);
    } catch (err) {
      console.error(`Failed to load comparisons for ${taskId}`, err);
    } finally {
      setLoadingComparisons(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadMetadata();
    loadRuns();
    loadLeaderboard();
  }, [loadMetadata, loadRuns, loadLeaderboard]);

  // When selected task changes, reload comparisons
  useEffect(() => {
    if (selectedTask) {
      loadTaskComparisons(selectedTask);
    }
  }, [selectedTask, loadTaskComparisons]);

  // Model selection helpers
  const toggleModel = (model: string) => {
    sounds.playClick('typewriter');
    setSelectedModels((prev) =>
      prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model]
    );
  };

  const addCustomModel = () => {
    const trimmed = customModelInput.trim();
    if (trimmed && !selectedModels.includes(trimmed)) {
      setSelectedModels((prev) => [...prev, trimmed]);
      setCustomModelInput('');
    }
  };

  // Start benchmark run for the selected task and models
  const handleStartBenchmark = async () => {
    if (selectedModels.length === 0) {
      setStatusMsg('Pilih minimal 1 model untuk diuji.');
      return;
    }

    setIsExecuting(true);
    sounds.playClick('typewriter');
    setLiveProgress({ completed: 0, total: selectedModels.length, activeModel: selectedModels[0] });

    try {
      const req = {
        task_id: selectedTask,
        models: selectedModels,
        provider_route: selectedProvider,
        use_fixtures: useFixtures,
        concurrency: concurrency,
      };

      const res = await api.benchmarkRunTrigger(req);
      setStatusMsg(`⚡ ${res.message}`);
      sounds.playAlert();

      // Poll task comparisons to pick up results live
      let pollCount = 0;
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

      pollIntervalRef.current = setInterval(async () => {
        pollCount += 1;
        await loadTaskComparisons(selectedTask);

        if (pollCount >= 15) {
          clearInterval(pollIntervalRef.current);
          setIsExecuting(false);
          setLiveProgress(null);
          loadRuns();
        }
      }, 4000);
    } catch (err: any) {
      setStatusMsg(`Error: ${err.message}`);
      setIsExecuting(false);
      setLiveProgress(null);
    }
  };

  // Best performers calculation for summary cards
  const validComparisons = taskComparisons.filter((c) => !c.error && c.score !== null);
  const bestScoreModel = [...validComparisons].sort((a, b) => (b.score || 0) - (a.score || 0))[0];
  const fastestModel = [...validComparisons].sort((a, b) => (a.latency_s || 999) - (b.latency_s || 999))[0];
  const cheapestModel = [...validComparisons].sort((a, b) => (a.cost_usd_with_cache || 999) - (b.cost_usd_with_cache || 999))[0];

  const filteredTasksByCategory = selectedCategory === 'all'
    ? tasks
    : tasks.filter((t) => t.category === selectedCategory);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Header Card */}
      <div
        className="win-window ledger-card"
        style={{
          background: 'var(--color-paper-raised)',
          border: '1px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
          padding: '16px 20px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 'var(--text-title-md)', fontFamily: 'var(--font-heading)', color: 'var(--color-ink)' }}>
              🧪 LLM Role Benchmark &amp; Model Comparison Lab
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-soft)' }}>
              Uji model-model pilihanmu pada task_role spesifik secara nyata. Bandingkan skor kualitas, latensi, serta biaya dengan atau tanpa KV-cache hit.
            </p>
          </div>

          {/* Navigation View Tabs */}
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              onClick={() => setActiveTab('task_compare')}
              style={{
                padding: '6px 14px',
                borderRadius: '4px',
                fontSize: 'var(--text-body-sm)',
                fontWeight: 'bold',
                cursor: 'pointer',
                border: '1px solid var(--color-rule)',
                background: activeTab === 'task_compare' ? 'var(--color-moss)' : 'var(--color-paper)',
                color: activeTab === 'task_compare' ? 'var(--color-paper-raised)' : 'var(--color-ink)',
              }}
            >
              🎯 Per-Role Lab
            </button>
            <button
              onClick={() => setActiveTab('global_leaderboard')}
              style={{
                padding: '6px 14px',
                borderRadius: '4px',
                fontSize: 'var(--text-body-sm)',
                fontWeight: 'bold',
                cursor: 'pointer',
                border: '1px solid var(--color-rule)',
                background: activeTab === 'global_leaderboard' ? 'var(--color-moss)' : 'var(--color-paper)',
                color: activeTab === 'global_leaderboard' ? 'var(--color-paper-raised)' : 'var(--color-ink)',
              }}
            >
              🏆 Global Leaderboard
            </button>
            <button
              onClick={() => setActiveTab('run_history')}
              style={{
                padding: '6px 14px',
                borderRadius: '4px',
                fontSize: 'var(--text-body-sm)',
                fontWeight: 'bold',
                cursor: 'pointer',
                border: '1px solid var(--color-rule)',
                background: activeTab === 'run_history' ? 'var(--color-moss)' : 'var(--color-paper)',
                color: activeTab === 'run_history' ? 'var(--color-paper-raised)' : 'var(--color-ink)',
              }}
            >
              📜 Run History
            </button>
          </div>
        </div>

        {statusMsg && (
          <div
            style={{
              padding: '10px 14px',
              marginTop: '12px',
              background: 'var(--color-accent-subtle)',
              border: '1px solid var(--color-rule)',
              borderRadius: '4px',
              fontSize: 'var(--text-body-sm)',
              fontWeight: 600,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>{statusMsg}</span>
            <button
              onClick={() => setStatusMsg(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 'bold' }}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {activeTab === 'task_compare' && (
        <>
          {/* 3-Step Interactive Wizard */}
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-card)',
              padding: '16px 20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            {/* STEP 1: Pilih Task Role */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ background: 'var(--color-moss)', color: 'var(--color-paper-raised)', padding: '2px 8px', borderRadius: '50%', fontWeight: 'bold', fontSize: '12px' }}>
                  1
                </span>
                <strong style={{ fontSize: 'var(--text-body-md)', color: 'var(--color-ink)' }}>
                  PILIH TASK ROLE YANG INGIN DIUJI
                </strong>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                  (Satu task per benchmarking run)
                </span>
              </div>

              {/* Category Filter Pills */}
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
                {['all', ...categories].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    style={{
                      padding: '3px 10px',
                      borderRadius: '12px',
                      fontSize: 'var(--text-xs)',
                      fontWeight: selectedCategory === cat ? 'bold' : 'normal',
                      border: '1px solid var(--color-rule)',
                      background: selectedCategory === cat ? 'var(--color-paper-highlight)' : 'var(--color-paper)',
                      cursor: 'pointer',
                    }}
                  >
                    {cat.toUpperCase()}
                  </button>
                ))}
              </div>

              {/* Task Role Dropdown */}
              <select
                value={selectedTask}
                onChange={(e) => setSelectedTask(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '4px',
                  background: 'var(--color-paper)',
                  fontFamily: 'var(--font-precision)',
                  fontSize: 'var(--text-body-sm)',
                  fontWeight: 'bold',
                }}
              >
                {filteredTasksByCategory.map((t) => (
                  <option key={t.id} value={t.id}>
                    [{t.category.toUpperCase()}] {t.id} ({t.mode.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>

            {/* STEP 2: Pilih Model-Model Kandidat */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ background: 'var(--color-moss)', color: 'var(--color-paper-raised)', padding: '2px 8px', borderRadius: '50%', fontWeight: 'bold', fontSize: '12px' }}>
                    2
                  </span>
                  <strong style={{ fontSize: 'var(--text-body-md)', color: 'var(--color-ink)' }}>
                    PILIH MODEL-MODEL YANG INGIN DIUJI
                  </strong>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                    ({selectedModels.length} model terpilih)
                  </span>
                </div>

                <button
                  onClick={() => setSelectedModels([])}
                  style={{ background: 'none', border: 'none', color: 'var(--color-coral)', fontSize: 'var(--text-xs)', cursor: 'pointer' }}
                >
                  Reset Pilihan
                </button>
              </div>

              {/* Model Family Chip Groups */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {Object.entries(MODEL_FAMILIES).map(([family, models]) => (
                  <div key={family} style={{ background: 'var(--color-paper)', padding: '8px 12px', borderRadius: '4px', border: '1px solid var(--color-rule-soft)' }}>
                    <div style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--color-ink-soft)', marginBottom: '6px' }}>
                      {family.toUpperCase()}
                    </div>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {models.map((m) => {
                        const isSelected = selectedModels.includes(m);
                        return (
                          <button
                            key={m}
                            onClick={() => toggleModel(m)}
                            style={{
                              padding: '4px 10px',
                              borderRadius: '4px',
                              fontSize: 'var(--text-xs)',
                              fontFamily: 'var(--font-precision)',
                              fontWeight: isSelected ? 'bold' : 'normal',
                              border: isSelected ? '1px solid var(--color-moss)' : '1px solid var(--color-rule)',
                              background: isSelected ? 'var(--color-moss-subtle)' : 'var(--color-paper-raised)',
                              color: isSelected ? 'var(--color-ink)' : 'var(--color-ink-soft)',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <span>{isSelected ? '☑' : '☐'}</span>
                            <span>{m}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}

                {/* Custom Model Input */}
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <input
                    type="text"
                    list="candidate-models-datalist"
                    placeholder="Atau ketik/pilih nama model lain (mis. gpt-sol-6.1, qwen3.8-27b, dll)..."
                    value={customModelInput}
                    onChange={(e) => setCustomModelInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addCustomModel()}
                    style={{
                      flex: 1,
                      padding: '6px 12px',
                      border: '1px solid var(--color-rule)',
                      borderRadius: '4px',
                      fontFamily: 'var(--font-precision)',
                      fontSize: 'var(--text-body-sm)',
                    }}
                  />
                  <datalist id="candidate-models-datalist">
                    {candidateList.map((cand) => (
                      <option key={cand} value={cand} />
                    ))}
                  </datalist>
                  <TypewriterButton variant="secondary" onClick={addCustomModel}>
                    + Tambah Model
                  </TypewriterButton>
                </div>
              </div>
            </div>

            {/* STEP 3: Pilih Provider / Router */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ background: 'var(--color-moss)', color: 'var(--color-paper-raised)', padding: '2px 8px', borderRadius: '50%', fontWeight: 'bold', fontSize: '12px' }}>
                  3
                </span>
                <strong style={{ fontSize: 'var(--text-body-md)', color: 'var(--color-ink)' }}>
                  PILIH PROVIDER / ROUTER
                </strong>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                {PROVIDER_ROUTERS.map((p) => {
                  const isSelected = selectedProvider === p.id;
                  return (
                    <div
                      key={p.id}
                      onClick={() => {
                        sounds.playClick('typewriter');
                        setSelectedProvider(p.id);
                      }}
                      style={{
                        padding: '10px 14px',
                        borderRadius: '4px',
                        border: isSelected ? '1px solid var(--color-moss)' : '1px solid var(--color-rule)',
                        background: isSelected ? 'var(--color-moss-subtle)' : 'var(--color-paper)',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ fontWeight: 'bold', fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)' }}>
                        {isSelected ? '● ' : '○ '} {p.label}
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
                        {p.desc}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Execution Options & Trigger Action */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingTop: '12px',
                borderTop: '1px solid var(--color-rule-soft)',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', gap: '18px', alignItems: 'center' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: 'var(--text-body-sm)' }}>
                  <input
                    type="checkbox"
                    checked={useFixtures}
                    onChange={(e) => setUseFixtures(e.target.checked)}
                  />
                  <span>📦 Gunakan Mock Payload Realistis (250 Berita + Full Multi-Asset Context)</span>
                </label>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-soft)' }}>Concurrency:</span>
                  <input
                    type="number"
                    min={1}
                    max={8}
                    value={concurrency}
                    onChange={(e) => setConcurrency(parseInt(e.target.value) || 4)}
                    style={{ width: '50px', padding: '4px 6px', border: '1px solid var(--color-rule)', borderRadius: '4px' }}
                  />
                </div>
              </div>

              <TypewriterButton
                variant="primary"
                onClick={handleStartBenchmark}
                disabled={isExecuting || selectedModels.length === 0}
              >
                {isExecuting ? '⚡ Sedang Mengeksekusi...' : `▶ Mulai Benchmark (${selectedModels.length} Model)`}
              </TypewriterButton>
            </div>
          </div>

          {/* Active Live Progress Banner */}
          {isExecuting && (
            <div
              style={{
                padding: '12px 18px',
                background: 'var(--color-moss-subtle)',
                border: '1px solid var(--color-moss)',
                borderRadius: '4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <strong style={{ fontSize: 'var(--text-body-md)' }}>
                  ⚡ Eksekusi Benchmark Sedang Berjalan...
                  {liveProgress?.activeModel ? ` [Menguji: ${liveProgress.activeModel}]` : ''}
                </strong>
                <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
                  Task: <strong>{selectedTask}</strong> · Router: <strong>{selectedProvider.toUpperCase()}</strong> · Models: {selectedModels.join(', ')}
                </div>
              </div>
              <StatusIndicator status="connecting" label="RUNNING" />
            </div>
          )}

          {/* KPI Best Performer Cards */}
          {validComparisons.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
              {/* Best Quality */}
              <div
                className="win-window ledger-card"
                style={{
                  background: 'var(--color-paper-raised)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '4px',
                  padding: '12px 16px',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--color-ink-soft)' }}>
                  👑 TERTINGGI AKURASI / KUALITAS
                </div>
                <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 'bold', margin: '4px 0', color: 'var(--color-moss)' }}>
                  {bestScoreModel ? bestScoreModel.model_name : '-'}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                  Skor: <strong>{bestScoreModel?.score ? (bestScoreModel.score * 10).toFixed(1) : '-'} / 10</strong> ({bestScoreModel?.provider_route})
                </div>
              </div>

              {/* Fastest Speed */}
              <div
                className="win-window ledger-card"
                style={{
                  background: 'var(--color-paper-raised)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '4px',
                  padding: '12px 16px',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--color-ink-soft)' }}>
                  ⚡ TERCEPAT / LATENSI TERENDAH
                </div>
                <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 'bold', margin: '4px 0', color: 'var(--color-ochre)' }}>
                  {fastestModel ? fastestModel.model_name : '-'}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                  Latensi: <strong>{fastestModel?.latency_s?.toFixed(2) || '-'}s</strong> ({fastestModel?.provider_route})
                </div>
              </div>

              {/* Lowest Cost */}
              <div
                className="win-window ledger-card"
                style={{
                  background: 'var(--color-paper-raised)',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '4px',
                  padding: '12px 16px',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--color-ink-soft)' }}>
                  💰 BIAYA TERHEMAT (CACHE HIT)
                </div>
                <div style={{ fontSize: 'var(--text-title-sm)', fontWeight: 'bold', margin: '4px 0', color: 'var(--color-ink)' }}>
                  {cheapestModel ? cheapestModel.model_name : '-'}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
                  Cached: <strong>${cheapestModel?.cost_usd_with_cache?.toFixed(5) || '0.00000'}</strong> (Cold: ${cheapestModel?.cost_usd_no_cache?.toFixed(5)})
                </div>
              </div>
            </div>
          )}

          {/* Task Comparison Table */}
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar win-titlebar--moss"
              style={{
                padding: '8px 14px',
                borderBottom: '1px solid var(--color-rule)',
                display: 'flex',
                justifyContent: 'space-between',
                fontWeight: 'bold',
              }}
            >
              <span>📊 Hasil Komparasi Model untuk Role: <code>{selectedTask}</code></span>
              <span style={{ fontSize: 'var(--text-xs)' }}>
                {taskComparisons.length} Evaluasi Tersimpan di DB
              </span>
            </div>

            {loadingComparisons ? (
              <div style={{ padding: '30px', textAlign: 'center', color: 'var(--color-ink-soft)' }}>
                Memuat data komparasi model...
              </div>
            ) : taskComparisons.length === 0 ? (
              <EmptyState
                title="Belum Ada Hasil Uji untuk Role Ini"
                message={`Pilih model dan provider di atas, lalu klik "Mulai Benchmark (${selectedTask})" untuk menguji secara nyata.`}
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-body-sm)', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ background: 'var(--color-table-header)', borderBottom: '1px solid var(--color-rule)' }}>
                      <th style={{ padding: '10px 14px' }}>Rank</th>
                      <th style={{ padding: '10px 14px' }}>Model</th>
                      <th style={{ padding: '10px 14px' }}>Router / Provider</th>
                      <th style={{ padding: '10px 14px' }}>Kualitas / Skor</th>
                      <th style={{ padding: '10px 14px' }}>Speed (Latency)</th>
                      <th style={{ padding: '10px 14px' }}>Cost (No Cache)</th>
                      <th style={{ padding: '10px 14px' }}>Cost (With Cache)</th>
                      <th style={{ padding: '10px 14px' }}>Input / Output Tok</th>
                      <th style={{ padding: '10px 14px' }}>Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {taskComparisons.map((row, idx) => {
                      const score10 = row.score !== null ? (row.score * 10).toFixed(1) : '-';
                      const isBestScore = bestScoreModel && row.id === bestScoreModel.id;
                      const isFastest = fastestModel && row.id === fastestModel.id;

                      return (
                        <tr
                          key={row.id}
                          style={{
                            borderBottom: '1px solid var(--color-rule-soft)',
                            background: idx % 2 === 0 ? 'transparent' : 'var(--color-paper-subtle)',
                          }}
                        >
                          <td style={{ padding: '10px 14px', fontWeight: 'bold' }}>
                            #{idx + 1}
                          </td>
                          <td style={{ padding: '10px 14px', fontFamily: 'var(--font-precision)', fontWeight: 600 }}>
                            {row.model_name}
                            {isBestScore && (
                              <span style={{ marginLeft: '6px', fontSize: '11px', background: 'var(--color-moss-subtle)', color: 'var(--color-moss)', padding: '2px 4px', borderRadius: '3px' }}>
                                ★ TOP KUALITAS
                              </span>
                            )}
                            {isFastest && (
                              <span style={{ marginLeft: '6px', fontSize: '11px', background: 'var(--color-ochre-subtle)', color: 'var(--color-ochre)', padding: '2px 4px', borderRadius: '3px' }}>
                                ⚡ TERCEPAT
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <span
                              style={{
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontSize: '11px',
                                fontWeight: 'bold',
                                background: 'var(--color-paper-highlight)',
                                border: '1px solid var(--color-rule-soft)',
                              }}
                            >
                              {(row.provider_route || row.provider || 'direct').toUpperCase()}
                            </span>
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            {row.error ? (
                              <span style={{ color: 'var(--color-coral)', fontWeight: 'bold', fontSize: '12px' }}>
                                ERROR
                              </span>
                            ) : (
                              <span
                                style={{
                                  padding: '3px 8px',
                                  borderRadius: '4px',
                                  fontWeight: 'bold',
                                  background: (row.score || 0) >= 0.75
                                    ? 'var(--color-moss-subtle)'
                                    : (row.score || 0) >= 0.5
                                    ? 'var(--color-ochre-subtle)'
                                    : 'var(--color-coral-subtle)',
                                  color: (row.score || 0) >= 0.75
                                    ? 'var(--color-moss)'
                                    : (row.score || 0) >= 0.5
                                    ? 'var(--color-ochre)'
                                    : 'var(--color-coral)',
                                }}
                              >
                                {score10} / 10
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '10px 14px', fontFamily: 'var(--font-precision)' }}>
                            <strong>{row.latency_s?.toFixed(2) || '0.00'}s</strong>
                          </td>
                          <td style={{ padding: '10px 14px', fontFamily: 'var(--font-precision)', color: 'var(--color-ink-soft)' }}>
                            ${row.cost_usd_no_cache?.toFixed(5) || '0.00000'}
                          </td>
                          <td style={{ padding: '10px 14px', fontFamily: 'var(--font-precision)', fontWeight: 'bold', color: 'var(--color-ink)' }}>
                            ${row.cost_usd_with_cache?.toFixed(5) || '0.00000'}
                          </td>
                          <td style={{ padding: '10px 14px', fontSize: '11px', fontFamily: 'var(--font-precision)', color: 'var(--color-ink-soft)' }}>
                            {row.input_tokens?.toLocaleString()} / {row.output_tokens?.toLocaleString()}
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <button
                              onClick={() => setViewDetailModal(row)}
                              style={{
                                padding: '3px 8px',
                                fontSize: '11px',
                                borderRadius: '3px',
                                border: '1px solid var(--color-rule)',
                                background: 'var(--color-paper)',
                                cursor: 'pointer',
                              }}
                            >
                              Detail
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Global Leaderboard Tab */}
      {activeTab === 'global_leaderboard' && (
        <div
          className="win-window ledger-card"
          style={{
            background: 'var(--color-paper-raised)',
            border: '1px solid var(--color-rule)',
            borderRadius: 'var(--radius-card)',
            boxShadow: 'var(--shadow-card)',
            overflow: 'hidden',
          }}
        >
          <div
            className="win-titlebar win-titlebar--moss"
            style={{
              padding: '8px 14px',
              borderBottom: '1px solid var(--color-rule)',
              display: 'flex',
              justifyContent: 'space-between',
              fontWeight: 'bold',
            }}
          >
            <span>🏆 Model Leaderboard Agregat (Semua Task)</span>
            <span style={{ fontSize: 'var(--text-xs)' }}>{leaderboard.length} Kandidat Terdaftar</span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-body-sm)', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'var(--color-table-header)', borderBottom: '1px solid var(--color-rule)' }}>
                  <th style={{ padding: '10px 14px' }}>Rank</th>
                  <th style={{ padding: '10px 14px' }}>Model</th>
                  <th style={{ padding: '10px 14px' }}>Rata-rata Skor</th>
                  <th style={{ padding: '10px 14px' }}>Pass Rate</th>
                  <th style={{ padding: '10px 14px' }}>Avg Latensi</th>
                  <th style={{ padding: '10px 14px' }}>Avg Cost</th>
                  <th style={{ padding: '10px 14px' }}>Total Tasks</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((row, idx) => (
                  <tr key={row.model_name} style={{ borderBottom: '1px solid var(--color-rule-soft)' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 'bold' }}>#{idx + 1}</td>
                    <td style={{ padding: '10px 14px', fontFamily: 'var(--font-precision)', fontWeight: 600 }}>
                      {row.model_name}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontWeight: 'bold',
                          background: row.avg_score >= 0.8 ? 'var(--color-moss-subtle)' : row.avg_score >= 0.5 ? 'var(--color-ochre-subtle)' : 'var(--color-coral-subtle)',
                        }}
                      >
                        {(row.avg_score * 10).toFixed(1)} / 10
                      </span>
                    </td>
                    <td style={{ padding: '10px 14px' }}>{row.pass_rate_pct}%</td>
                    <td style={{ padding: '10px 14px' }}>{row.avg_latency_s}s</td>
                    <td style={{ padding: '10px 14px' }}>${row.avg_cost_usd.toFixed(4)}</td>
                    <td style={{ padding: '10px 14px' }}>{row.total_tasks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Run History Tab */}
      {activeTab === 'run_history' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '16px' }}>
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar"
              style={{
                padding: '8px 14px',
                borderBottom: '1px solid var(--color-rule)',
                fontWeight: 'bold',
              }}
            >
              <span>Laporan Markdown Run #{selectedRunId || 'Latest'}</span>
            </div>
            {loadingRun ? (
              <div style={{ padding: '20px', textAlign: 'center' }}>Memuat laporan run...</div>
            ) : runDetail && runDetail.report_markdown ? (
              <pre
                style={{
                  padding: '16px',
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'var(--font-precision)',
                  fontSize: 'var(--text-body-sm)',
                  maxHeight: '450px',
                  overflowY: 'auto',
                }}
              >
                {runDetail.report_markdown}
              </pre>
            ) : (
              <EmptyState title="Pilih Run" message="Pilih salah satu run dari daftar di samping untuk melihat laporannya." />
            )}
          </div>

          {/* Past Runs List */}
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar"
              style={{
                padding: '8px 14px',
                borderBottom: '1px solid var(--color-rule)',
                fontWeight: 'bold',
              }}
            >
              <span>Riwayat Run Benchmark</span>
            </div>
            <div style={{ maxHeight: '450px', overflowY: 'auto' }}>
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
                    <StatusIndicator status={r.is_running ? 'connecting' : 'connected'} label={r.is_running ? 'RUNNING' : 'SELESAI'} />
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginTop: '2px' }}>
                    {r.tasks_count} tasks · {r.models_count} models
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>
                    {r.started_at ? new Date(r.started_at).toLocaleString() : '-'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Output / Detail Modal */}
      {viewDetailModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
          }}
        >
          <div
            className="win-window ledger-card"
            style={{
              background: 'var(--color-paper-raised)',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              width: '100%',
              maxWidth: '700px',
              maxHeight: '80vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: 'var(--shadow-modal)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar"
              style={{
                padding: '8px 14px',
                borderBottom: '1px solid var(--color-rule)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontWeight: 'bold',
              }}
            >
              <span>Detail Hasil: {viewDetailModal.model_name} on {viewDetailModal.task_id}</span>
              <button
                onClick={() => setViewDetailModal(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 'bold' }}
              >
                ✕
              </button>
            </div>
            <div style={{ padding: '16px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px' }}>
                <div><strong>Score:</strong> {viewDetailModal.score !== null ? (viewDetailModal.score * 10).toFixed(1) : '-'} / 10</div>
                <div><strong>Speed:</strong> {viewDetailModal.latency_s?.toFixed(2)}s</div>
                <div><strong>Router:</strong> {viewDetailModal.provider_route?.toUpperCase()}</div>
                <div><strong>Cost (Cold):</strong> ${viewDetailModal.cost_usd_no_cache?.toFixed(5)}</div>
                <div><strong>Cost (Cached):</strong> ${viewDetailModal.cost_usd_with_cache?.toFixed(5)}</div>
                <div><strong>Tokens:</strong> {viewDetailModal.input_tokens} in / {viewDetailModal.output_tokens} out</div>
              </div>

              {viewDetailModal.error && (
                <div style={{ padding: '8px 12px', background: 'var(--color-coral-subtle)', color: 'var(--color-coral)', borderRadius: '4px', fontSize: 'var(--text-xs)' }}>
                  <strong>Error:</strong> {viewDetailModal.error}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
