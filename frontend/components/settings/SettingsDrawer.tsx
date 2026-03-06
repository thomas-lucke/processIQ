"use client";

import type { BusinessProfile, Constraints, Industry, CompanySize, RegulatoryEnvironment } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SettingsDrawerProps {
  profile: BusinessProfile;
  constraints: Constraints;
  analysisMode: string;
  llmProvider: "anthropic" | "openai" | "ollama";
  maxCycles: number;
  onProfileChange: (p: BusinessProfile) => void;
  onConstraintsChange: (c: Constraints) => void;
  onAnalysisModeChange: (mode: string) => void;
  onLlmProviderChange: (p: "anthropic" | "openai" | "ollama") => void;
  onMaxCyclesChange: (n: number) => void;
}

const INDUSTRIES: { value: Industry; label: string }[] = [
  { value: "financial_services", label: "Financial Services" },
  { value: "healthcare", label: "Healthcare" },
  { value: "manufacturing", label: "Manufacturing" },
  { value: "retail", label: "Retail" },
  { value: "technology", label: "Technology" },
  { value: "government", label: "Government" },
  { value: "education", label: "Education" },
  { value: "other", label: "Other" },
];

const COMPANY_SIZES: { value: CompanySize; label: string }[] = [
  { value: "startup", label: "Startup (< 50)" },
  { value: "small", label: "Small (50-200)" },
  { value: "mid_market", label: "Mid-market (200-1000)" },
  { value: "enterprise", label: "Enterprise (1000+)" },
];

const REGULATORY_ENVS: { value: RegulatoryEnvironment; label: string }[] = [
  { value: "minimal", label: "Minimal" },
  { value: "moderate", label: "Moderate" },
  { value: "strict", label: "Strict" },
  { value: "highly_regulated", label: "Highly regulated" },
];

const ANALYSIS_MODES = [
  { value: "cost_optimized", label: "Cost optimized", description: "Fewer LLM calls, faster, cheaper" },
  { value: "balanced", label: "Balanced", description: "Default — good quality vs speed trade-off" },
  { value: "deep_analysis", label: "Deep analysis", description: "More investigation cycles, higher quality" },
];

const LLM_PROVIDERS: { value: "anthropic" | "openai" | "ollama"; label: string; description: string }[] = [
  { value: "anthropic", label: "Anthropic Claude", description: "Default — best analysis quality" },
  { value: "openai", label: "OpenAI GPT", description: "Alternative cloud provider" },
  { value: "ollama", label: "Ollama (local)", description: "Runs locally — no data leaves your machine" },
];

function SectionHeader({ title }: { title: string }) {
  return (
    <p className="text-xs font-semibold text-ink-faint uppercase tracking-wide pt-4 pb-1 border-t border-dark-border first:pt-0 first:border-t-0">
      {title}
    </p>
  );
}

function NumberField({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: number | undefined;
  placeholder?: string;
  onChange: (v: number | undefined) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-ink-muted font-medium">{label}</label>
      <input
        type="number"
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value ? parseFloat(e.target.value) : undefined)}
        className="w-full text-xs border border-dark-border rounded-lg px-2.5 py-1.5 bg-dark-bg outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 text-ink placeholder:text-ink-faint transition-colors"
      />
    </div>
  );
}

function CheckboxField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded border-dark-border bg-dark-bg text-accent focus:ring-accent/50"
      />
      <span className="text-xs text-ink-muted">{label}</span>
    </label>
  );
}

const inputClass = "w-full text-xs border border-dark-border rounded-lg px-2.5 py-1.5 bg-dark-bg outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 text-ink transition-colors";

