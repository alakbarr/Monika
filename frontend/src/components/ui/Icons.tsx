// ==============================================================================
// File: src/components/ui/Icons.tsx
// Description: Architectural Linework Icons for Monika Swiss Editorial Desk
// Zero raw hex literals — inherits CSS custom properties (--color-ink, etc.)
// ==============================================================================

import React from 'react';

export interface IconProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
  className?: string;
}

/** 1. Chapter II — Editorial Journal & Dossier Icon */
export const FolderDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <path
      d="M4 4.5H14L19 9.5V19.5H4V4.5Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path d="M14 4.5V9.5H19" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <line x1="7.5" y1="13" x2="15.5" y2="13" stroke="currentColor" strokeWidth="1.5" />
    <line x1="7.5" y1="16" x2="12.5" y2="16" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

/** 2. Chapter I — Capital & Sculptural Monument Icon */
export const CrtMonitorIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <path
      d="M3 17L9 11L13 14.5L21 6.5"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="square"
      strokeLinejoin="miter"
    />
    <path d="M16 6.5H21V11.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" />
    <line x1="3" y1="20" x2="21" y2="20" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

/** 3. Chapter V — Atelier & System Architecture Icon */
export const FloppyDiskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <rect x="3.5" y="3.5" width="17" height="17" stroke="currentColor" strokeWidth="1.5" />
    <line x1="3.5" y1="9" x2="20.5" y2="9" stroke="currentColor" strokeWidth="1.5" />
    <line x1="9" y1="9" x2="9" y2="20.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

/** 4. Dispatch Envelope Icon */
export const MailDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <rect x="3" y="5" width="18" height="14" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 6L12 13L21 6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
);

/** 5. Chapter III — Mechanical Fortress & Risk Ledger Icon */
export const NotebookDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <path
      d="M12 3L19.5 6.5V12C19.5 16.5 16.3 19.8 12 21C7.7 19.8 4.5 16.5 4.5 12V6.5L12 3Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path d="M9 12L11 14L15 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" />
  </svg>
);

/** 6. Chapter IV — Quantitative Lab & Telemetry Icon */
export const TelegraphDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.5" />
    <line x1="12" y1="3.5" x2="12" y2="20.5" stroke="currentColor" strokeWidth="1.2" />
    <line x1="3.5" y1="12" x2="20.5" y2="12" stroke="currentColor" strokeWidth="1.2" />
    <circle cx="12" cy="12" r="2.5" fill="currentColor" />
  </svg>
);

/** 7. Verification Seal Icon */
export const WaxSealDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.2" strokeDasharray="2 2" />
    <path d="M9.5 12L11.2 13.8L14.8 10.2" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

/** 8. Global Macro Meridian Icon */
export const GlobeDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
    <line x1="3" y1="12" x2="21" y2="12" stroke="currentColor" strokeWidth="1.3" />
    <ellipse cx="12" cy="12" rx="4.5" ry="9" stroke="currentColor" strokeWidth="1.3" />
  </svg>
);

/** 9. Prune / Archive Icon */
export const TrashDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <line x1="4" y1="6" x2="20" y2="6" stroke="currentColor" strokeWidth="1.5" />
    <path d="M6.5 6V19.5H17.5V6" stroke="currentColor" strokeWidth="1.5" />
    <path d="M9 6V4H15V6" stroke="currentColor" strokeWidth="1.5" />
    <line x1="10" y1="10" x2="10" y2="16" stroke="currentColor" strokeWidth="1.3" />
    <line x1="14" y1="10" x2="14" y2="16" stroke="currentColor" strokeWidth="1.3" />
  </svg>
);

/** 10. Audio Feedback Toggle Icon */
export const AudioToggleIcon: React.FC<IconProps & { muted?: boolean }> = ({
  size = 16,
  muted = false,
  className,
  ...props
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <path
      d="M4 9H7.5L12.5 4.5V19.5L7.5 15H4V9Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    {muted ? (
      <>
        <line x1="16" y1="9.5" x2="21" y2="14.5" stroke="var(--color-loss)" strokeWidth="1.5" />
        <line x1="21" y1="9.5" x2="16" y2="14.5" stroke="var(--color-loss)" strokeWidth="1.5" />
      </>
    ) : (
      <>
        <path d="M16 9C17.2 10 17.8 11 17.8 12C17.8 13 17.2 14 16 15" stroke="currentColor" strokeWidth="1.5" />
        <path d="M18.8 6.5C20.6 8.2 21.5 10 21.5 12C21.5 14 20.6 15.8 18.8 17.5" stroke="currentColor" strokeWidth="1.5" />
      </>
    )}
  </svg>
);

/** 11. Precision Loupe / Search Icon */
export const MagnifierDeskIcon: React.FC<IconProps> = ({ size = 18, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" strokeWidth="1.5" />
    <line x1="15.5" y1="15.5" x2="20.5" y2="20.5" stroke="currentColor" strokeWidth="1.8" />
  </svg>
);
