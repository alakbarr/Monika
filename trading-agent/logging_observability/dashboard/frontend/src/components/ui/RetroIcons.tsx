// ==============================================================================
// File: src/components/ui/RetroIcons.tsx
// Description: Pure SVG Retro Vector Icons inspired by 90s OS (vintage-ui.jpg)
// ==============================================================================

import React from 'react';

export interface RetroIconProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
  className?: string;
}

/** 1. Yellow Desktop Folder with paper insert */
export const FolderDeskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Rear folder tab */}
    <path
      d="M3 6.5C3 5.67 3.67 5 4.5 5H9.2C9.7 5 10.18 5.25 10.46 5.66L11.8 7.5H19.5C20.33 7.5 21 8.17 21 9V17.5C21 18.33 20.33 19 19.5 19H4.5C3.67 19 3 18.33 3 17.5V6.5Z"
      fill="#E5A823"
      stroke="#1C1917"
      strokeWidth="2"
      strokeLinejoin="round"
    />
    {/* White document slip inside folder */}
    <rect x="6" y="4" width="10" height="7" rx="1" fill="#FAF7F2" stroke="#1C1917" strokeWidth="1.5" />
    <line x1="8" y1="6.5" x2="14" y2="6.5" stroke="#877F75" strokeWidth="1.2" strokeLinecap="round" />
    <line x1="8" y1="8.5" x2="12" y2="8.5" stroke="#877F75" strokeWidth="1.2" strokeLinecap="round" />
    {/* Front folder flap */}
    <path
      d="M3 10C3 9.45 3.45 9 4 9H20C20.55 9 21 9.45 21 10V17.5C21 18.33 20.33 19 19.5 19H4.5C3.67 19 3 18.33 3 17.5V10Z"
      fill="#F5BD38"
      stroke="#1C1917"
      strokeWidth="2"
      strokeLinejoin="round"
    />
  </svg>
);

/** 2. Retro CRT Terminal Monitor */
export const CrtMonitorIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Beige CRT casing */}
    <rect x="2.5" y="3" width="19" height="13" rx="2" fill="#EFE9DF" stroke="#1C1917" strokeWidth="2" />
    {/* Glass CRT screen */}
    <rect x="4.5" y="5" width="15" height="9" rx="1" fill="#3BA4C4" stroke="#1C1917" strokeWidth="1.5" />
    {/* Pixel face on screen */}
    <circle cx="9" cy="8.5" r="1" fill="#1C1917" />
    <circle cx="15" cy="8.5" r="1" fill="#1C1917" />
    <path d="M10 11C10.5 12 13.5 12 14 11" stroke="#1C1917" strokeWidth="1.2" strokeLinecap="round" />
    {/* Monitor neck & stand */}
    <path d="M9 16V18H15V16" stroke="#1C1917" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <rect x="6" y="18" width="12" height="3" rx="1" fill="#D8D2C2" stroke="#1C1917" strokeWidth="2" />
  </svg>
);

/** 3. 3.5-inch Floppy Disk */
export const FloppyDiskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Charcoal diskette body */}
    <path
      d="M4 3.5C4 2.67 4.67 2 5.5 2H17.5L21 5.5V20.5C21 21.33 20.33 22 19.5 22H4.5C3.67 22 3 21.33 3 20.5V4.5C3 3.67 3.67 3 4.5 3H5.5"
      fill="#24201D"
      stroke="#1C1917"
      strokeWidth="2"
      strokeLinejoin="round"
    />
    {/* Silver metal shutter */}
    <rect x="7" y="2" width="10" height="7" rx="0.5" fill="#D8D2C2" stroke="#1C1917" strokeWidth="1.5" />
    <rect x="12" y="4" width="2.5" height="4" fill="#1C1917" />
    {/* Cyan paper label */}
    <rect x="6" y="11" width="12" height="9" rx="1" fill="#3BA4C4" stroke="#1C1917" strokeWidth="1.5" />
    <line x1="8" y1="14" x2="16" y2="14" stroke="#FAF7F2" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="8" y1="17" x2="13" y2="17" stroke="#FAF7F2" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

/** 4. Classic Salmon Postal Mail Envelope */
export const MailDeskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Salmon envelope body */}
    <rect x="3" y="5" width="18" height="14" rx="2" fill="#E86C53" stroke="#1C1917" strokeWidth="2" />
    {/* Envelope fold flap */}
    <path d="M6 7L12 12L18 7" stroke="#1C1917" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    {/* Side creases */}
    <path d="M3 17L9 11M21 17L15 11" stroke="#1C1917" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

/** 5. Spiral Notebook Ledger */
export const NotebookDeskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Cream pad paper */}
    <rect x="5" y="3" width="15" height="18" rx="1.5" fill="#FAF7F2" stroke="#1C1917" strokeWidth="2" />
    {/* Spiral rings */}
    <circle cx="4.5" cy="6" r="1.5" fill="#C49A45" stroke="#1C1917" strokeWidth="1.2" />
    <circle cx="4.5" cy="10" r="1.5" fill="#C49A45" stroke="#1C1917" strokeWidth="1.2" />
    <circle cx="4.5" cy="14" r="1.5" fill="#C49A45" stroke="#1C1917" strokeWidth="1.2" />
    <circle cx="4.5" cy="18" r="1.5" fill="#C49A45" stroke="#1C1917" strokeWidth="1.2" />
    {/* Ledger lines */}
    <line x1="8" y1="7" x2="16" y2="7" stroke="#3BA4C4" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="8" y1="11" x2="17" y2="11" stroke="#877F75" strokeWidth="1.2" strokeLinecap="round" />
    <line x1="8" y1="15" x2="15" y2="15" stroke="#877F75" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
);

