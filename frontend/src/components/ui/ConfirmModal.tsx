import React from 'react';
import { TypewriterButton } from './TypewriterButton';
import { X } from 'lucide-react';

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  actionSummary: string;
  details?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  title,
  actionSummary,
  details,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}) => {
  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      className="editorial-modal-scrim"
      style={{
        zIndex: 10000,
        padding: '16px',
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '480px',
          background: 'var(--color-canvas)',
          border: `1px solid ${danger ? 'var(--color-loss)' : 'var(--color-rule-strong)'}`,
          boxShadow: 'var(--shadow-modal)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          id="confirm-modal-title"
          style={{
            padding: '14px 20px',
            borderBottom: '1px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: danger ? 'var(--color-loss)' : 'var(--color-ink)',
          }}
        >
          <span>{title}</span>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--color-ink-muted)',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
            }}
          >
            <X size={15} />
          </button>
        </div>

        <div style={{ padding: '24px 20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div
            style={{
              fontFamily: 'var(--font-editorial)',
              fontSize: 'var(--text-display-sm)',
              color: 'var(--color-ink)',
              lineHeight: 1.25,
            }}
          >
            {actionSummary}
          </div>
          {details && (
            <div
              style={{
                fontSize: 'var(--text-body-sm)',
                color: 'var(--color-ink-secondary)',
                lineHeight: 1.55,
              }}
            >
              {details}
            </div>
          )}

          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '10px',
              paddingTop: '12px',
              borderTop: '1px solid var(--color-rule)',
            }}
          >
            <TypewriterButton variant="secondary" onClick={onCancel}>
              {cancelLabel}
            </TypewriterButton>
            <TypewriterButton variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>
              {confirmLabel}
            </TypewriterButton>
          </div>
        </div>
      </div>
    </div>
  );
};
