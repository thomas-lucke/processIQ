"use client";

import { useEffect, useState } from "react";
import { getUserSessions } from "@/lib/api";
import type { AnalysisSessionSummary, RecommendationSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function industryLabel(industry: string): string {
  if (!industry) return "";
  return industry.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Empty / loading / error states
// ---------------------------------------------------------------------------

function EmptyLibrary() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-8">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" className="text-ink-faint" aria-hidden="true">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
      <p className="text-sm font-medium text-ink-muted">No analyses yet</p>
      <p className="text-xs text-ink-faint leading-relaxed max-w-xs">
        Past analyses are saved automatically. Run your first analysis and it will appear here.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recommendation card (expandable, with full text)
// ---------------------------------------------------------------------------


function RecommendationCard({
  rec,
  wasAccepted,
  wasRejected,
}: {
  rec: RecommendationSummary;
  wasAccepted: boolean;
  wasRejected: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={cn(
      "rounded-lg border overflow-hidden",
      wasAccepted ? "border-green-900/40 bg-green-950/20" :
      wasRejected ? "border-dark-border bg-dark-bg/40 opacity-60" :
      "border-dark-border bg-dark-bg/40"
    )}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-3 py-2 flex items-center justify-between gap-2 hover:bg-dark-hover transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className={cn(
            "flex-shrink-0 text-xs",
            wasAccepted ? "text-status-success" : wasRejected ? "text-ink-faint" : "text-ink-faint"
          )}>
            {wasAccepted ? "✓" : wasRejected ? "✕" : "·"}
          </span>
          <span className={cn(
            "text-xs font-medium truncate",
            wasRejected ? "line-through text-ink-faint" : "text-ink"
          )}>
            {rec.title}
          </span>
        </div>
        <span className={cn(
          "text-ink-faint transition-transform duration-150 text-xs flex-shrink-0",
          expanded && "rotate-180"
        )}>▼</span>
      </button>

      {expanded && (
        <div className="border-t border-dark-border px-3 py-2.5 space-y-2">
          <p className="text-xs text-ink-muted leading-relaxed">{rec.description}</p>
          {rec.expected_benefit && (
            <p className="text-xs text-status-success/80">{rec.expected_benefit}</p>
          )}
          {rec.estimated_roi && (
            <p className="text-xs text-ink-faint italic">{rec.estimated_roi}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session row / expanded detail
// ---------------------------------------------------------------------------

function AcceptanceBar({ offered, accepted }: { offered: number; accepted: number }) {
  if (offered === 0) return null;
  const pct = Math.round((accepted / offered) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 rounded-full bg-dark-border overflow-hidden">
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-ink-faint tabular-nums w-8 text-right">{pct}%</span>
    </div>
  );
}

function SessionCard({ session }: { session: AnalysisSessionSummary }) {
  const [expanded, setExpanded] = useState(false);

  const issueCount = session.bottlenecks_found.length;
  const recCount = session.recommendations_full.length || session.suggestions_offered.length;
  const acceptedCount = session.suggestions_accepted.length;

  return (
    <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
      {/* Header row — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full text-left px-4 py-3.5 flex items-start justify-between gap-3 hover:bg-dark-hover transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        <div className="flex-1 min-w-0 space-y-1">
          <p className="text-sm font-semibold text-ink truncate">{session.process_name}</p>
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs text-ink-faint">{formatDate(session.timestamp)}</span>
            {session.industry && (
              <span className="text-xs text-ink-faint">{industryLabel(session.industry)}</span>
            )}
            {session.step_names.length > 0 && (
              <span className="text-xs text-ink-faint">{session.step_names.length} steps</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 pt-0.5">
          {issueCount > 0 && (
            <span className="text-xs bg-red-950 text-red-400 px-2 py-0.5 rounded-full border border-red-900/40">
              {issueCount} issue{issueCount !== 1 ? "s" : ""}
            </span>
          )}
          {recCount > 0 && (
            <span className="text-xs bg-accent-muted text-accent px-2 py-0.5 rounded-full border border-accent/20">
              {recCount} rec{recCount !== 1 ? "s" : ""}
            </span>
          )}
          <span className={cn(
            "text-ink-faint transition-transform duration-150 text-xs",
            expanded && "rotate-180"
          )}>▼</span>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-dark-border px-4 py-3 space-y-4">

          {/* Process description */}
          {session.process_description && (
            <p className="text-xs text-ink-muted leading-relaxed">{session.process_description}</p>
          )}

          {/* Steps */}
          {session.step_names.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-ink-faint uppercase tracking-wide">Steps</p>
              <div className="flex flex-wrap gap-1">
                {session.step_names.map((s) => (
                  <span key={s} className="text-xs bg-dark-bg border border-dark-border text-ink-muted px-2 py-0.5 rounded-full">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Bottlenecks */}
          {session.bottlenecks_found.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-ink-faint uppercase tracking-wide">Issues identified</p>
              <ul className="space-y-1">
                {session.bottlenecks_found.map((b, i) => (
                  <li key={i} className="text-xs text-ink-muted flex items-start gap-1.5">
                    <span className="mt-0.5 text-red-400 flex-shrink-0">•</span>
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Recommendations + acceptance */}
          {recCount > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-ink-faint uppercase tracking-wide">Recommendations</p>
                <span className="text-xs text-ink-faint">
                  {acceptedCount}/{recCount} accepted
                </span>
              </div>
              <AcceptanceBar offered={recCount} accepted={acceptedCount} />
              {session.recommendations_full.length > 0 ? (
                <div className="space-y-1.5">
                  {session.recommendations_full.map((rec, i) => (
                    <RecommendationCard
                      key={i}
                      rec={rec}
                      wasAccepted={session.suggestions_accepted.includes(rec.title)}
                      wasRejected={session.suggestions_rejected.includes(rec.title)}
                    />
                  ))}
                </div>
              ) : (
                // Fallback for old sessions that only stored titles
                <ul className="space-y-1">
                  {session.suggestions_offered.map((r, i) => {
                    const wasAccepted = session.suggestions_accepted.includes(r);
                    const wasRejected = session.suggestions_rejected.includes(r);
                    return (
                      <li key={i} className="text-xs flex items-start gap-1.5">
                        <span className={cn(
                          "mt-0.5 flex-shrink-0",
                          wasAccepted ? "text-status-success" : wasRejected ? "text-ink-faint" : "text-ink-faint"
                        )}>
                          {wasAccepted ? "✓" : wasRejected ? "✕" : "·"}
                        </span>
                        <span className={cn(wasRejected ? "text-ink-faint line-through" : "text-ink-muted")}>
                          {r}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function LibraryPanel() {
  const [sessions, setSessions] = useState<AnalysisSessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getUserSessions()
      .then((res) => setSessions(res.sessions))
      .catch(() => setError("Could not load past analyses."));
  }, []);

  return (
    <div className="flex flex-col h-full bg-dark-bg">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-dark-border px-6 py-4">
        <h2 className="text-sm font-semibold text-ink">Analysis library</h2>
        <p className="text-xs text-ink-faint mt-0.5">Your past analyses, newest first.</p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {sessions === null && !error && (
          <div className="flex items-center justify-center h-32">
            <p className="text-sm text-ink-faint">Loading...</p>
          </div>
        )}

        {error && (
          <p className="text-sm text-red-400 py-4">{error}</p>
        )}

        {sessions !== null && sessions.length === 0 && <EmptyLibrary />}

        {sessions !== null && sessions.length > 0 && (
          <div className="space-y-2 max-w-2xl">
            <p className="text-xs text-ink-faint mb-3">
              {sessions.length} analysis{sessions.length !== 1 ? "es" : ""} on record
            </p>
            {sessions.map((s) => (
              <SessionCard key={s.session_id} session={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
