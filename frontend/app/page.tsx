"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type {
  AnalysisInsight,
  BusinessProfile,
  Constraints,
  GraphSchema,
  ProcessData,
} from "@/lib/types";
import { getGraphSchema } from "@/lib/api";
import { SettingsDrawer } from "@/components/settings/SettingsDrawer";
import { Header } from "@/components/layout/Header";
import { LeftRail } from "@/components/layout/LeftRail";
import { ContextStrip } from "@/components/layout/ContextStrip";
import { EmptyState } from "@/components/chat/EmptyState";
import { RevealTransition, computeHealth } from "@/components/layout/RevealTransition";

const ChatInterface = dynamic(
  () => import("@/components/chat/ChatInterface").then((m) => m.ChatInterface),
  { ssr: false }
);
const ProcessIntelligencePanel = dynamic(
  () => import("@/components/results/ProcessIntelligencePanel").then((m) => m.ProcessIntelligencePanel),
  { ssr: false }
);
const ProcessStepsTable = dynamic(
  () => import("@/components/process/ProcessStepsTable").then((m) => m.ProcessStepsTable),
  { ssr: false }
);

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULT_PROFILE: BusinessProfile = {
  industry: null,
  company_size: null,
  regulatory_environment: "moderate",
  typical_constraints: [],
  preferred_frameworks: [],
  previous_improvements: [],
  rejected_approaches: [],
  notes: "",
};

