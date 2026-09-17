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
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9000,
        background: 'rgba(28, 25, 23, 0.75)',
        display: 'flex',
        fontFamily: 'var(--font-precision)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '280px',
          height: '100%',
          background: 'var(--color-paper-raised)',
          borderRight: '2px solid var(--color-rule)',
          boxShadow: '4px 0 0 var(--color-rule)',
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="win-titlebar"
          style={{
            padding: '8px 12px',
            borderBottom: '2px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--color-win-blue)',
            color: 'var(--color-titlebar-text)',
            fontWeight: 'bold',
          }}
        >
          <span>NAVIGATION // WORKSPACES</span>
          <button
            onClick={onClose}
            className="win-control-btn"
            style={{ width: '20px', height: '20px', fontSize: '12px' }}
          >
            ×
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', padding: '8px 0', gap: '2px' }}>
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
                className={`folder-tab ${isActive ? '-active' : ''}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '8px 14px',
                  margin: '1px 8px',
                  borderRadius: 'var(--radius-md)',
                  background: isActive ? 'var(--color-paper)' : 'transparent',
                  color: isActive ? 'var(--color-ink)' : 'var(--color-ink-soft)',
                  border: isActive ? '2px solid var(--color-rule)' : '2px solid transparent',
                  borderLeft: isActive ? '5px solid var(--color-win-yellow)' : '2px solid transparent',
                  boxShadow: isActive ? '2px 2px 0 var(--color-rule)' : 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: 'var(--text-body-sm)',
                }}
              >
                {Icon && <Icon size={16} strokeWidth={isActive ? 2.2 : 1.7} color={isActive ? 'var(--color-ink)' : 'currentColor'} />}
                <span style={{ fontWeight: isActive ? 'bold' : 'normal' }}>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
