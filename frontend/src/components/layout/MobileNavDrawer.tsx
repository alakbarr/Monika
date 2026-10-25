import React from 'react';

interface NavItem {
  id: string;
  label: string;
  icon?: React.ElementType;
}

interface MobileNavDrawerProps {
  isOpen: boolean;
  activeTab: string;
  tabs: NavItem[];
  onSelectTab: (tabId: string) => void;
  onClose: () => void;
}

export const MobileNavDrawer: React.FC<MobileNavDrawerProps> = ({
  isOpen,
  activeTab,
  tabs,
  onSelectTab,
  onClose,
}) => {
  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Navigation Menu"
      className="retro-modal-scrim"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9000,
        display: 'flex',
        fontFamily: 'var(--font-sans)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '280px',
          height: '100%',
          background: 'var(--color-surface)',
          borderRight: '1px solid var(--color-border-strong)',
          boxShadow: 'var(--shadow-modal)',
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid var(--color-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--color-surface-well)',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            fontWeight: 600,
            letterSpacing: '0.08em',
          }}
        >
          <span>MONIKA · CHAPTER VIEWS</span>
          <button
            onClick={onClose}
            aria-label="Close navigation menu"
            style={{
              background: 'transparent',
              border: '1px solid var(--color-border)',
              color: 'var(--color-ink)',
              padding: '2px 8px',
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              cursor: 'pointer',
            }}
          >
            ESC
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', padding: '8px', gap: '2px' }}>
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  onSelectTab(tab.id);
                  onClose();
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '10px 12px',
                  borderRadius: '2px',
                  background: isActive ? 'var(--color-ink)' : 'transparent',
                  color: isActive ? 'var(--color-surface)' : 'var(--color-ink-muted)',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  fontWeight: isActive ? 600 : 500,
                }}
              >
                {Icon && <Icon size={15} strokeWidth={1.5} color="currentColor" />}
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