const DEFAULT_CONSTRAINTS: Constraints = {
  budget_limit: null,
  no_layoffs: false,
  no_new_hires: false,
  regulatory_requirements: [],
  timeline_weeks: null,
  technology_restrictions: [],
  custom_constraints: [],
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function HomePage() {
  const [processData, setProcessData] = useState<ProcessData | null>(null);
  const [insight, setInsight] = useState<AnalysisInsight | null>(null);
  const [graphSchema, setGraphSchema] = useState<GraphSchema | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [runLabel, setRunLabel] = useState<string | null>(null);
  const [highlightedSteps, setHighlightedSteps] = useState<string[]>([]);

  const [profile, setProfile] = useState<BusinessProfile>(DEFAULT_PROFILE);
  const [constraints, setConstraints] = useState<Constraints>(DEFAULT_CONSTRAINTS);
  const [analysisMode, setAnalysisMode] = useState("balanced");
  const [llmProvider, setLlmProvider] = useState<"anthropic" | "openai" | "ollama">("anthropic");
  const [maxCycles, setMaxCycles] = useState(3);

  // Settings panel open state — shared between LeftRail and Header settings gear
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Reveal transition: "idle" | "revealing" | "done"
  const [revealState, setRevealState] = useState<"idle" | "revealing" | "done">("idle");

  // Two-phase layout: hasResults drives the split-column view
  const hasResults = !!insight && revealState === "done";

  // Non-default settings indicator
  const hasNonDefaults =
    !!profile.industry ||
    !!profile.company_size ||
    !!constraints.no_layoffs ||
    !!constraints.budget_limit ||
    analysisMode !== "balanced" ||
    llmProvider !== "anthropic" ||
    maxCycles !== 3;

  // Whether the chat has any user messages (to decide empty state)
  const [hasMessages, setHasMessages] = useState(false);

  // Pending process data — mirrored from ChatInterface for Header button
  const [pendingProcessData, setPendingProcessData] = useState<ProcessData | null>(null);
  const [isAnalysisLoading, setIsAnalysisLoading] = useState(false);

  async function handleAnalysisComplete(
    newInsight: AnalysisInsight,
    newThreadId: string | null,
    label: string
  ) {
    setInsight(newInsight);
    setThreadId(newThreadId);
    setRunLabel(label);
    setHighlightedSteps([]);
    setIsAnalysisLoading(false);

    if (newThreadId) {
      try {
        const schema = await getGraphSchema(newThreadId);
        setGraphSchema(schema);
      } catch {
        setGraphSchema(null);
      }
    }

    // Trigger reveal transition
    setRevealState("revealing");
  }

  function handleRevealComplete() {
    setRevealState("done");
  }

  function handleProcessExtracted(data: ProcessData) {
    setProcessData(data);
    setPendingProcessData(data);
    setHasMessages(true);
  }

  const handleEmptyStatePrompt = useCallback((_text: string) => {
    setHasMessages(true);
  }, []);

  // Compute health for reveal transition
  const revealHealth = insight
    ? computeHealth(
        insight.issues?.filter((i) => i.severity === "high").length ?? 0,
        insight.issues?.length ?? 0
      )
    : "healthy";

  return (
    <div className="min-h-screen flex flex-col bg-dark-bg">
      {/* Reveal transition overlay */}
      {revealState === "revealing" && insight && (
        <RevealTransition health={revealHealth} onComplete={handleRevealComplete} />
      )}

      {/* Header */}
      <Header
        processName={processData?.name ?? null}
        sessionId={threadId}
        hasResults={hasResults}
        hasNonDefaultSettings={hasNonDefaults}
        pendingProcessData={!!pendingProcessData && !isAnalysisLoading && !hasResults}
        isLoading={isAnalysisLoading}
        onSettingsClick={() => setSettingsOpen(!settingsOpen)}
      />

      {/* Context strip — Phase 2 only, sticky below header */}
      {hasResults && insight && (
        <ContextStrip
          processName={processData?.name ?? runLabel ?? "Process"}
          insight={insight}
          processData={processData}
          constraints={constraints}
        />
      )}

      {/* Body: left rail + main content */}
      <div
        className="flex flex-1 overflow-hidden"
        style={{ height: hasResults ? "calc(100vh - 56px - 48px)" : "calc(100vh - 56px)" }}
      >
        {/* Left rail — always present */}
        <LeftRail
          settingsOpen={settingsOpen}
          onSettingsToggle={() => setSettingsOpen(!settingsOpen)}
        />

        {/* Settings sidebar panel — slide-in panel when settingsOpen */}
        {settingsOpen && (
          <div className="flex-shrink-0 w-72 bg-dark-surface border-r border-dark-border overflow-y-auto p-4 transition-all duration-[220ms] ease-out z-10">
            <p className="text-xs font-semibold text-ink-faint uppercase tracking-wide mb-4">
              Analysis Settings
            </p>
            <SettingsDrawer
              profile={profile}
              constraints={constraints}
              analysisMode={analysisMode}
              llmProvider={llmProvider}
              maxCycles={maxCycles}
              onProfileChange={setProfile}
              onConstraintsChange={setConstraints}
              onAnalysisModeChange={setAnalysisMode}
              onLlmProviderChange={setLlmProvider}
              onMaxCyclesChange={setMaxCycles}
            />
          </div>
        )}

        {/* Main content area */}
        <div className="flex flex-1 overflow-hidden transition-all duration-300 ease-in-out">

          {/* Chat column */}
          <div
            className="flex flex-col overflow-hidden transition-all duration-300 ease-in-out"
            style={{
              width: hasResults ? "40%" : "100%",
              borderRight: hasResults ? "1px solid #1e2d45" : "none",
            }}
          >
            <div
              className={`flex flex-col flex-1 overflow-hidden${!hasResults ? " dot-grid-bg" : ""}`}
              style={{ backgroundColor: hasResults ? "#0f1623" : "#080c14" }}
            >
              {/* Phase 1 empty state — shown before any messages */}
              {!hasResults && !hasMessages && (
                <div className="flex-shrink-0 pt-6">
                  <EmptyState onSelectPrompt={handleEmptyStatePrompt} />
                </div>
              )}

              {/* Chat — centered + constrained in Phase 1, full-width in Phase 2 */}
              <div
                className="flex flex-col transition-all duration-300"
                style={{
                  flex: 1,
                  maxWidth: hasResults ? "none" : "800px",
                  width: "100%",
                  margin: hasResults ? "0" : "0 auto",
                  padding: hasResults ? "16px 16px 0" : "0 24px 0",
                  minHeight: 0,
                }}
              >
                <ChatInterface
                  constraints={constraints}
                  profile={profile}
                  analysisMode={analysisMode}
                  llmProvider={llmProvider}
                  maxCyclesOverride={maxCycles !== 3 ? maxCycles : null}
                  hasResults={hasResults}
                  onProcessExtracted={handleProcessExtracted}
                  onAnalysisComplete={handleAnalysisComplete}
                />
              </div>

              {/* Process steps table */}
              {processData && (
                <div
                  className="flex-shrink-0 transition-all duration-300 pb-4"
                  style={{
                    maxWidth: hasResults ? "none" : "800px",
                    width: "100%",
                    margin: hasResults ? "0" : "0 auto",
                    padding: hasResults ? "0 16px" : "0 24px",
                  }}
                >
                  <ProcessStepsTable processData={processData} onChange={setProcessData} />
                </div>
              )}
            </div>
          </div>

          {/* Process Intelligence Panel — Phase 2 right column */}
          {hasResults && insight && (
            <main
              className="overflow-hidden bg-dark-bg"
              style={{
                width: "60%",
                animation: "fadeSlideIn 0.3s ease-out forwards",
              }}
            >
              <ProcessIntelligencePanel
                insight={insight}
                graphSchema={graphSchema}
                runLabel={runLabel}
                highlightedSteps={highlightedSteps}
                onHighlightSteps={setHighlightedSteps}
              />
            </main>
          )}
        </div>
      </div>
    </div>
  );
}
