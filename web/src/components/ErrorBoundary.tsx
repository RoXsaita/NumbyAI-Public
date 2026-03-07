/**
 * React Error Boundary Component
 * 
 * Catches JavaScript errors in child component tree and displays
 * a fallback UI instead of crashing the whole widget.
 * 
 * Usage:
 *   <ErrorBoundary fallback={<ErrorFallback />}>
 *     <Dashboard />
 *   </ErrorBoundary>
 */

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { createLogger } from '../shared/logger';

const logger = createLogger('ErrorBoundary');

// ============================================================================
// TYPES
// ============================================================================

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

// ============================================================================
// DEFAULT FALLBACK UI
// ============================================================================

interface ErrorFallbackProps {
  error: Error | null;
  onRetry?: () => void;
}

export const ErrorFallback: React.FC<ErrorFallbackProps> = ({ error, onRetry }) => {
  return (
    <div
      style={{
        padding: 24,
        textAlign: 'center',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        color: '#374151',
        backgroundColor: '#fef2f2',
        border: '1px solid #fecaca',
        borderRadius: 8,
        margin: 16,
      }}
    >
      <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
      <h2 style={{ 
        margin: '0 0 8px 0', 
        fontSize: 18, 
        fontWeight: 600,
        color: '#991b1b',
      }}>
        Something went wrong
      </h2>
      <p style={{ 
        margin: '0 0 16px 0', 
        fontSize: 14, 
        color: '#7f1d1d',
      }}>
        The dashboard encountered an error and couldn't display.
      </p>
      {error && (
        <details
          style={{
            textAlign: 'left',
            backgroundColor: '#fff',
            padding: 12,
            borderRadius: 6,
            marginBottom: 16,
            fontSize: 12,
            overflow: 'auto',
            maxHeight: 200,
          }}
        >
          <summary style={{ cursor: 'pointer', fontWeight: 500, marginBottom: 8 }}>
            Error Details
          </summary>
          <pre style={{ 
            margin: 0, 
            whiteSpace: 'pre-wrap', 
            wordBreak: 'break-word',
            color: '#dc2626',
          }}>
            {error.message}
          </pre>
        </details>
      )}
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            padding: '10px 20px',
            fontSize: 14,
            fontWeight: 500,
            color: '#fff',
            backgroundColor: '#dc2626',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
          }}
        >
          Try Again
        </button>
      )}
    </div>
  );
};

// ============================================================================
// ERROR BOUNDARY CLASS COMPONENT
// ============================================================================

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // Update state so the next render shows the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log the error
    logger.error('React component error', error, {
      componentStack: errorInfo.componentStack,
    });

    // Update state with error info
    this.setState({ errorInfo });

    // Call optional error handler
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // Render custom fallback or default fallback
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <ErrorFallback 
          error={this.state.error} 
          onRetry={this.handleRetry}
        />
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;

