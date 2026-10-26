import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  retry = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <h1>
            渲染错误
          </h1>
          <p>
            {this.state.error.message}
          </p>
          <button
            
            onClick={this.retry}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
