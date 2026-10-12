import React from 'react';
import { sounds } from '../../lib/soundEffects';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface TypewriterButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: React.ReactNode;
}

export const TypewriterButton: React.FC<TypewriterButtonProps> = ({
  children,
  variant = 'secondary',
  size = 'md',
  icon,
  className = '',
  style,
  disabled,
  onClick,
  ...props
}) => {
  const sizeStyles: Record<ButtonSize, React.CSSProperties> = {
    sm: { padding: '0 10px', fontSize: 'var(--text-xs)', height: '26px', boxSizing: 'border-box' },
    md: { padding: '0 14px', fontSize: 'var(--text-body-sm)', height: '32px', boxSizing: 'border-box' },
    lg: { padding: '0 20px', fontSize: 'var(--text-body-md)', height: '40px', boxSizing: 'border-box' },
  };

  const variantClass = variant === 'primary' 
    ? 'win-btn-primary typewriter-btn-brass' 
    : variant === 'danger' 
    ? 'win-btn-danger typewriter-btn-danger' 
    : '';

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    sounds.playClick('typewriter');
    if (onClick) onClick(e);
  };

  return (
    <button
      className={`win-btn typewriter-btn ${variantClass} ${className}`}
      disabled={disabled}
      onClick={handleClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '6px',
        boxSizing: 'border-box',
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-btn)',
        ...sizeStyles[size],
        ...style,
      }}
      {...props}
    >
      {icon && <span style={{ display: 'inline-flex', alignItems: 'center' }}>{icon}</span>}
      {children}
    </button>
  );
};

export const WinButton = TypewriterButton;
