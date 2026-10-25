// ==============================================================================
// File: src/theme/tokens.ts
// Description: Swiss Editorial & Unboxed Sculptural Design System Tokens
// Centralizes all CSS variable references and Canvas/WebGL hex palettes so zero
// raw hex literals appear in component .tsx files (G1 Token Integrity).
// ==============================================================================

import type { ITheme } from '@xterm/xterm';

export const colors = {
  // Architectural Surfaces & Swiss Liquid Glass v4.0
  canvas: 'var(--color-canvas)',
  well: 'var(--color-well)',
  wellHover: 'var(--color-well-hover)',
  wellSunken: 'var(--color-well-sunken)',
  surfaceElevated: 'var(--color-surface-elevated)',
  glassSurface: 'var(--color-glass-surface)',
  glassSurfaceElevated: 'var(--color-glass-surface-elevated)',
  glassChrome: 'var(--color-glass-chrome)',
  glassDock: 'var(--color-glass-dock)',
  glassBorder: 'var(--color-glass-border)',
  glassSpecularTop: 'var(--color-glass-specular-top)',
  dockBg: 'var(--color-dock-bg)',
  dockFg: 'var(--color-dock-fg)',

  // Backward-compatible surface aliases
  desktop: 'var(--color-canvas)',
  paper: 'var(--color-well)',
  paperRaised: 'var(--color-canvas)',
  surface: 'var(--color-well)',
  surfaceCard: 'var(--color-canvas)',
  surfaceHover: 'var(--color-well-hover)',
  surfaceSubtle: 'var(--color-well)',

  // Ink Hierarchy
  ink: 'var(--color-ink)',
  inkSecondary: 'var(--color-ink-secondary)',
  inkMuted: 'var(--color-ink-muted)',
  inkSoft: 'var(--color-ink-secondary)',
  textPrimary: 'var(--color-ink)',
  textSecondary: 'var(--color-ink-secondary)',
  textMuted: 'var(--color-ink-muted)',
  textWhite: 'var(--color-ink)',

  // Architectural Hairline Rules
  rule: 'var(--color-rule)',
  ruleStrong: 'var(--color-rule-strong)',
  border: 'var(--color-rule)',
  borderStrong: 'var(--color-rule-strong)',
  borderFocus: 'var(--color-ink)',

  // Semantic Financial Truth
  gain: 'var(--color-gain)',
  gainBg: 'var(--color-gain-bg)',
  gainBorder: 'var(--color-gain-border)',
  loss: 'var(--color-loss)',
  lossBg: 'var(--color-loss-bg)',
  lossBorder: 'var(--color-loss-border)',
  warn: 'var(--color-warn)',
  warnBg: 'var(--color-warn-bg)',
  warnBorder: 'var(--color-warn-border)',
  info: 'var(--color-info)',
  infoBg: 'var(--color-info-bg)',
  infoBorder: 'var(--color-info-border)',

  // Legacy Semantic Aliases
  primary: 'var(--color-ink)',
  primaryActive: 'var(--color-primary-active)',
  primaryDim: 'var(--color-primary-dim)',
  brass: 'var(--color-warn)',
  brassBright: 'var(--color-warn)',
  ledgerGreen: 'var(--color-gain)',
  ledgerRed: 'var(--color-loss)',
  profit: 'var(--color-gain)',
  profitDim: 'var(--color-gain-bg)',
  lossDim: 'var(--color-loss-bg)',
  warnDim: 'var(--color-warn-bg)',
  active: 'var(--color-gain)',
  paused: 'var(--color-warn)',
  error: 'var(--color-loss)',

  // Console
  consoleBg: 'var(--color-console-bg)',
  consolePhosphor: 'var(--color-console-phosphor)',
  consoleDim: 'var(--color-console-dim)',
} as const;

export const fonts = {
  editorial: 'var(--font-editorial)',
  sans: 'var(--font-sans)',
  mono: 'var(--font-mono)',
  precision: 'var(--font-mono)',
  narrative: 'var(--font-sans)',
  display: 'var(--font-editorial)',
  number: 'var(--font-mono)',
} as const;