export function SettingsDrawer({
  profile,
  constraints,
  analysisMode,
  llmProvider,
  maxCycles,
  onProfileChange,
  onConstraintsChange,
  onAnalysisModeChange,
  onLlmProviderChange,
  onMaxCyclesChange,
}: SettingsDrawerProps) {
  return (
    <div className="space-y-3 text-sm">

      {/* LLM Provider */}
      <SectionHeader title="LLM provider" />
      <div className="space-y-2">
        {LLM_PROVIDERS.map((p) => (
          <label key={p.value} className="flex items-start gap-2 cursor-pointer">
            <input
              type="radio"
              name="llm_provider"
              value={p.value}
              checked={llmProvider === p.value}
              onChange={() => onLlmProviderChange(p.value)}
              className="mt-0.5 text-accent focus:ring-accent/50 bg-dark-bg border-dark-border"
            />
            <div>
              <p className="text-xs font-medium text-ink">{p.label}</p>
              <p className="text-xs text-ink-faint">{p.description}</p>
            </div>
          </label>
        ))}
      </div>

      {/* Analysis mode */}
      <SectionHeader title="Analysis mode" />
      <div className="space-y-2">
        {ANALYSIS_MODES.map((mode) => (
          <label key={mode.value} className="flex items-start gap-2 cursor-pointer">
            <input
              type="radio"
              name="analysis_mode"
              value={mode.value}
              checked={analysisMode === mode.value}
              onChange={() => onAnalysisModeChange(mode.value)}
              className="mt-0.5 text-accent focus:ring-accent/50 bg-dark-bg border-dark-border"
            />
            <div>
              <p className="text-xs font-medium text-ink">{mode.label}</p>
              <p className="text-xs text-ink-faint">{mode.description}</p>
            </div>
          </label>
        ))}
      </div>

      {/* Investigation depth */}
      <SectionHeader title="Investigation depth" />
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-xs text-ink-muted font-medium">Max investigation cycles</label>
          <span className="text-xs font-semibold text-ink tabular-nums w-4 text-right">{maxCycles}</span>
        </div>
        <input
          type="range"
          min={1}
          max={10}
          step={1}
          value={maxCycles}
          onChange={(e) => onMaxCyclesChange(parseInt(e.target.value, 10))}
          className="w-full accent-accent h-1.5 rounded-full bg-dark-border cursor-pointer"
        />
        <div className="flex justify-between text-xs text-ink-faint">
          <span>1 — fast</span>
          <span>10 — thorough</span>
        </div>
        <p className="text-xs text-ink-faint">
          {maxCycles <= 2
            ? "Minimal investigation — faster, lower cost."
            : maxCycles <= 5
            ? "Standard investigation — good quality/speed balance."
            : "Deep investigation — more thorough, higher cost."}
        </p>
      </div>

      {/* Business profile */}
      <SectionHeader title="Business profile" />

      <div className="space-y-1">
        <label className="text-xs text-ink-muted font-medium">Industry</label>
        <select
          value={profile.industry ?? ""}
          onChange={(e) =>
            onProfileChange({
              ...profile,
              industry: (e.target.value || null) as Industry | null,
              custom_industry: e.target.value === "other" ? (profile.custom_industry ?? "") : "",
            })
          }
          className={inputClass}
        >
          <option value="">— not specified —</option>
          {INDUSTRIES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {profile.industry === "other" && (
          <input
            type="text"
            value={profile.custom_industry ?? ""}
            placeholder="Describe your industry..."
            onChange={(e) => onProfileChange({ ...profile, custom_industry: e.target.value })}
            className={cn(inputClass, "mt-1")}
            autoFocus
          />
        )}
      </div>

      <div className="space-y-1">
        <label className="text-xs text-ink-muted font-medium">Company size</label>
        <select
          value={profile.company_size ?? ""}
          onChange={(e) => onProfileChange({ ...profile, company_size: (e.target.value || null) as CompanySize | null })}
          className={inputClass}
        >
          <option value="">— not specified —</option>
          {COMPANY_SIZES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-ink-muted font-medium">Regulatory environment</label>
        <select
          value={profile.regulatory_environment ?? "moderate"}
          onChange={(e) => onProfileChange({ ...profile, regulatory_environment: e.target.value as RegulatoryEnvironment })}
          className={inputClass}
        >
          {REGULATORY_ENVS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Constraints */}
      <SectionHeader title="Constraints" />
      <NumberField
        label="Budget limit ($)"
        value={constraints.budget_limit ?? undefined}
        placeholder="No limit"
        onChange={(v) => onConstraintsChange({ ...constraints, budget_limit: v ?? null })}
      />
      <NumberField
        label="Timeline (weeks)"
        value={constraints.timeline_weeks ?? undefined}
        placeholder="No limit"
        onChange={(v) => onConstraintsChange({ ...constraints, timeline_weeks: v ?? null })}
      />
      <div className="space-y-1.5">
        <CheckboxField
          label="No layoffs"
          checked={constraints.no_layoffs ?? false}
          onChange={(v) => onConstraintsChange({ ...constraints, no_layoffs: v })}
        />
        <CheckboxField
          label="No new hires"
          checked={constraints.no_new_hires ?? false}
          onChange={(v) => onConstraintsChange({ ...constraints, no_new_hires: v })}
        />
      </div>

      <p className="text-xs text-ink-faint italic pt-2">Settings apply to the next analysis run.</p>
    </div>
  );
}