/** 6. Brass Morse Telegraph Key */
export const TelegraphDeskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Base plate */}
    <rect x="2" y="18" width="20" height="3" rx="0.5" fill="#5C544C" stroke="#1C1917" strokeWidth="2" />
    {/* Brass fulcrum pillar */}
    <rect x="7" y="12" width="3" height="6" fill="#C49A45" stroke="#1C1917" strokeWidth="1.5" />
    <circle cx="8.5" cy="12" r="1.5" fill="#F5BD38" />
    {/* Lever arm */}
    <line x1="4" y1="13" x2="19" y2="9" stroke="#1C1917" strokeWidth="2.5" strokeLinecap="round" />
    {/* Contact point */}
    <line x1="18" y1="9" x2="18" y2="14" stroke="#C49A45" strokeWidth="2" />
    <circle cx="18" cy="15" r="1.5" fill="#F5BD38" stroke="#1C1917" strokeWidth="1" />
    {/* Telegraph knob */}
    <rect x="16" y="5" width="4" height="4" rx="1" fill="#1C1917" />
  </svg>
);

/** 7. Bank Wax Seal Stamp */
export const WaxSealDeskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Red wax seal */}
    <ellipse cx="12" cy="14" rx="8" ry="7" fill="#E25B45" stroke="#1C1917" strokeWidth="2" />
    <circle cx="12" cy="14" r="5" fill="#B04A36" stroke="#1C1917" strokeWidth="1.5" strokeDasharray="2 2" />
    <path d="M10 12L12 16L14 12" stroke="#FAF7F2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    {/* Wooden/brass handle */}
    <path d="M10 2H14V5C14 6.5 13 8 12 9C11 8 10 6.5 10 5V2Z" fill="#C49A45" stroke="#1C1917" strokeWidth="1.5" />
  </svg>
);

/** 8. Meridian Globe */
export const GlobeDeskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    <circle cx="12" cy="12" r="9" fill="#3BA4C4" stroke="#1C1917" strokeWidth="2" />
    {/* Equator */}
    <line x1="3" y1="12" x2="21" y2="12" stroke="#1C1917" strokeWidth="1.5" />
    {/* Meridian */}
    <ellipse cx="12" cy="12" rx="4.5" ry="9" stroke="#1C1917" strokeWidth="1.5" />
    <line x1="12" y1="3" x2="12" y2="21" stroke="#1C1917" strokeWidth="1.5" />
  </svg>
);

/** 9. Retro Desktop Recycle Bin */
export const TrashDeskIcon: React.FC<RetroIconProps> = ({ size = 20, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Bin lid */}
    <rect x="5" y="4" width="14" height="3" rx="1" fill="#D8D2C2" stroke="#1C1917" strokeWidth="2" />
    <rect x="9.5" y="2" width="5" height="2" rx="0.5" fill="#1C1917" />
    {/* Bin canister */}
    <path d="M6 7L7.5 20C7.6 20.6 8.1 21 8.7 21H15.3C15.9 21 16.4 20.6 16.5 20L18 7" fill="#EFE9DF" stroke="#1C1917" strokeWidth="2" />
    <line x1="10" y1="10" x2="10" y2="17" stroke="#877F75" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="14" y1="10" x2="14" y2="17" stroke="#877F75" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

/** 10. Typewriter Audio Toggle Switch (Speaker / Mute) */
export const AudioToggleIcon: React.FC<RetroIconProps & { muted?: boolean }> = ({ size = 20, muted = false, className, ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    {...props}
  >
    {/* Speaker horn */}
    <path d="M4 8H7L12 4V20L7 16H4C3.45 16 3 15.55 3 15V9C3 8.45 3.45 8 4 8Z" fill="#F5BD38" stroke="#1C1917" strokeWidth="2" strokeLinejoin="round" />
    {muted ? (
      <>
        {/* Mute cross */}
        <line x1="16" y1="9" x2="21" y2="14" stroke="#E25B45" strokeWidth="2" strokeLinecap="round" />
        <line x1="21" y1="9" x2="16" y2="14" stroke="#E25B45" strokeWidth="2" strokeLinecap="round" />
      </>
    ) : (
      <>
        {/* Audio waves */}
        <path d="M15.5 8.5C16.5 9.5 17 10.7 17 12C17 13.3 16.5 14.5 15.5 15.5" stroke="#1C1917" strokeWidth="2" strokeLinecap="round" />
        <path d="M18.5 5.5C20.5 7.5 21.5 9.7 21.5 12C21.5 14.3 20.5 16.5 18.5 18.5" stroke="#1C1917" strokeWidth="2" strokeLinecap="round" />
      </>
    )}
  </svg>
);
