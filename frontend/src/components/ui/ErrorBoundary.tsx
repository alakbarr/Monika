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
          style={{
            padding: '20px',
            margin: '16px 0',
            borderRadius: '2px',
            background: 'var(--color-loss-soft)',
            border: '1px solid var(--color-loss)',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.06em',
                padding: '2px 7px',
                color: 'var(--color-loss)',
                border: '1px solid var(--color-loss)',
                borderRadius: '2px',
              }}
            >
              SYSTEM FAULT
            </span>
            <span style={{ fontWeight: 600, fontSize: '13px', fontFamily: 'var(--font-mono)' }}>
              PANEL RENDERING EXCEPTION
            </span>
          </div>
          <p
            style={{
              fontSize: '12px',
              color: 'var(--color-ink-muted)',
              marginBottom: '12px',
              wordBreak: 'break-word',
            }}
          >
            {this.state.error?.message || 'A system exception occurred while rendering this telemetry panel.'}
          </p>
          <button
            onClick={this.handleReset}
            className="editorial-btn"
            style={{ fontSize: '11px' }}
          >
            RETRY COMPONENT
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
