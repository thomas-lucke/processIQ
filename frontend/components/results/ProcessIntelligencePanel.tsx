"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { AnalysisInsight, GraphSchema, Issue, Recommendation } from "@/lib/types";

const ProcessGraph = dynamic(
  () => import("@/components/visualization/ProcessGraph").then((m) => m.ProcessGraph),
  { ssr: false }
);

// ---------------------------------------------------------------------------
// Tab types
// ---------------------------------------------------------------------------

type TabId = "overview" | "issues" | "recommendations" | "flow" | "scenarios";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "issues", label: "Issues" },
  { id: "recommendations", label: "Recommendations" },
  { id: "flow", label: "Flow" },
  { id: "scenarios", label: "Scenarios" },
];

// ---------------------------------------------------------------------------
// Shared badge components
// ---------------------------------------------------------------------------

function SeverityBadge({ severity }: { severity: Issue["severity"] }) {
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold",
      severity === "high" && "bg-red-950 text-red-400",
      severity === "medium" && "bg-orange-950 text-orange-400",
      severity === "low" && "bg-yellow-950 text-yellow-500",
    )}>
      {severity === "high" ? "High" : severity === "medium" ? "Medium" : "Low"}
    </span>
  );
}

function ConfidenceBadge({ level }: { level: "high" | "medium" | "low" }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
      level === "high" && "bg-emerald-950 text-emerald-400 ring-1 ring-emerald-800",
      level === "medium" && "bg-amber-950 text-amber-400 ring-1 ring-amber-800",
      level === "low" && "bg-dark-card text-ink-muted ring-1 ring-dark-border",
    )}>
      <span className={cn("w-1.5 h-1.5 rounded-full",
        level === "high" && "bg-emerald-400",
        level === "medium" && "bg-amber-400",
        level === "low" && "bg-ink-faint",
      )} />
      {level === "high" ? "High confidence" : level === "medium" ? "Medium" : "Needs validation"}
    </span>
  );
}

function FeasibilityBadge({ feasibility }: { feasibility: Recommendation["feasibility"] }) {
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold",
      feasibility === "easy" && "bg-emerald-950 text-emerald-400",
      feasibility === "moderate" && "bg-accent-muted text-accent",
      feasibility === "complex" && "bg-purple-950 text-purple-400",
    )}>
      {feasibility === "easy" ? "Easy" : feasibility === "moderate" ? "Moderate" : "Complex"}
    </span>
  );
}

