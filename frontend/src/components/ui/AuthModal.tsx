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
        fontFamily: 'var(--font-precision)',
      }}
    >
      <div
        className="win-window"
        style={{
          width: '100%',
          maxWidth: '480px',
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          boxShadow: '4px 4px 0 var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Title Bar */}
        <div
          id="auth-modal-title"
          className="win-titlebar"
          style={{
            padding: '6px 12px',
            borderBottom: '2px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--color-win-titlebar)',
            color: 'var(--color-on-titlebar)',
            fontWeight: 'bold',
            fontSize: 'var(--text-body-sm)',
          }}
        >
          <span>Monika Security — Dashboard Authentication</span>
          {onClose && (
            <button
              type="button"
              className="win-control-btn"
              onClick={onClose}
              aria-label="Close authentication modal"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'inherit',
                cursor: 'pointer',
                fontWeight: 'bold',
                fontSize: '14px',
              }}
            >
              ✕
            </button>
          )}
        </div>

        {/* Content Body */}
        <form onSubmit={handleSubmit} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', lineHeight: 1.5 }}>
            Access to this Monika trading node is protected. Enter your <strong>DASHBOARD_API_KEY</strong> to authenticate telemetry feeds, risk controls, and automated trading charts.
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label
              htmlFor="dashboard-api-key-input"
              style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)' }}
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
                  padding: '8px 40px 8px 10px',
                  fontFamily: 'monospace',
                  fontSize: 'var(--text-body-sm)',
                  border: errorMsg ? '2px solid var(--color-negative)' : '1px solid var(--color-rule)',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--color-paper)',
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
                  fontSize: 'var(--text-xs)',
                  padding: '4px',
                }}
              >
                {showKey ? 'Hide' : 'Show'}
              </button>
            </div>
            {errorMsg && (
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-negative)' }}>
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
              style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink)', cursor: 'pointer' }}
            >
              Remember key on this browser (localStorage)
            </label>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: 'var(--color-paper-sunken)',
              border: '1px dashed var(--color-rule)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--text-xs)',
              color: 'var(--color-ink-soft)',
              lineHeight: 1.4,
            }}
          >
            <strong>Where is this key?</strong> Found in your VPS root directory inside the <code>.env</code> file under <code>DASHBOARD_API_KEY</code>.
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
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
