"use client";

import React from "react";
import { C } from "@/lib/theme";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Catches React render errors so the whole app doesn't show a white screen.
 * Shows a friendly Spanish message and a "Reload" button.
 * In dev, shows the error message; in prod, hides it.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Only log in dev. In prod, silent — no sensitive info leaked.
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("ErrorBoundary caught:", error, errorInfo);
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = () => {
    if (typeof window !== "undefined") window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      const isDev = process.env.NODE_ENV !== "production";
      return (
        <div style={{
          minHeight: "50vh",
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          padding: "40px 20px", textAlign: "center", fontFamily: "'DM Sans', system-ui, sans-serif",
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>😵</div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: C.text, margin: "0 0 8px" }}>
            Algo salió mal
          </h2>
          <p style={{ fontSize: 14, color: C.mute, margin: "0 0 24px", maxWidth: 440 }}>
            Ocurrió un error inesperado. Intenta recargar la página.
            Si el problema persiste, contáctanos.
          </p>
          {isDev && this.state.error && (
            <pre style={{
              fontSize: 11, color: C.red, background: C.redBg,
              padding: 12, borderRadius: 8, maxWidth: 640, overflow: "auto",
              textAlign: "left", border: `1px solid ${C.redBd}`,
            }}>
              {this.state.error.message}
            </pre>
          )}
          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            <button onClick={this.handleReset} style={{
              padding: "10px 20px", borderRadius: 8,
              border: `1px solid ${C.border}`, background: C.surface,
              color: C.text, fontWeight: 600, fontSize: 13, cursor: "pointer",
              fontFamily: "inherit",
            }}>Reintentar</button>
            <button onClick={this.handleReload} style={{
              padding: "10px 20px", borderRadius: 8,
              border: "none", background: C.accent, color: "#fff",
              fontWeight: 700, fontSize: 13, cursor: "pointer",
              fontFamily: "inherit",
            }}>Recargar página</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