function StepTag({ name, onClick }: { name: string; onClick?: () => void }) {
  if (onClick) {
    return (
      <button
        onClick={onClick}
        className="text-xs bg-accent-muted text-accent px-2 py-0.5 rounded-full hover:bg-accent/20 transition-colors border border-accent/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        title="Highlight in Flow tab"
      >
        {name}
      </button>
    );
  }
  return (
    <span className="text-xs bg-dark-card text-ink-muted px-2 py-0.5 rounded-full border border-dark-border">
      {name}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Health utility
// ---------------------------------------------------------------------------

function deriveHealth(insight: AnalysisInsight): "critical" | "at-risk" | "healthy" {
  const highCount = insight.issues?.filter((i) => i.severity === "high").length ?? 0;
  const issueCount = insight.issues?.length ?? 0;
  if (highCount >= 2) return "critical";
  if (highCount === 1 || issueCount >= 3) return "at-risk";
  return "healthy";
}

// ---------------------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------------------

function OverviewTab({
  insight,
  graphSchema,
  highlightedSteps,
  onHighlightSteps,
}: {
  insight: AnalysisInsight;
  graphSchema?: GraphSchema | null;
  highlightedSteps: string[];
  onHighlightSteps: (steps: string[]) => void;
}) {
  const health = deriveHealth(insight);
  const topIssues = (insight.issues ?? []).slice(0, 3);

  const healthConfig = {
    critical: {
      border: "border-status-danger/40",
      bg: "bg-red-950/20",
      text: "text-status-danger",
      label: "Critical Issues Found",
    },
    "at-risk": {
      border: "border-status-warning/40",
      bg: "bg-amber-950/20",
      text: "text-status-warning",
      label: "Improvement Opportunities",
    },
    healthy: {
      border: "border-status-success/40",
      bg: "bg-emerald-950/20",
      text: "text-status-success",
      label: "Process Is Healthy",
    },
  }[health];

  return (
    <div className="space-y-5">
      {/* Health summary card */}
      <div className={cn("rounded-xl border px-5 py-4 space-y-3", healthConfig.border, healthConfig.bg)}>
        <div className="flex items-center justify-between">
          <span className={cn("text-base font-bold", healthConfig.text)}>{healthConfig.label}</span>
          <div className="flex items-center gap-3 text-xs text-ink-muted">
            {(insight.issues?.length ?? 0) > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-status-danger" />
                {insight.issues!.length} issue{insight.issues!.length !== 1 ? "s" : ""}
              </span>
            )}
            {(insight.recommendations?.length ?? 0) > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-accent" />
                {insight.recommendations!.length} rec{insight.recommendations!.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        <p className="text-sm text-ink leading-relaxed">{insight.process_summary}</p>
        {insight.patterns && insight.patterns.length > 0 && (
          <ul className="space-y-1">
            {insight.patterns.map((p, i) => (
              <li key={i} className="text-xs text-ink-muted flex items-start gap-1.5">
                <span className="mt-0.5 text-ink-faint flex-shrink-0">•</span>
                {p}
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-ink-faint italic border-t border-dark-border pt-2">
          AI-generated analysis. Review before acting.
        </p>
      </div>

      {/* Top 3 issues */}
      {topIssues.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Top Issues</h3>
          {topIssues.map((issue, i) => (
            <div key={i} className="bg-dark-card border border-dark-border rounded-lg px-4 py-3 space-y-1.5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-ink leading-snug">{issue.title}</p>
                <SeverityBadge severity={issue.severity} />
              </div>
              <p className="text-xs text-ink-muted">{issue.description.slice(0, 120)}{issue.description.length > 120 ? "..." : ""}</p>
              {issue.affected_steps && issue.affected_steps.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {issue.affected_steps.map((s) => (
                    <StepTag key={s} name={s} onClick={() => onHighlightSteps([s])} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Mini flow graph */}
      {graphSchema && graphSchema.before_nodes.length >= 2 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Process Flow</h3>
          <div className="border border-dark-border rounded-xl overflow-hidden" style={{ height: 240 }}>
            <ProcessGraph schema={graphSchema} highlightedSteps={highlightedSteps} />
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Issues tab
// ---------------------------------------------------------------------------

function IssueCard({ issue }: { issue: Issue }) {
  const [showReasoning, setShowReasoning] = useState(false);
  const confidence: "high" | "medium" | "low" =
    issue.severity === "high" ? "high" : issue.severity === "medium" ? "medium" : "low";
  const hasEvidence = (issue.evidence && issue.evidence.length > 0) || issue.root_cause_hypothesis;

  return (
    <div className="bg-dark-card border border-dark-border rounded-xl px-4 py-4 space-y-2.5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-ink leading-snug">{issue.title}</p>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <SeverityBadge severity={issue.severity} />
          <ConfidenceBadge level={confidence} />
        </div>
      </div>
      <p className="text-sm text-ink-muted leading-relaxed">{issue.description}</p>
      {issue.affected_steps && issue.affected_steps.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {issue.affected_steps.map((s) => <StepTag key={s} name={s} />)}
        </div>
      )}
      {hasEvidence && (
        <>
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            aria-expanded={showReasoning}
            className="text-xs text-accent hover:text-accent/80 flex items-center gap-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            <span>{showReasoning ? "▲" : "▼"}</span>
            {showReasoning ? "Hide reasoning" : "Show reasoning"}
          </button>
          {showReasoning && (
            <div className="rounded-lg bg-accent-muted border border-accent/20 px-3 py-2.5 space-y-1.5 text-xs text-ink">
              <p className="font-semibold text-accent">AI reasoning</p>
              {issue.root_cause_hypothesis && (
                <p><span className="font-medium text-ink">Root cause: </span>{issue.root_cause_hypothesis}</p>
              )}
              {issue.evidence && issue.evidence.length > 0 && (
                <ul className="list-disc ml-4 space-y-0.5 text-ink-muted">
                  {issue.evidence.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function IssuesTab({ insight }: { insight: AnalysisInsight }) {
  const issues = insight.issues ?? [];
  const high = issues.filter((i) => i.severity === "high");
  const medium = issues.filter((i) => i.severity === "medium");
  const low = issues.filter((i) => i.severity === "low");

  if (issues.length === 0) {
    return <p className="text-sm text-ink-muted py-4">No issues identified.</p>;
  }

  return (
    <div className="space-y-6">
      {high.length > 0 && (
        <IssueGroup label="High severity" issues={high} />
      )}
      {medium.length > 0 && (
        <IssueGroup label="Medium severity" issues={medium} />
      )}
      {low.length > 0 && (
        <IssueGroup label="Low severity" issues={low} />
      )}
    </div>
  );
}

function IssueGroup({ label, issues }: { label: string; issues: Issue[] }) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wider">{label}</h3>
      {issues.map((issue, i) => <IssueCard key={i} issue={issue} />)}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recommendations tab
// ---------------------------------------------------------------------------

type RecAction = "accepted" | "dismissed" | null;

function RecommendationCard({
  rec,
  index,
  onHighlightSteps,
}: {
  rec: Recommendation;
  index: number;
  onHighlightSteps?: (steps: string[]) => void;
}) {
  const [expanded, setExpanded] = useState(index === 0);
  const [showReasoning, setShowReasoning] = useState(false);
  const [action, setAction] = useState<RecAction>(null);

  if (action === "dismissed") {
    return (
      <div className="bg-dark-card border border-dark-border rounded-xl px-4 py-3 flex items-center justify-between text-xs text-ink-faint">
        <span className="italic">{rec.title} — dismissed</span>
        <button onClick={() => setAction(null)} className="text-accent hover:text-accent/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Restore</button>
      </div>
    );
  }

  if (action === "accepted") {
    return (
      <div className="bg-emerald-950/30 border border-emerald-800/50 rounded-xl px-4 py-3 flex items-center justify-between text-xs text-emerald-400 border-l-2 border-l-emerald-500">
        <span className="font-medium">✓ {rec.title} — added to improvement plan</span>
        <button onClick={() => setAction(null)} className="text-ink-faint hover:text-ink-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Undo</button>
      </div>
    );
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-xl px-4 py-4 space-y-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span className="text-xs font-bold text-ink-faint mt-0.5 w-6 flex-shrink-0">
            {String(index + 1).padStart(2, "0")}
          </span>
          <p className="text-sm font-semibold text-ink leading-snug">{rec.title}</p>
        </div>
        <FeasibilityBadge feasibility={rec.feasibility} />
      </div>

      <p className="text-sm text-ink-muted leading-relaxed ml-8">{rec.description}</p>

      {rec.expected_benefit && (
        <p className="ml-8 text-sm font-medium text-status-success">
          → {rec.expected_benefit}
        </p>
      )}

      {rec.affected_steps && rec.affected_steps.length > 0 && (
        <div className="ml-8 flex flex-wrap gap-1 items-center">
          <span className="text-xs text-ink-faint">Steps:</span>
          {rec.affected_steps.map((s) => (
            <StepTag
              key={s}
              name={s}
              onClick={onHighlightSteps ? () => onHighlightSteps(rec.affected_steps ?? []) : undefined}
            />
          ))}
        </div>
      )}

      {rec.estimated_roi && (
        <p className="ml-8 text-xs text-ink-muted">Estimated ROI: {rec.estimated_roi}</p>
      )}

      <div className="ml-8 flex items-center gap-3">
        <button
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          className="text-xs text-accent hover:text-accent/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          {expanded ? "Less detail" : "More detail"}
        </button>
        {rec.plain_explanation && (
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            aria-expanded={showReasoning}
            className="text-xs text-ink-muted hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            Show reasoning
          </button>
        )}
      </div>

      {expanded && (
        <div className="ml-8 space-y-2 text-sm">
          {rec.concrete_next_steps && rec.concrete_next_steps.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-1 uppercase tracking-wide">How to implement</p>
              <ol className="list-decimal ml-4 space-y-1 text-xs text-ink-muted">
                {rec.concrete_next_steps.map((s, i) => <li key={i}>{s}</li>)}
              </ol>
            </div>
          )}
          {rec.risks && rec.risks.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-1 uppercase tracking-wide">Risks</p>
              <ul className="list-disc ml-4 space-y-0.5 text-xs text-orange-400">
                {rec.risks.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
          {rec.prerequisites && rec.prerequisites.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-ink-muted mb-1 uppercase tracking-wide">Prerequisites</p>
              <ul className="list-disc ml-4 space-y-0.5 text-xs text-ink-muted">
                {rec.prerequisites.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {showReasoning && rec.plain_explanation && (
        <div className="ml-8 rounded-lg bg-accent-muted border border-accent/20 px-3 py-2.5 text-xs text-ink">
          <p className="font-semibold text-accent mb-1">AI reasoning</p>
          <p>{rec.plain_explanation}</p>
        </div>
      )}

      <div className="ml-8 flex items-center gap-2 pt-1">
        <button
          onClick={() => setAction("accepted")}
          className="text-xs px-4 py-1.5 rounded-lg bg-accent text-dark-bg hover:bg-accent/90 hover:shadow-btn-accent transition-all duration-100 font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          Accept
        </button>
        <button
          onClick={() => setAction("dismissed")}
          className="text-xs px-4 py-1.5 rounded-lg border border-dark-border text-ink-muted hover:bg-dark-hover transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

function RecommendationsTab({
  insight,
  onHighlightSteps,
}: {
  insight: AnalysisInsight;
  onHighlightSteps: (steps: string[]) => void;
}) {
  const recs = insight.recommendations ?? [];
  if (recs.length === 0) {
    return <p className="text-sm text-ink-muted py-4">No recommendations generated.</p>;
  }
  return (
    <div className="space-y-3">
      {recs.map((rec, i) => (
        <RecommendationCard key={i} rec={rec} index={i} onHighlightSteps={onHighlightSteps} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Flow tab
// ---------------------------------------------------------------------------

function FlowTab({
  graphSchema,
  highlightedSteps,
}: {
  graphSchema?: GraphSchema | null;
  highlightedSteps: string[];
}) {
  if (!graphSchema || graphSchema.before_nodes.length < 2) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-ink-muted">
        Process graph not available. Run an analysis first.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="border border-dark-border rounded-xl overflow-hidden" style={{ height: 420 }}>
        <ProcessGraph schema={graphSchema} highlightedSteps={highlightedSteps} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scenarios tab
// ---------------------------------------------------------------------------

function ScenariosTab({ insight }: { insight: AnalysisInsight }) {
  // TODO: wire to real API — derive before/after KPIs from backend when available
  const topRec = insight.recommendations?.[0];
  const issues = insight.issues ?? [];

  return (
    <div className="space-y-4">
      <p className="text-xs text-ink-faint italic">
        Scenario comparison is estimated. Projections are based on the top recommendation&apos;s expected benefit.
      </p>
      <div className="grid grid-cols-2 gap-4">
        {/* Current state */}
        <div className="bg-dark-card border border-dark-border rounded-xl px-4 py-4 space-y-3">
          <div>
            <p className="text-xs font-semibold text-ink-faint uppercase tracking-wider mb-1">Current state</p>
            <div className={cn(
              "text-sm font-bold",
              issues.filter(i => i.severity === "high").length >= 2 ? "text-status-danger"
              : issues.filter(i => i.severity === "high").length >= 1 ? "text-status-warning"
              : "text-status-success"
            )}>
              {issues.filter(i => i.severity === "high").length >= 2 ? "Critical" : issues.filter(i => i.severity === "high").length >= 1 ? "At Risk" : "Healthy"}
            </div>
          </div>
          <div className="space-y-2">
            <ScenarioKpi label="Issues" value={`${issues.length} identified`} direction="bad" />
            <ScenarioKpi label="High severity" value={`${issues.filter(i => i.severity === "high").length}`} direction="bad" />
          </div>
        </div>

        {/* After top recommendation */}
        <div className="bg-dark-card border border-accent/20 rounded-xl px-4 py-4 space-y-3">
          <div>
            <p className="text-xs font-semibold text-ink-faint uppercase tracking-wider mb-1">
              After top recommendation
            </p>
            <div className="text-sm font-bold text-status-success">Projected improvement</div>
          </div>
          {topRec ? (
            <div className="space-y-2">
              <ScenarioKpi label="Recommendation" value={topRec.title} direction="good" small />
              {topRec.expected_benefit && (
                <ScenarioKpi label="Expected benefit" value={topRec.expected_benefit} direction="good" small />
              )}
              {topRec.estimated_roi && (
                <ScenarioKpi label="Estimated ROI" value={topRec.estimated_roi} direction="good" small />
              )}
            </div>
          ) : (
            <p className="text-xs text-ink-muted">No recommendations available.</p>
          )}
        </div>
      </div>

      {/* Remaining recommendations */}
      {(insight.recommendations?.length ?? 0) > 1 && (
        <div className="bg-dark-card border border-dark-border rounded-xl px-4 py-3 space-y-2">
          <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
            Additional recommendations ({insight.recommendations!.length - 1} more)
          </p>
          {insight.recommendations!.slice(1).map((rec, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-xs text-ink-faint mt-0.5 flex-shrink-0">{i + 2}.</span>
              <div>
                <p className="text-xs font-medium text-ink">{rec.title}</p>
                {rec.expected_benefit && (
                  <p className="text-xs text-status-success">{rec.expected_benefit}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScenarioKpi({
  label,
  value,
  direction,
  small,
}: {
  label: string;
  value: string;
  direction: "good" | "bad" | "neutral";
  small?: boolean;
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-2xs text-ink-faint uppercase tracking-wider">{label}</p>
      <p className={cn(
        "font-semibold",
        small ? "text-xs" : "text-sm",
        direction === "good" && "text-status-success",
        direction === "bad" && "text-status-danger",
        direction === "neutral" && "text-ink",
      )}>
        {value}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

interface ProcessIntelligencePanelProps {
  insight: AnalysisInsight;
  graphSchema?: GraphSchema | null;
  runLabel?: string | null;
  highlightedSteps: string[];
  onHighlightSteps: (steps: string[]) => void;
}

export function ProcessIntelligencePanel({
  insight,
  graphSchema,
  runLabel,
  highlightedSteps,
  onHighlightSteps,
}: ProcessIntelligencePanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  return (
    <div className="flex flex-col h-full bg-dark-bg">
      {/* Tab bar */}
      <div className="flex-shrink-0 border-b border-dark-border px-5 pt-4">
        {runLabel && (
          <p className="text-xs text-ink-muted mb-3 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent" />
            {runLabel}
          </p>
        )}
        <div className="flex items-end gap-1" role="tablist" aria-label="Analysis sections">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-4 py-2 text-sm font-medium transition-all duration-100 border-b-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent",
                activeTab === tab.id
                  ? "text-ink border-accent"
                  : "text-ink-muted border-transparent hover:text-ink hover:border-dark-border"
              )}
            >
              {tab.label}
              {tab.id === "issues" && (insight.issues?.length ?? 0) > 0 && (
                <span className="ml-1.5 text-xs bg-dark-card text-ink-muted px-1.5 py-0.5 rounded-full border border-dark-border">
                  {insight.issues!.length}
                </span>
              )}
              {tab.id === "recommendations" && (insight.recommendations?.length ?? 0) > 0 && (
                <span className="ml-1.5 text-xs bg-dark-card text-ink-muted px-1.5 py-0.5 rounded-full border border-dark-border">
                  {insight.recommendations!.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-5" role="tabpanel">
        {activeTab === "overview" && (
          <OverviewTab
            insight={insight}
            graphSchema={graphSchema}
            highlightedSteps={highlightedSteps}
            onHighlightSteps={onHighlightSteps}
          />
        )}
        {activeTab === "issues" && <IssuesTab insight={insight} />}
        {activeTab === "recommendations" && (
          <RecommendationsTab insight={insight} onHighlightSteps={onHighlightSteps} />
        )}
        {activeTab === "flow" && (
          <FlowTab graphSchema={graphSchema} highlightedSteps={highlightedSteps} />
        )}
        {activeTab === "scenarios" && <ScenariosTab insight={insight} />}
      </div>
    </div>
  );
}
