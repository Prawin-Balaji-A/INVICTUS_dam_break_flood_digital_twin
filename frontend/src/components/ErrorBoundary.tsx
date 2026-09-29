import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  // Rendered instead of children when a descendant throws during render.
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
  // Called after an error is caught (e.g. to close a modal so the app is usable).
  onError?: (error: Error) => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

// Class error boundary: a failed AI request/render can never blank the whole
// app. It isolates its subtree — if a child throws, only the fallback shows and
// the rest of the twin keeps running.
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error('[ErrorBoundary] caught render error:', error);
    this.props.onError?.(error);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback(this.state.error, this.reset);
      return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="bg-slate-900 border border-red-700/50 rounded-xl max-w-md w-full p-6 text-slate-200 shadow-2xl space-y-3">
            <h2 className="text-base font-bold text-red-300">Something went wrong</h2>
            <p className="text-xs text-slate-400 font-mono break-words">{this.state.error.message}</p>
            <button
              onClick={this.reset}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
            >
              Dismiss
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
