import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import type { PluginItem, PluginCatalogItem } from '../../types/api';
import { sounds } from '../../lib/soundEffects';

export const PluginManagerPanel: React.FC = () => {
  const [activeSubView, setActiveSubView] = useState<'installed' | 'marketplace' | 'custom'>('installed');
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [catalog, setCatalog] = useState<PluginCatalogItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [actionPendingId, setActionPendingId] = useState<string | null>(null);

  // Custom package install state
  const [customPackage, setCustomPackage] = useState<string>('');
  const [installing, setInstalling] = useState<boolean>(false);
  const [consoleOutput, setConsoleOutput] = useState<string | null>(null);
  const [showConsoleModal, setShowConsoleModal] = useState<boolean>(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [pluginsRes, catalogRes] = await Promise.all([
        api.plugins(),
        api.pluginCatalog(),
      ]);
      if (pluginsRes?.plugins) setPlugins(pluginsRes.plugins);
      if (catalogRes?.catalog) setCatalog(catalogRes.catalog);
    } catch (err) {
      console.error('Failed to load plugin data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleToggle = async (plugin: PluginItem) => {
    if (!plugin.can_toggle || actionPendingId) return;
    sounds.playClick('typewriter');
    setActionPendingId(plugin.id);
    const nextState = !plugin.enabled;

    try {
      const res = await api.pluginToggle(plugin.id, plugin.category, nextState);
      if (res?.plugins) {
        setPlugins(res.plugins);
      } else {
        // Fallback optimistic update
        setPlugins((prev) =>
          prev.map((p) =>
            p.id === plugin.id
              ? {
                  ...p,
                  enabled: nextState,
                  status: nextState ? 'ACTIVE' : 'DISABLED',
                }
              : p
          )
        );
      }
    } catch (err) {
      console.error('Failed to toggle plugin:', err);
      alert(`Failed to toggle plugin status: ${err}`);
    } finally {
      setActionPendingId(null);
    }
  };

  const handleInstall = async (packageName: string) => {
    if (!packageName.trim() || installing) return;
    sounds.playClick('toggle');
    setInstalling(true);
    setConsoleOutput(`[Harness.Installer] Running pip install: ${packageName.trim()}...\nPlease wait...`);
    setShowConsoleModal(true);

    try {
      const res = await api.pluginInstall(packageName.trim());
      setConsoleOutput(
        res.output ||
          `[Harness.Installer] Successfully installed ${packageName}. Refreshing plugins list...`
      );
      if (res?.plugins) {
        setPlugins(res.plugins);
      } else {
        await loadData();
      }
    } catch (err: any) {
      setConsoleOutput(`[ERROR] Installation failed:\n${err?.message || err}`);
    } finally {
      setInstalling(false);
    }
  };

  const handleUninstall = async (packageName: string) => {
    if (!window.confirm(`Are you sure you want to uninstall package ${packageName}?`)) return;
    sounds.playClick('toggle');
    setActionPendingId(packageName);

    try {
      const res = await api.pluginUninstall(packageName);
      alert(res.output || `Package ${packageName} uninstalled successfully.`);
      if (res?.plugins) {
        setPlugins(res.plugins);
      } else {
        await loadData();
      }
    } catch (err: any) {
      alert(`Gagal uninstall: ${err?.message || err}`);
    } finally {
      setActionPendingId(null);
    }
  };

  const categories = ['all', ...Array.from(new Set(plugins.map((p) => p.category)))];

  const filteredPlugins = plugins.filter((p) => {
    const matchesCat = selectedCategory === 'all' || p.category === selectedCategory;
    const matchesSearch =
      searchQuery === '' ||
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCat && matchesSearch;
  });

  const activeCount = plugins.filter((p) => p.enabled).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Banner / Window Header */}
      <div
        className="win-window ledger-card"
        style={{
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          padding: '16px 20px',
          boxShadow: 'var(--shadow-card)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <div
            style={{
              fontFamily: 'var(--font-heading)',
              fontSize: '1.25rem',
              fontWeight: 700,
              letterSpacing: '0.05em',
              color: 'var(--color-ink)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <span>🔌</span> PLUGIN MARKETPLACE &amp; HARNESS HOST
          </div>
          <div
            style={{
              fontFamily: 'var(--font-precision)',
              fontSize: '0.82rem',
              color: 'var(--color-ink-soft)',
              marginTop: '4px',
            }}
          >
            Modular "Everything is Plug-in" Architecture • Dynamic ON/OFF Lifecycle
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              fontFamily: 'var(--font-precision)',
              fontSize: '0.85rem',
              padding: '6px 12px',
              borderRadius: '4px',
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
            }}
          >
            Active: <strong style={{ color: 'var(--color-green, #10b981)' }}>{activeCount}</strong> / {plugins.length}
          </div>

          <button
            onClick={() => {
              sounds.playClick('typewriter');
              loadData();
            }}
            disabled={loading}
            className="win-btn"
            style={{
              fontFamily: 'var(--font-precision)',
              fontSize: '0.82rem',
              padding: '6px 14px',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Refreshing...' : '🔄 Refresh'}
          </button>
        </div>
      </div>

      {/* View Switcher Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          borderBottom: '2px solid var(--color-rule)',
          paddingBottom: '2px',
        }}
      >
        <button
          onClick={() => {
            sounds.playClick('typewriter');
            setActiveSubView('installed');
          }}
          className={`tab-btn ${activeSubView === 'installed' ? 'active' : ''}`}
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '0.9rem',
            padding: '8px 18px',
            background: activeSubView === 'installed' ? 'var(--color-paper-raised)' : 'transparent',
            border: activeSubView === 'installed' ? '2px solid var(--color-rule)' : '2px solid transparent',
            borderBottom: 'none',
            borderTopLeftRadius: '6px',
            borderTopRightRadius: '6px',
            cursor: 'pointer',
            fontWeight: activeSubView === 'installed' ? 700 : 500,
          }}
        >
          Installed Plugins ({plugins.length})
        </button>

        <button
          onClick={() => {
            sounds.playClick('typewriter');
            setActiveSubView('marketplace');
          }}
          className={`tab-btn ${activeSubView === 'marketplace' ? 'active' : ''}`}
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '0.9rem',
            padding: '8px 18px',
            background: activeSubView === 'marketplace' ? 'var(--color-paper-raised)' : 'transparent',
            border: activeSubView === 'marketplace' ? '2px solid var(--color-rule)' : '2px solid transparent',
            borderBottom: 'none',
            borderTopLeftRadius: '6px',
            borderTopRightRadius: '6px',
            cursor: 'pointer',
            fontWeight: activeSubView === 'marketplace' ? 700 : 500,
          }}
        >
          Marketplace &amp; 1-Click Catalog ({catalog.length})
        </button>

        <button
          onClick={() => {
            sounds.playClick('typewriter');
            setActiveSubView('custom');
          }}
          className={`tab-btn ${activeSubView === 'custom' ? 'active' : ''}`}
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '0.9rem',
            padding: '8px 18px',
            background: activeSubView === 'custom' ? 'var(--color-paper-raised)' : 'transparent',
            border: activeSubView === 'custom' ? '2px solid var(--color-rule)' : '2px solid transparent',
            borderBottom: 'none',
            borderTopLeftRadius: '6px',
            borderTopRightRadius: '6px',
            cursor: 'pointer',
            fontWeight: activeSubView === 'custom' ? 700 : 500,
          }}
        >
          Install Custom Package (pip)
        </button>
      </div>

      {/* VIEW 1: INSTALLED PLUGINS */}
      {activeSubView === 'installed' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Filter Bar */}
          <div
            style={{
              display: 'flex',
              gap: '12px',
              flexWrap: 'wrap',
              alignItems: 'center',
              background: 'var(--color-paper)',
              padding: '10px 14px',
              border: '1px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
            }}
          >
            <input
              type="text"
              placeholder="Search plugins by name, id, description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                flex: '1 1 250px',
                padding: '6px 12px',
                fontFamily: 'var(--font-precision)',
                fontSize: '0.85rem',
                border: '1px solid var(--color-rule)',
                borderRadius: '4px',
                background: 'var(--color-paper-raised)',
                color: 'var(--color-ink)',
              }}
            />

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontFamily: 'var(--font-precision)', fontSize: '0.82rem', color: 'var(--color-ink-soft)' }}>
                Category:
              </span>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                style={{
                  padding: '6px 10px',
                  fontFamily: 'var(--font-precision)',
                  fontSize: '0.82rem',
                  border: '1px solid var(--color-rule)',
                  borderRadius: '4px',
                  background: 'var(--color-paper-raised)',
                  color: 'var(--color-ink)',
                }}
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Plugin Cards Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
              gap: '14px',
            }}
          >
            {filteredPlugins.map((plugin) => {
              const isPending = actionPendingId === plugin.id;
              const isActive = plugin.enabled;
              const isDegraded = plugin.status.startsWith('DEGRADED');

              return (
                <div
                  key={plugin.id}
                  className="win-window ledger-card"
                  style={{
                    background: 'var(--color-paper-raised)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: 'var(--radius-card)',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: '12px',
                    boxShadow: 'var(--shadow-card)',
                    opacity: isActive ? 1 : 0.72,
                    transition: 'opacity 0.2s ease',
                  }}
                >
                  <div>
                    {/* Header Row */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                      <div>
                        <div
                          style={{
                            fontFamily: 'var(--font-heading)',
                            fontSize: '1rem',
                            fontWeight: 700,
                            color: 'var(--color-ink)',
                          }}
                        >
                          {plugin.name}
                        </div>
                        <div
                          style={{
                            fontFamily: 'var(--font-mono, monospace)',
                            fontSize: '0.78rem',
                            color: 'var(--color-ink-soft)',
                            marginTop: '2px',
                          }}
                        >
                          id: {plugin.id} • v{plugin.version}
                        </div>
                      </div>

                      {/* Status Badges */}
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                        <span
                          style={{
                            fontFamily: 'var(--font-mono, monospace)',
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            padding: '2px 8px',
                            borderRadius: '3px',
                            background: isDegraded
                              ? '#fef3c7'
                              : isActive
                              ? '#d1fae5'
                              : '#f3f4f6',
                            color: isDegraded
                              ? '#92400e'
                              : isActive
                              ? '#065f46'
                              : '#6b7280',
                            border: `1px solid ${
                              isDegraded ? '#f59e0b' : isActive ? '#10b981' : '#d1d5db'
                            }`,
                          }}
                        >
                          {isDegraded ? 'DEGRADED' : isActive ? '🟢 ACTIVE' : '⚪ DISABLED'}
                        </span>

                        <span
                          style={{
                            fontFamily: 'var(--font-precision)',
                            fontSize: '0.68rem',
                            color: 'var(--color-ink-soft)',
                            textTransform: 'uppercase',
                          }}
                        >
                          {plugin.category} • {plugin.origin}
                        </span>
                      </div>
                    </div>

                    {/* Description */}
                    <div
                      style={{
                        fontFamily: 'var(--font-body)',
                        fontSize: '0.84rem',
                        color: 'var(--color-ink)',
                        marginTop: '10px',
                        lineHeight: 1.4,
                      }}
                    >
                      {plugin.description || 'No description provided.'}
                    </div>

                    {/* Degraded Message if any */}
                    {plugin.status_message && (
                      <div
                        style={{
                          marginTop: '8px',
                          padding: '6px 8px',
                          borderRadius: '4px',
                          background: '#fffbeb',
                          border: '1px solid #fde68a',
                          fontFamily: 'var(--font-mono, monospace)',
                          fontSize: '0.74rem',
                          color: '#b45309',
                        }}
                      >
                        ⚠️ {plugin.status_message}
                      </div>
                    )}
                  </div>

                  {/* Actions Bar */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      borderTop: '1px solid var(--color-rule)',
                      paddingTop: '10px',
                      marginTop: '4px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {plugin.can_uninstall && (
                        <button
                          onClick={() => handleUninstall(plugin.id)}
                          disabled={isPending}
                          style={{
                            fontFamily: 'var(--font-precision)',
                            fontSize: '0.74rem',
                            padding: '3px 8px',
                            background: '#fee2e2',
                            color: '#b91c1c',
                            border: '1px solid #f87171',
                            borderRadius: '3px',
                            cursor: 'pointer',
                          }}
                        >
                          Uninstall
                        </button>
                      )}
                    </div>

                    {/* Instant ON/OFF Switch */}
                    <button
                      onClick={() => handleToggle(plugin)}
                      disabled={isPending || !plugin.can_toggle}
                      style={{
                        fontFamily: 'var(--font-heading)',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        padding: '6px 14px',
                        borderRadius: '4px',
                        cursor: plugin.can_toggle && !isPending ? 'pointer' : 'not-allowed',
                        background: isActive ? '#059669' : 'var(--color-paper)',
                        color: isActive ? '#ffffff' : 'var(--color-ink-soft)',
                        border: `1px solid ${isActive ? '#047857' : 'var(--color-rule)'}`,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        transition: 'all 0.15s ease',
                      }}
                      title={!plugin.can_toggle ? 'Core invariant cannot be toggled off' : 'Click to toggle ON/OFF'}
                    >
                      <span>{isPending ? '⏳' : isActive ? '●' : '○'}</span>
                      <span>{isPending ? 'Updating...' : isActive ? 'ON (Active)' : 'OFF (Standby)'}</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* VIEW 2: COMMUNITY MARKETPLACE */}
      {activeSubView === 'marketplace' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div
            style={{
              padding: '12px 16px',
              borderRadius: 'var(--radius-card)',
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
              fontFamily: 'var(--font-precision)',
              fontSize: '0.84rem',
              color: 'var(--color-ink)',
            }}
          >
            📦 <strong>Curated Community Marketplace</strong>: Official plugins and verified extensions for Monika.
            Click <strong>1-Click Install</strong> to fetch via pip into Monika virtual environment.
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
              gap: '14px',
            }}
          >
            {catalog.map((item) => {
              const isInstalled = plugins.some((p) => p.id === item.id || p.name === item.name);

              return (
                <div
                  key={item.id}
                  className="win-window ledger-card"
                  style={{
                    background: 'var(--color-paper-raised)',
                    border: '1px solid var(--color-rule)',
                    borderRadius: 'var(--radius-card)',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: '12px',
                    boxShadow: 'var(--shadow-card)',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                      <div>
                        <div
                          style={{
                            fontFamily: 'var(--font-heading)',
                            fontSize: '1rem',
                            fontWeight: 700,
                            color: 'var(--color-ink)',
                          }}
                        >
                          {item.name}
                        </div>
                        <div
                          style={{
                            fontFamily: 'var(--font-mono, monospace)',
                            fontSize: '0.78rem',
                            color: 'var(--color-ink-soft)',
                            marginTop: '2px',
                          }}
                        >
                          {item.package} • v{item.version}
                        </div>
                      </div>

                      <span
                        style={{
                          fontFamily: 'var(--font-mono, monospace)',
                          fontSize: '0.72rem',
                          padding: '2px 8px',
                          borderRadius: '3px',
                          background: 'var(--color-paper)',
                          border: '1px solid var(--color-rule)',
                          color: 'var(--color-ink-soft)',
                          textTransform: 'uppercase',
                        }}
                      >
                        {item.category}
                      </span>
                    </div>

                    <div
                      style={{
                        fontFamily: 'var(--font-body)',
                        fontSize: '0.84rem',
                        color: 'var(--color-ink)',
                        marginTop: '10px',
                        lineHeight: 1.4,
                      }}
                    >
                      {item.description}
                    </div>

                    <div
                      style={{
                        fontFamily: 'var(--font-precision)',
                        fontSize: '0.76rem',
                        color: 'var(--color-ink-soft)',
                        marginTop: '8px',
                      }}
                    >
                      Author: {item.author}
                    </div>
                  </div>

                  <div
                    style={{
                      borderTop: '1px solid var(--color-rule)',
                      paddingTop: '10px',
                      display: 'flex',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <button
                      onClick={() => handleInstall(item.package)}
                      disabled={installing}
                      className="win-btn"
                      style={{
                        fontFamily: 'var(--font-heading)',
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        padding: '6px 16px',
                        cursor: installing ? 'not-allowed' : 'pointer',
                        background: isInstalled ? '#f3f4f6' : 'var(--color-paper-raised)',
                        color: isInstalled ? '#4b5563' : 'var(--color-ink)',
                      }}
                    >
                      {isInstalled ? '✓ Reinstall / Update' : '📥 1-Click Install'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* VIEW 3: CUSTOM PIP INSTALLER */}
      {activeSubView === 'custom' && (
        <div
          className="win-window ledger-card"
          style={{
            background: 'var(--color-paper-raised)',
            border: '2px solid var(--color-rule)',
            borderRadius: 'var(--radius-card)',
            padding: '20px',
            maxWidth: '680px',
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--font-heading)',
              fontSize: '1.1rem',
              fontWeight: 700,
              color: 'var(--color-ink)',
              marginBottom: '8px',
            }}
          >
            Direct Pip Package Installation
          </div>
          <div
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: '0.85rem',
              color: 'var(--color-ink-soft)',
              marginBottom: '16px',
              lineHeight: 1.4,
            }}
          >
            Enter any valid Monika plugin package name (e.g. <code>monika-plugin-telegram-extended</code>),
            Git HTTPS URL (e.g. <code>https://github.com/user/monika-plugin-x.git</code>), or local <code>.whl</code> file path.
          </div>

          <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
            <input
              type="text"
              placeholder="e.g. monika-plugin-deepseek"
              value={customPackage}
              onChange={(e) => setCustomPackage(e.target.value)}
              style={{
                flex: 1,
                padding: '8px 12px',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: '0.85rem',
                border: '1px solid var(--color-rule)',
                borderRadius: '4px',
                background: 'var(--color-paper)',
                color: 'var(--color-ink)',
              }}
            />

            <button
              onClick={() => handleInstall(customPackage)}
              disabled={installing || !customPackage.trim()}
              className="win-btn"
              style={{
                fontFamily: 'var(--font-heading)',
                fontSize: '0.85rem',
                fontWeight: 700,
                padding: '8px 20px',
                cursor: installing || !customPackage.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              {installing ? 'Installing...' : 'Install via pip'}
            </button>
          </div>

          <div
            style={{
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: '0.76rem',
              color: 'var(--color-ink-soft)',
              background: 'var(--color-paper)',
              padding: '10px 12px',
              borderRadius: '4px',
              border: '1px solid var(--color-rule)',
            }}
          >
            Virtualenv Python: Executed via <code>sys.executable -m pip install</code>.<br />
            Security filter enforced: Dangerous shell tokens are strictly rejected.
          </div>
        </div>
      )}

      {/* CONSOLE MODAL FOR LIVE PIP OUTPUT */}
      {showConsoleModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            className="win-window ledger-card console-scanline"
            role="dialog"
            aria-modal="true"
            aria-labelledby="plugin-console-title"
            style={{
              background: 'var(--color-console-bg)',
              color: 'var(--color-console-phosphor)',
              border: '2px solid var(--color-rule)',
              borderRadius: 'var(--radius-card)',
              width: '100%',
              maxWidth: '720px',
              maxHeight: '80vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: 'var(--shadow-elevated)',
              overflow: 'hidden',
            }}
          >
            <div
              className="win-titlebar"
              style={{
                padding: '8px 14px',
                borderBottom: '2px solid var(--color-rule)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                background: 'var(--color-win-yellow)',
                color: '#1C1917',
              }}
            >
              <span id="plugin-console-title" style={{ fontFamily: 'var(--font-precision)', fontSize: 'var(--text-body-sm)', fontWeight: 700, letterSpacing: '0.05em' }}>
                {installing ? '⏳ [INSTALLING PLUGIN VIA PIP...]' : '[TERMINAL INSTALLATION OUTPUT]'}
              </span>
              <button
                onClick={() => setShowConsoleModal(false)}
                disabled={installing}
                aria-label="Close terminal output"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#1C1917',
                  fontSize: '1rem',
                  fontWeight: 'bold',
                  cursor: installing ? 'not-allowed' : 'pointer',
                }}
              >
                ✕
              </button>
            </div>

            <div
              style={{
                padding: '16px',
                overflowY: 'auto',
                fontFamily: 'var(--font-precision)',
                fontSize: 'var(--text-body-sm)',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                flex: 1,
                minHeight: '260px',
                color: 'var(--color-console-phosphor)',
                background: 'var(--color-console-bg)',
              }}
            >
              {consoleOutput}
            </div>

            <div
              style={{
                padding: '10px 16px',
                borderTop: '2px solid var(--color-rule)',
                display: 'flex',
                justifyContent: 'flex-end',
                background: 'var(--color-paper-raised)',
              }}
            >
              <button
                onClick={() => setShowConsoleModal(false)}
                disabled={installing}
                className="win-btn"
                style={{
                  fontFamily: 'var(--font-precision)',
                  fontSize: 'var(--text-body-sm)',
                  padding: '6px 16px',
                  cursor: installing ? 'not-allowed' : 'pointer',
                }}
              >
                {installing ? 'Please wait...' : 'Close'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
