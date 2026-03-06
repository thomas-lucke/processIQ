"use client";

import { cn } from "@/lib/utils";
import type { AnalysisInsight, Constraints, ProcessData } from "@/lib/types";

interface ContextStripProps {
  processName: string;
  insight: AnalysisInsight;
  processData?: ProcessData | null;
  constraints?: Constraints | null;
}

function deriveHealth(insight: AnalysisInsight): "critical" | "at-risk" | "healthy" {
  const highCount = insight.issues?.filter((i) => i.severity === "high").length ?? 0;
  const issueCount = insight.issues?.length ?? 0;
  if (highCount >= 2) return "critical";
  if (highCount === 1 || issueCount >= 3) return "at-risk";
  return "healthy";
}

function deriveKpis(insight: AnalysisInsight, processData?: ProcessData | null) {
  // Derive best-effort KPIs from available data
  // TODO: wire to real API — backend should return computed KPIs directly
  const steps = processData?.steps ?? [];
  const totalHours = steps.reduce((sum, s) => sum + s.average_time_hours, 0);
  const totalCost = steps.reduce((sum, s) => sum + (s.cost_per_instance ?? 0), 0);
  const topBottleneck = insight.issues?.find((i) => i.severity === "high");

  return {
    cycleTime: totalHours > 0 ? `${totalHours.toFixed(1)}h` : null,
    monthlyCost: totalCost > 0 ? `€${totalCost.toLocaleString()}` : null,
    topBottleneck: topBottleneck?.affected_steps?.[0] ?? topBottleneck?.title?.split(" ").slice(0, 3).join(" ") ?? null,
  };
}

function buildConstraintChips(constraints?: Constraints | null): string[] {
  if (!constraints) return [];
  const chips: string[] = [];
  if (constraints.no_layoffs) chips.push("No layoffs");
  if (constraints.no_new_hires) chips.push("No new hires");
  if (constraints.budget_limit) chips.push(`Budget < €${constraints.budget_limit.toLocaleString()}`);
  if (constraints.timeline_weeks) chips.push(`${constraints.timeline_weeks}w timeline`);
  constraints.custom_constraints?.forEach((c) => chips.push(c));
  return chips;
}

export function ContextStrip({ processName, insight, processData, constraints }: ContextStripProps) {
  const health = deriveHealth(insight);
  const kpis = deriveKpis(insight, processData);
  const chips = buildConstraintChips(constraints);

  const healthConfig = {
    critical: { label: "Critical", border: "border-status-danger/60", text: "text-status-danger" },
    "at-risk": { label: "At Risk", border: "border-status-warning/60", text: "text-status-warning" },
    healthy: { label: "Healthy", border: "border-status-success/60", text: "text-status-success" },
  }[health];

  return (
    <div className="h-12 flex-shrink-0 flex items-center gap-4 px-5 bg-dark-surface border-b border-dark-border overflow-hidden">
      {/* Left: process name + health pill */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-sm font-semibold text-ink truncate max-w-[180px]">{processName}</span>
        <span
          className={cn(
            "text-2xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded border",
            healthConfig.border,
            healthConfig.text
          )}
        >
          {healthConfig.label}
        </span>
      </div>

      {/* Divider */}
      <div className="h-5 w-px bg-dark-border flex-shrink-0" />

      {/* Center: constraint chips */}
      {chips.length > 0 && (
        <div className="flex items-center gap-1.5 overflow-hidden">
          {chips.map((chip) => (
            <span
              key={chip}
              className="text-2xs text-ink-muted bg-dark-card border border-dark-border px-2 py-0.5 rounded-full whitespace-nowrap flex-shrink-0"
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {/* Right: KPI tiles — pushed to the far right */}
      <div className="ml-auto flex items-center gap-4 flex-shrink-0">
        {kpis.cycleTime && (
          <KpiTile label="Avg. cycle time" value={kpis.cycleTime} />
        )}
        {kpis.monthlyCost && (
          <KpiTile label="Total cost/instance" value={kpis.monthlyCost} />
        )}
        {kpis.topBottleneck && (
          <KpiTile label="Top bottleneck" value={kpis.topBottleneck} valueClass="text-status-danger" />
        )}
      </div>
    </div>
  );
}

function KpiTile({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-2xs text-ink-faint uppercase tracking-wider leading-none">{label}</span>
      <span className={cn("text-xs font-semibold text-ink leading-tight", valueClass)}>{value}</span>
    </div>
  );
}
