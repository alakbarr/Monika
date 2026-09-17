import React from 'react';

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  className?: string;
  style?: React.CSSProperties;
}

export const Skeleton: React.FC<SkeletonProps> = ({ 
  width = '100%', 
  height = '20px', 
  borderRadius = 'var(--radius-sm)',
  className = '',
  style 
}) => {
  return (
    <div
      className={className}
      style={{
        width,
        height,
        borderRadius,
        background: 'var(--color-paper)',
        border: '1px solid var(--color-rule)',
        opacity: 0.7,
        animation: 'pulse 1.8s ease-in-out infinite',
        ...style,
      }}
    />
  );
};

export const SkeletonCard: React.FC<SkeletonProps> = (props) => (
  <div
    className="win-window ledger-card"
    style={{
      background: 'var(--color-paper-raised)',
      border: '2px solid var(--color-rule)',
      borderRadius: 'var(--radius-card)',
      boxShadow: 'var(--shadow-card)',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
    }}
  >
    <Skeleton height="20px" width="40%" {...props} />
    <Skeleton height="40px" width="100%" {...props} />
    <Skeleton height="14px" width="60%" {...props} />
  </div>
);

export const SkeletonText: React.FC<{ rows?: number; width?: string } & SkeletonProps> = ({ 
  rows = 3, 
  width = '100%',
  ...props 
}) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width }}>
    {Array.from({ length: rows }).map((_, i) => (
      <Skeleton 
        key={i} 
        height="14px" 
        width={i === rows - 1 ? '70%' : '100%'} 
        {...props} 
      />
    ))}
  </div>
);
