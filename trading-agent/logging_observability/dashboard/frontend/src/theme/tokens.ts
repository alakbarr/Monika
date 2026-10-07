// ==============================================================================
// File: src/theme/tokens.ts
// Description: Type-Safe CSS Variable Tokens for Monika Vintage Design System
// ==============================================================================

export const colors = {
  // Surfaces & Backgrounds
  desktop: 'var(--color-desktop)',
  paper: 'var(--color-paper)',
  paperRaised: 'var(--color-paper-raised)',
  paperDark: 'var(--color-paper-dark)',
  surface: 'var(--color-surface)',
  surfaceCard: 'var(--color-surface-card)',
  surfaceHover: 'var(--color-surface-hover)',
  surfaceSubtle: 'var(--color-surface-subtle)',

  // Ink & Typography
  ink: 'var(--color-ink)',
  inkSoft: 'var(--color-ink-soft)',
  inkMuted: 'var(--color-ink-muted)',

  // Borders & Rules
  rule: 'var(--color-rule)',
  edge: 'var(--color-edge)',
  border: 'var(--color-border)',
  borderThick: 'var(--color-border-thick)',
  borderFocus: 'var(--color-border-focus)',

  // Vintage OS Palette
  winBlue: 'var(--color-win-blue)',
  winYellow: 'var(--color-win-yellow)',
  winSalmon: 'var(--color-win-salmon)',
  winCoral: 'var(--color-win-coral)',
  winGreen: 'var(--color-win-green)',
  winGray: 'var(--color-win-gray)',
  winDim: 'var(--color-win-dim)',
  titlebar: 'var(--color-titlebar)',
  titlebarText: 'var(--color-titlebar-text)',
  onWinBlue: 'var(--color-on-win-blue)',
  onWinYellow: 'var(--color-on-win-yellow)',
  onWinSalmon: 'var(--color-on-win-salmon)',
  onWinCoral: 'var(--color-on-win-coral)',
  onWinGreen: 'var(--color-on-win-green)',
  onWinGray: 'var(--color-on-win-gray)',

  // Accents & Financial Indicators
  brass: 'var(--color-brass)',
  brassBright: 'var(--color-brass-bright)',
  profit: 'var(--color-profit)',
  profitDim: 'var(--color-profit-dim)',
  profitBg: 'var(--color-profit-bg)',
  loss: 'var(--color-loss)',
  lossDim: 'var(--color-loss-dim)',
  lossBg: 'var(--color-loss-bg)',
  ledgerGreen: 'var(--color-ledger-green)',
  ledgerRed: 'var(--color-ledger-red)',

  // Status
  warn: 'var(--color-warn)',
  warning: 'var(--color-warning)',
  warnDim: 'var(--color-warn-dim)',
  error: 'var(--color-error)',
  active: 'var(--color-active)',
  paused: 'var(--color-paused)',
  info: 'var(--color-info)',

  // High-Contrast Text Tokens (WCAG 2.1 AA >= 4.5:1)
  textWarn: 'var(--color-text-warn)',
  textInfo: 'var(--color-text-info)',
  textAccent: 'var(--color-text-accent)',
  textProfit: 'var(--color-text-profit)',
  textLoss: 'var(--color-text-loss)',

  // Harmonized Vintage Palette Additions
  navy: 'var(--color-navy)',
  moss: 'var(--color-moss)',
  mossSubtle: 'var(--color-moss-subtle)',
  coral: 'var(--color-coral)',
  coralSubtle: 'var(--color-coral-subtle)',
  ochre: 'var(--color-ochre)',
  ochreSubtle: 'var(--color-ochre-subtle)',
  paperSubtle: 'var(--color-paper-subtle)',
  paperSunken: 'var(--color-paper-sunken)',
  paperHighlight: 'var(--color-paper-highlight)',
  surfaceActive: 'var(--color-surface-active)',
  tableHeader: 'var(--color-table-header)',
  ruleSoft: 'var(--color-rule-soft)',
  winBorder: 'var(--color-win-border)',
  accentSubtle: 'var(--color-accent-subtle)',

  // Console Phosphor Terminal
  consoleBg: 'var(--color-console-bg)',
  consolePhosphor: 'var(--color-console-phosphor)',
  consoleDim: 'var(--color-console-dim)',
  consoleBorder: 'var(--color-console-border)',
} as const;

export const fonts = {
  precision: 'var(--font-precision)',
  narrative: 'var(--font-narrative)',
  body: 'var(--font-body)',
  heading: 'var(--font-heading)',
} as const;

export const typography = {
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
  body: 'var(--text-body)',
  sm: 'var(--text-sm)',
  caption: 'var(--text-caption)',
  xs: 'var(--text-xs)',
} as const;

export const shadows = {
  card: 'var(--shadow-card)',
  elevated: 'var(--shadow-elevated)',
  btn: 'var(--shadow-btn)',
  dropdown: 'var(--shadow-dropdown)',
  modal: 'var(--shadow-modal)',
} as const;

export const radii = {
  xs: 'var(--radius-xs)',
  sm: 'var(--radius-sm)',
  md: 'var(--radius-md)',
  lg: 'var(--radius-lg)',
  card: 'var(--radius-card)',
  control: 'var(--radius-control)',
} as const;

export const tokens = {
  colors,
  fonts,
  typography,
  shadows,
  radii,
} as const;

export default tokens;
