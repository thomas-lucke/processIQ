"use client";

import { cn } from "@/lib/utils";

interface HeaderProps {
  processName?: string | null;
  sessionId?: string | null;
  hasResults: boolean;
  hasNonDefaultSettings: boolean;
  pendingProcessData: boolean;
  isLoading: boolean;
  onRunAnalysis?: () => void;
  onSettingsClick?: () => void;
}

function IconSettings({ hasDot }: { hasDot: boolean }) {
  return (
    <span className="relative">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
      {hasDot && (
        <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-accent" />
      )}
    </span>
  );
}

export function Header({
  processName,
  sessionId,
  hasResults,
  hasNonDefaultSettings,
  pendingProcessData,
  isLoading,
  onRunAnalysis,
  onSettingsClick,
}: HeaderProps) {
  return (
    <header className="h-14 flex-shrink-0 flex items-center justify-between px-5 bg-dark-surface border-b border-dark-border z-10">
      {/* Left — wordmark (only shown when rail is collapsed, always visible in header) */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold text-ink tracking-tight">ProcessIQ</span>
        {!hasResults && (
          <span className="hidden sm:block text-xs text-ink-faint border-l border-dark-border pl-3">
            AI process optimization
          </span>
        )}
      </div>

      {/* Center — Phase 2: process name + session ID */}
      {hasResults && processName && (
        <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">{processName}</span>
          {sessionId && (
            <span className="text-xs text-ink-faint font-mono hidden sm:inline">
              {sessionId.slice(0, 8)}
            </span>
          )}
        </div>
      )}

      {/* Right — run analysis button + settings */}
      <div className="flex items-center gap-3">
        {pendingProcessData && !isLoading && (
          <button
            onClick={onRunAnalysis}
            className={cn(
              "text-sm font-semibold px-4 py-1.5 rounded-lg bg-accent text-dark-bg transition-all duration-100",
              "hover:bg-accent/90 hover:shadow-btn-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            )}
          >
            Run Analysis
          </button>
        )}
        {isLoading && (
          <div className="flex items-center gap-1.5 text-xs text-ink-muted">
            <span className="w-1.5 h-1.5 rounded-full bg-accent pulse-dot" />
            Analyzing...
          </div>
        )}

        <button
          onClick={onSettingsClick}
          aria-label="Analysis settings"
          title="Analysis settings"
          className="text-ink-muted hover:text-ink transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          <IconSettings hasDot={hasNonDefaultSettings} />
        </button>
      </div>
    </header>
  );
}
