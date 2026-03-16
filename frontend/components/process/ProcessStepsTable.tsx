"use client";

import { useEffect, useRef, useState } from "react";
import type { ProcessData, ProcessStep } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ProcessStepsTableProps {
  processData: ProcessData;
  onChange?: (updated: ProcessData) => void;
  onEstimate?: () => void;
}

type EditingCell = { rowIndex: number; field: keyof ProcessStep } | null;

function formatTime(hours: number): string {
  if (hours <= 0) return "—";
  const totalMinutes = Math.round(hours * 60);
  if (totalMinutes < 60) return `${totalMinutes} min`;
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

const EDITABLE_FIELDS: { key: keyof ProcessStep; label: string; unit?: string; type: "text" | "number" }[] = [
  { key: "step_name", label: "Step", type: "text" },
  { key: "average_time_hours", label: "Time", type: "number" },
  { key: "cost_per_instance", label: "Cost ($)", type: "number" },
  { key: "error_rate_pct", label: "Error %", type: "number" },
  { key: "resources_needed", label: "Resources", type: "number" },
];

function StepNotesTooltip({ notes }: { notes: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [above, setAbove] = useState(false);

  function handleMouseEnter() {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    setAbove(spaceAbove > spaceBelow);
  }

  return (
    <div ref={ref} onMouseEnter={handleMouseEnter} className="absolute left-0 top-0 w-full h-full group/tooltip">
      <div className={cn(
        "pointer-events-none absolute left-0 z-10 hidden group-hover/tooltip:block w-64 rounded-md border border-dark-border bg-dark-card px-2.5 py-1.5 text-xs text-ink-muted shadow-lg",
        above ? "bottom-full mb-1" : "top-full mt-1"
      )}>
        {notes}
      </div>
    </div>
  );
}

function EditableCell({
  value,
  displayValue,
  type,
  isEditing,
  onStartEdit,
  onCommit,
}: {
  value: string | number | undefined;
  displayValue?: string;
  type: "text" | "number";
  isEditing: boolean;
  onStartEdit: () => void;
  onCommit: (val: string) => void;
}) {
  const [draft, setDraft] = useState(String(value ?? ""));

  if (isEditing) {
    return (
      <input
        autoFocus
        type={type}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => onCommit(draft)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onCommit(draft);
          if (e.key === "Escape") onCommit(String(value ?? ""));
        }}
        className="w-full text-xs px-1.5 py-0.5 border border-accent/50 rounded outline-none focus:ring-1 focus:ring-accent/50 bg-dark-bg text-ink"
      />
    );
  }

  const shown = displayValue ?? (value !== undefined && value !== "" ? String(value) : "—");
  return (
    <button
      onClick={onStartEdit}
      title="Click to edit"
      className={cn(
        "w-full text-left text-xs px-1.5 py-0.5 rounded hover:bg-dark-hover transition-colors",
        value === undefined || value === "" ? "text-ink-faint italic" : "text-ink-muted"
      )}
    >
      {shown}
    </button>
  );
}