export const fontSizes = {
  monument: 'var(--text-monument)',
  hero: 'var(--text-hero)',
  displayLg: 'var(--text-display-lg)',
  displayMd: 'var(--text-display-md)',
  displaySm: 'var(--text-display-sm)',
  titleLg: 'var(--text-title-lg)',
  titleMd: 'var(--text-title-md)',
  titleSm: 'var(--text-title-sm)',
  titleXs: 'var(--text-title-xs)',
  bodyLg: 'var(--text-body-lg)',
  bodyMd: 'var(--text-body-md)',
  bodySm: 'var(--text-body-sm)',
  caption: 'var(--text-caption)',
  xs: 'var(--text-xs)',
} as const;

export const radii = {
  xs: 'var(--radius-xs)',
  sm: 'var(--radius-sm)',
  md: 'var(--radius-md)',
  lg: 'var(--radius-lg)',
  xl: 'var(--radius-xl)',
  pill: 'var(--radius-pill)',
  card: 'var(--radius-card)',
} as const;

/**
 * Lightweight-Charts Canvas Palette (requires resolved hex/rgba strings for HTML5 Canvas)
 */
export const getChartPalette = (isLight: boolean) => ({
  background: isLight ? '#FFFFFF' : '#121316',
  textColor: isLight ? '#525660' : '#9CA3AF',
  gridColor: isLight ? 'rgba(17, 18, 21, 0.05)' : 'rgba(243, 244, 246, 0.05)',
  borderScale: isLight ? '#E5E7EB' : '#23262D',
  upColor: isLight ? '#0D7A52' : '#10B981',
  downColor: isLight ? '#C82838' : '#F43F5E',
  obBull: isLight ? '#0D7A52' : '#10B981',
  obBear: isLight ? '#C82838' : '#F43F5E',
  fvgBull: isLight ? '#1D4ED8' : '#60A5FA',
  fvgBear: isLight ? '#9A5B00' : '#F59E0B',
  chochColor: isLight ? '#9A5B00' : '#F59E0B',
  bosColor: isLight ? '#111215' : '#F3F4F6',
  timesfmMedian: isLight ? '#1D4ED8' : '#60A5FA',
  timesfmCone: isLight ? 'rgba(29, 78, 216, 0.28)' : 'rgba(96, 165, 250, 0.28)',
});

/**
 * XTerm.js Terminal Themes (Swiss Editorial Light & Obsidian Dark)
 */
export const DARK_TERMINAL_THEME: ITheme = {
  background: '#0E0F12',
  foreground: '#F3F4F6',
  cursor: '#10B981',
  cursorAccent: '#0E0F12',
  selectionBackground: 'rgba(243, 244, 246, 0.2)',
  selectionForeground: '#FFFFFF',
  black: '#121316',
  red: '#F43F5E',
  green: '#10B981',
  yellow: '#F59E0B',
  blue: '#60A5FA',
  magenta: '#A78BFA',
  cyan: '#34D399',
  white: '#F3F4F6',
  brightBlack: '#686D78',
  brightRed: '#FB7185',
  brightGreen: '#34D399',
  brightYellow: '#FBBF24',
  brightBlue: '#93C5FD',
  brightMagenta: '#C4B5FD',
  brightCyan: '#6EE7B7',
  brightWhite: '#FFFFFF',
};

export const LIGHT_TERMINAL_THEME: ITheme = {
  background: '#FFFFFF',
  foreground: '#111215',
  cursor: '#111215',
  cursorAccent: '#FFFFFF',
  selectionBackground: 'rgba(17, 18, 21, 0.14)',
  selectionForeground: '#111215',
  black: '#111215',
  red: '#C82838',
  green: '#0D7A52',
  yellow: '#9A5B00',
  blue: '#1D4ED8',
  magenta: '#6D28D9',
  cyan: '#0F766E',
  white: '#F7F8FA',
  brightBlack: '#525660',
  brightRed: '#E11D48',
  brightGreen: '#059669',
  brightYellow: '#B45309',
  brightBlue: '#2563EB',
  brightMagenta: '#7C3AED',
  brightCyan: '#0D9488',
  brightWhite: '#FFFFFF',
};
