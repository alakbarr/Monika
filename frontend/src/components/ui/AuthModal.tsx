import React, { useState, useEffect } from 'react';
import { TypewriterButton } from './TypewriterButton';
import { getStoredToken, setStoredToken, type TokenStorageType } from '../../lib/api';

interface AuthModalProps {
  isOpen: boolean;
  onSuccess: () => void;
  onClose?: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onSuccess,
  onClose,
}) => {
  const [apiKey, setApiKey] = useState('');
  const [remember, setRemember] = useState(true);
  const [showKey, setShowKey] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (isOpen) {
      setApiKey(getStoredToken());
      setErrorMsg('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = apiKey.trim();
    if (!trimmed) {
      setErrorMsg('API key cannot be empty.');
      return;
    }
    const storageType: TokenStorageType = remember ? 'local' : 'session';
    setStoredToken(trimmed, storageType);
    onSuccess();
    if (onClose) onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
      className="retro-modal-scrim"
      style={{
        zIndex: 10000,
        padding: '16px',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '480px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border-strong)',
          boxShadow: 'var(--shadow-modal)',
          borderRadius: '2px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          id="auth-modal-title"
          style={{
            padding: '10px 16px',
            borderBottom: '1px solid var(--color-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--color-surface-well)',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            fontSize: '11px',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          <span>MONIKA SECURITY — DASHBOARD AUTHENTICATION</span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close authentication modal"
              style={{
                background: 'transparent',
                border: '1px solid var(--color-border)',
                color: 'var(--color-ink)',
                cursor: 'pointer',
                padding: '2px 6px',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
              }}
            >
              ESC
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: '13px', color: 'var(--color-ink)', lineHeight: 1.5 }}>
            Access to this Monika trading node is protected. Enter your <strong>DASHBOARD_API_KEY</strong> to authenticate telemetry feeds, risk controls, and execution surfaces.
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label
              htmlFor="dashboard-api-key-input"
              style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}
            >
              API Key / Access Token
            </label>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <input
                id="dashboard-api-key-input"
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  if (errorMsg) setErrorMsg('');
                }}
                placeholder="Enter DASHBOARD_API_KEY from .env"
                autoFocus
                style={{
                  width: '100%',
                  padding: '8px 48px 8px 10px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  border: errorMsg ? '1px solid var(--color-loss)' : '1px solid var(--color-border)',
                  borderRadius: '2px',
                  background: 'var(--color-surface-well)',
                  color: 'var(--color-ink)',
                }}
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                style={{
                  position: 'absolute',
                  right: '8px',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--color-ink-soft)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  padding: '4px',
                }}
              >
                {showKey ? 'HIDE' : 'SHOW'}
              </button>
            </div>
            {errorMsg && (
              <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-loss)' }}>
                {errorMsg}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input
              id="remember-token"
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            <label
              htmlFor="remember-token"
              style={{ fontSize: '12px', color: 'var(--color-ink)', cursor: 'pointer' }}
            >
              Remember key on this browser (localStorage)
            </label>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-surface-well)',
              border: '1px solid var(--color-border)',
              borderRadius: '2px',
              fontSize: '12px',
              color: 'var(--color-ink-soft)',
              lineHeight: 1.4,
            }}
          >
            <strong>Where is this key?</strong> Configured in your host environment under <code>DASHBOARD_API_KEY</code>.
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '4px' }}>
            {onClose && (
              <TypewriterButton type="button" variant="secondary" onClick={onClose}>
                Cancel
              </TypewriterButton>
            )}
            <TypewriterButton type="submit" variant="primary">
              Authenticate & Connect
            </TypewriterButton>
          </div>
        </form>
      </div>
    </div>
  );
};