export function ProcessStepsTable({ processData, onChange, onEstimate }: ProcessStepsTableProps) {
  const [editingCell, setEditingCell] = useState<EditingCell>(null);
  const [localSteps, setLocalSteps] = useState<ProcessStep[]>(processData.steps);

  // Sync local steps when parent processData changes (e.g. after chat edits add/remove steps).
  // Depend on the whole processData object so reference changes (new step added) always sync.
  useEffect(() => {
    setLocalSteps(processData.steps);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [processData]);

  function commitEdit(rowIndex: number, field: keyof ProcessStep, rawValue: string) {
    setEditingCell(null);
    const step = localSteps[rowIndex];
    const fieldDef = EDITABLE_FIELDS.find((f) => f.key === field);
    const parsed: ProcessStep = { ...step };

    if (fieldDef?.type === "number") {
      const num = parseFloat(rawValue);
      if (!isNaN(num)) {
        (parsed as unknown as Record<string, unknown>)[field] = num;
      }
    } else {
      (parsed as unknown as Record<string, unknown>)[field] = rawValue;
    }

    const updated = localSteps.map((s, i) => (i === rowIndex ? parsed : s));
    setLocalSteps(updated);
    onChange?.({ ...processData, steps: updated });
  }

  const totalTime = localSteps.reduce((s, step) => s + step.average_time_hours, 0);
  const totalCost = localSteps.reduce((s, step) => s + (step.cost_per_instance ?? 0), 0);
  const stepsWithError = localSteps.filter((s) => s.error_rate_pct != null);
  const avgErrorRate =
    stepsWithError.length > 0
      ? stepsWithError.reduce((s, step) => s + (step.error_rate_pct ?? 0), 0) / localSteps.length
      : null;
  const totalResources = localSteps.reduce((s, step) => s + step.resources_needed, 0);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between px-1">
        <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Process Steps</p>
        <div className="flex items-center gap-3">
          {onEstimate && (
            <button
              onClick={onEstimate}
              title="Ask the AI to estimate any blank or zero fields based on process context"
              className="text-xs text-ink-faint hover:text-ink-muted border border-dark-border hover:border-ink-faint rounded px-2 py-0.5 transition-colors"
            >
              Estimate missing values
            </button>
          )}
          <p className="text-xs text-ink-faint">{localSteps.length} steps · {formatTime(totalTime)} total</p>
        </div>
      </div>

      <div className="border border-dark-border rounded-xl overflow-hidden">
        {/* Header */}
        <div className="grid bg-dark-card border-b border-dark-border" style={{ gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1.5fr" }}>
          {EDITABLE_FIELDS.map((f) => (
            <div key={f.key} className="px-2 py-1.5 text-xs font-semibold text-ink-faint uppercase tracking-wide">
              {f.label}
            </div>
          ))}
          <div className="px-2 py-1.5 text-xs font-semibold text-ink-faint uppercase tracking-wide">
            Depends on
          </div>
        </div>

        {/* Rows */}
        <div className="divide-y divide-dark-border max-h-80 overflow-y-auto bg-dark-surface">
          {localSteps.map((step, rowIndex) => (
            <div
              key={rowIndex}
              className="grid hover:bg-dark-hover transition-colors"
              style={{ gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1.5fr" }}
            >
              {EDITABLE_FIELDS.map((field) => (
                <div key={field.key} className="px-1 py-1 relative group/cell">
                  <EditableCell
                    value={step[field.key] as string | number | undefined}
                    displayValue={field.key === "average_time_hours" && typeof step.average_time_hours === "number" ? formatTime(step.average_time_hours) : undefined}
                    type={field.type}
                    isEditing={editingCell?.rowIndex === rowIndex && editingCell?.field === field.key}
                    onStartEdit={() => setEditingCell({ rowIndex, field: field.key })}
                    onCommit={(val) => commitEdit(rowIndex, field.key, val)}
                  />
                  {field.key === "step_name" && step.notes && (
                    <StepNotesTooltip notes={step.notes} />
                  )}
                </div>
              ))}
              <div className="px-2 py-1.5 text-xs text-ink-faint">
                {step.depends_on && step.depends_on.length > 0 ? step.depends_on.join(", ") : "—"}
              </div>
            </div>
          ))}
        </div>

        {/* Summary row */}
        <div
          className="grid border-t-2 border-dark-border bg-dark-card"
          style={{ gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1.5fr" }}
        >
          <div className="px-2 py-1.5 text-xs font-semibold text-ink-muted">
            Total ({localSteps.length})
          </div>
          <div className="px-2 py-1.5 text-xs font-semibold text-ink tabular-nums text-left pl-2">
            {formatTime(totalTime)}
          </div>
          <div className="px-2 py-1.5 text-xs font-semibold text-ink tabular-nums text-left pl-2">
            {totalCost > 0 ? `$${totalCost.toLocaleString()}` : "—"}
          </div>
          <div className="px-2 py-1.5 text-xs font-semibold text-ink tabular-nums text-left pl-2">
            {avgErrorRate != null ? `ø ${avgErrorRate.toFixed(1)}%` : "—"}
          </div>
          <div className="px-2 py-1.5 text-xs font-semibold text-ink tabular-nums text-left pl-2">
            {totalResources}
          </div>
          <div className="px-2 py-1.5 text-xs text-ink-faint">—</div>
        </div>
      </div>

      <p className="text-xs text-ink-faint italic px-1">Click any cell to edit. Changes update the analysis on next run.</p>
    </div>
  );
}
