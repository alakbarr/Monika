import React from 'react';

interface IconProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
  color?: string;
}

/** 1. Vintage brass magnifying glass - Search & inspection */
export const BrassMagnifierIcon: React.FC<IconProps> = ({ size = 20, color = 'currentColor', ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <circle cx="10.5" cy="10.5" r="7" />
    <circle cx="10.5" cy="10.5" r="5" strokeDasharray="2 3" opacity="0.6" />
    <line x1="15.5" y1="15.5" x2="21.5" y2="21.5" strokeWidth="2.5" />
    <path d="M19 19L21.5 21.5" strokeWidth="3" />
  </svg>
);

/** 2. Brass Morse telegraph key - Agent triggers & execution */
export const TelegraphKeyIcon: React.FC<IconProps> = ({ size = 20, color = 'currentColor', ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    {/* Base plate */}
    <rect x="2" y="18" width="20" height="3" rx="0.5" />
    {/* Fulcrum pillar */}
    <rect x="7" y="12" width="3" height="6" />
    <circle cx="8.5" cy="12" r="1.5" fill={color} />
    {/* Lever arm */}
    <line x1="4" y1="13" x2="19" y2="9" strokeWidth="2" />
    {/* Contact point */}
    <circle cx="18" cy="15" r="1.5" />
    <line x1="18" y1="9" x2="18" y2="13.5" strokeWidth="2" />
    {/* Key knob */}
    <rect x="16" y="5" width="4" height="4" rx="1" fill={color} />
  </svg>
);

/** 3. Banking wax seal stamp - Transaction confirmations & approvals */
export const WaxSealStampIcon: React.FC<IconProps> = ({ size = 20, color = 'currentColor', ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    {/* Stamp handle */}
    <path d="M10 2H14V5C14 6.5 15.5 8 16 9C16.5 10 17 11 17 13H7C7 11 7.5 10 8 9C8.5 8 10 6.5 10 5V2Z" />
    <circle cx="12" cy="3" r="1" fill={color} />
    {/* Stamp base ring */}
    <ellipse cx="12" cy="15" rx="8" ry="3" />
    {/* Stamp imprint / seal */}
    <path d="M6 18C7.5 19.5 9.5 21 12 21C14.5 21 16.5 19.5 18 18" strokeDasharray="2 2" />
    <circle cx="12" cy="15" r="1.5" fill={color} />
  </svg>
);

/** 4. Navigational compass - Portfolio allocation & strategy directional bias */
export const CompassIcon: React.FC<IconProps> = ({ size = 20, color = 'currentColor', ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="8" strokeDasharray="1 3" opacity="0.6" />
    {/* Compass needle */}
    <polygon points="12,4 15,12 12,14 9,12" fill={color} />
    <polygon points="12,20 15,12 12,14 9,12" opacity="0.4" />
    <circle cx="12" cy="12" r="1.5" fill="var(--color-paper)" />
  </svg>
);

/** 5. Steel-brass vault door - Risk parameters & capital safety controls */
export const SafeDoorIcon: React.FC<IconProps> = ({ size = 20, color = 'currentColor', ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    {/* Safe body */}
    <rect x="3" y="3" width="18" height="18" rx="1" />
    {/* Safe door inner frame */}
    <rect x="5" y="5" width="14" height="14" rx="0.5" strokeDasharray="3 3" opacity="0.5" />
    {/* Combination dial */}
    <circle cx="12" cy="12" r="3.5" />
    <circle cx="12" cy="12" r="1" fill={color} />
    {/* Dial spoke handle */}
    <line x1="12" y1="7" x2="12" y2="8.5" />
    <line x1="12" y1="15.5" x2="12" y2="17" />
    <line x1="7" y1="12" x2="8.5" y2="12" />
    <line x1="15.5" y1="12" x2="17" y2="12" />
    {/* Hinges */}
    <rect x="2" y="6" width="2" height="3" fill={color} />
    <rect x="2" y="15" width="2" height="3" fill={color} />
  </svg>
);

/** 6. Paper ticker tape roll - Market tick activity & trade ledger history */
export const TickerTapeRollIcon: React.FC<IconProps> = ({ size = 20, color = 'currentColor', ...props }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    {/* Tape spool */}
    <circle cx="7" cy="8" r="5" />
    <circle cx="7" cy="8" r="2" fill={color} />
    {/* Unfurling paper ribbon */}
    <path d="M7 13C7 16 10 18 14 18H22" strokeWidth="2" />
    <path d="M12 8H20C21.1 8 22 8.9 22 10V14C22 15.1 21.1 16 20 16H13" />
    {/* Printed dots on ribbon */}
    <circle cx="14" cy="12" r="0.75" fill={color} />
    <circle cx="17" cy="12" r="0.75" fill={color} />
    <circle cx="20" cy="12" r="0.75" fill={color} />
  </svg>
);
