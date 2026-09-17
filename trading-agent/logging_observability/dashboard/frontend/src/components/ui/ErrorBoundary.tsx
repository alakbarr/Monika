import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error in dashboard component:', error, errorInfo);
  }

  public handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div
          className="ledger-card"
          style={{
            padding: '20px',
            margin: '16px 0',
            borderRadius: 'var(--radius-card)',
            background: 'var(--color-paper-raised)',
            border: '2px solid var(--color-ledger-red)',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-precision)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span
              className="stamp-badge"
              style={{
                color: 'var(--color-ledger-red)',
                border: '1.5px solid var(--color-ledger-red)',
                background: 'var(--color-loss-dim)',
              }}
            >
              [ SYSTEM ERROR // EXECUTION HALTED ]
            </span>
            <span style={{ fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-body-sm)' }}>
              PANEL RENDERING FAULT
            </span>
          </div>
          <p
            style={{
              fontSize: 'var(--text-body-sm)',
              color: 'var(--color-ink-soft)',
              marginBottom: '12px',
              wordBreak: 'break-word',
            }}
          >
            {this.state.error?.message || 'A system exception occurred while rendering this telemetry panel.'}
          </p>
          <button
            onClick={this.handleReset}
            className="typewriter-btn"
            style={{ fontSize: 'var(--text-xs)' }}
          >
            [ RETRY COMPONENT ]
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
