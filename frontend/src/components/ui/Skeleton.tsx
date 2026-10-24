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
  borderRadius = '2px',
  className = '',
  style,
}) => {
  return (
    <div
      className={className}
      style={{
        width,
        height,
        borderRadius,
        background: 'var(--color-surface-well)',
        border: '1px solid var(--color-border)',
        opacity: 0.7,
        animation: 'pulse 1.8s ease-in-out infinite',
        ...style,
      }}
    />
  );
};

export const SkeletonCard: React.FC<SkeletonProps> = (props) => (
  <div
    className="editorial-section"
    style={{
      background: 'var(--color-surface)',
      borderTop: '1px solid var(--color-border)',
      borderBottom: '1px solid var(--color-border)',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
    }}
  >
    <Skeleton height="16px" width="40%" {...props} />
    <Skeleton height="36px" width="100%" {...props} />
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
