"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { analyzeProcess, extractFile, extractText } from "@/lib/api";
import type {
  AnalysisInsight,
  BusinessProfile,
  Constraints,
  GraphSchema,
  ProcessData,
  UIMessage,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type AIStatus = "idle" | "extracting" | "analyzing" | "needs_clarification" | "error";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  isError?: boolean;
  summary?: string;
}

interface AnalysisRun {
  label: string;
  timestamp: string;
  messageIndex: number;
}

interface ChatInterfaceProps {
  constraints?: Constraints | null;
  profile?: BusinessProfile | null;
  analysisMode?: string | null;
  llmProvider?: "anthropic" | "openai" | "ollama" | null;
  maxCyclesOverride?: number | null;
  hasResults?: boolean;
  currentProcessData?: ProcessData | null;
  onProcessExtracted?: (data: ProcessData) => void;
  onAnalysisComplete?: (insight: AnalysisInsight, threadId: string | null, runLabel: string, graphSchema?: GraphSchema | null) => void;
}

const EXTRACTING_STEPS = [
  "Reading process description...",
  "Identifying process steps...",
  "Mapping dependencies between steps...",
  "Calculating time and cost metrics...",
  "Detecting step types and roles...",
  "Structuring process data...",
  "Validating extracted steps...",
];

const ANALYZING_STEPS = [
  "Investigating bottlenecks...",
  "Calculating efficiency metrics...",
  "Identifying root causes...",
  "Generating recommendations...",
  "Assessing feasibility...",
  "Prioritizing improvements...",
  "Finalizing analysis...",
];

function StatusChip({ status }: { status: AIStatus }) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (status !== "extracting" && status !== "analyzing") return;
    const steps = status === "extracting" ? EXTRACTING_STEPS : ANALYZING_STEPS;
    setStepIndex(0);
    const interval = setInterval(() => {
      setStepIndex((i) => (i + 1) % steps.length);
    }, 2800);
    return () => clearInterval(interval);
  }, [status]);

  if (status === "idle") return null;

  const staticConfig: Record<Exclude<AIStatus, "idle" | "extracting" | "analyzing">, { label: string; color: string }> = {
    needs_clarification: { label: "Waiting for your input", color: "bg-dark-card text-ink-muted border border-dark-border" },
    error: { label: "Something went wrong", color: "bg-red-950 text-red-400 border border-red-900" },
  };

  if (status === "extracting" || status === "analyzing") {
    const steps = status === "extracting" ? EXTRACTING_STEPS : ANALYZING_STEPS;
    const color = status === "extracting"
      ? "bg-accent-muted text-accent border border-accent/20"
      : "bg-dark-card text-ink-muted border border-dark-border";
    return (
      <div className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", color)}>
        <span className="w-1.5 h-1.5 rounded-full bg-current pulse-dot flex-shrink-0" />
        <span className="transition-all duration-300">{steps[stepIndex]}</span>
      </div>
    );
  }

  const { label, color } = staticConfig[status];
  return (
    <div className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", color)}>
      {label}
    </div>
  );
}

function MessageBubble({ msg, collapsed, onExpand }: {
  msg: ChatMessage; collapsed: boolean; onExpand?: () => void;
}) {
  if (collapsed && msg.summary) {
    return (
      <div className="flex justify-start">
        <button onClick={onExpand} className="text-xs text-ink-faint hover:text-ink-muted italic px-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
          {msg.summary} (expand)
        </button>
      </div>
    );
  }
  return (
    <div className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
      <div className={cn(
        "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed",
        msg.role === "user"
          // User: dark card + accent left border, no full cyan background
          ? "bg-dark-card border border-dark-border border-l-2 border-l-accent-strong font-medium text-ink rounded-br-sm"
          : msg.isError
          ? "bg-red-950 border border-red-800 text-red-300 rounded-bl-sm"
          : "bg-dark-card border border-dark-border text-ink rounded-bl-sm py-3"
      )}>
        {msg.content}
      </div>
    </div>
  );
}

// "Process Building" indicator pill shown in Phase 1 when process data exists
function ProcessBuildingIndicator({ processName }: { processName: string }) {
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-accent-muted border border-accent/20 text-accent">
      <span className="w-1.5 h-1.5 rounded-full bg-accent pulse-dot flex-shrink-0" />
      Building process model: {processName}
    </div>
  );
}

export function ChatInterface({
  constraints,
  profile,
  analysisMode,
  llmProvider,
  maxCyclesOverride,
  hasResults = false,
  currentProcessData,
  onProcessExtracted,
  onAnalysisComplete,
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    role: "assistant",
    content: "Describe your business process - the steps involved, roughly how long each takes, and any dependencies between them. You can also upload a file: PDF, Word document, Excel, CSV, PowerPoint, or image.",
    summary: "Initial prompt",
  }]);
  const [collapsedBefore, setCollapsedBefore] = useState(0);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<AIStatus>("idle");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pendingProcessData, setPendingProcessData] = useState<ProcessData | null>(null);
  // True when extraction returned new/edited process data that hasn't been re-analysed yet
  const [hasPendingEdit, setHasPendingEdit] = useState(false);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const submittingRef = useRef(false); // synchronous guard against concurrent submissions
  const isLoading = status === "extracting" || status === "analyzing";

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => {
      const next = [...prev, msg];
      if (next.length > 6) setCollapsedBefore(next.length - 6);
      return next;
    });
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }, []);

  useEffect(() => { if (!isLoading) inputRef.current?.focus(); }, [isLoading]);

  const uiMessages: UIMessage[] = useMemo(
    () => messages.map((m) => ({ role: m.role, content: m.content })),
    [messages]
  );

  const runAnalysis = useCallback(async (process: ProcessData) => {
    setStatus("analyzing");
    addMessage({ role: "assistant", content: "Running analysis..." });
    const timestamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const runLabel = `${process.name} at ${timestamp}`;
    try {
      const result = await analyzeProcess({ process, constraints, profile, thread_id: threadId, analysis_mode: analysisMode, llm_provider: llmProvider ?? null, max_cycles_override: maxCyclesOverride ?? null });
      if (result.thread_id) setThreadId(result.thread_id);
      if (result.is_error || !result.analysis_insight) {
        addMessage({ role: "assistant", content: result.message || "Analysis failed. Please try again.", isError: true });
        setStatus("error"); setTimeout(() => setStatus("idle"), 2000); return;
      }
      setAnalysisRuns((prev) => [...prev, { label: runLabel, timestamp, messageIndex: messages.length }]);
      addMessage({ role: "assistant", content: `Analysis complete - results shown on the right. (Run: ${runLabel})`, summary: `Analysis: ${runLabel}` });
      setStatus("idle");
      setHasPendingEdit(false);
      onAnalysisComplete?.(result.analysis_insight, result.thread_id ?? null, runLabel, result.graph_schema);
    } catch (err) {
      addMessage({ role: "assistant", content: `Analysis error: ${err instanceof Error ? err.message : "Unknown error"}`, isError: true });
      setStatus("error"); setTimeout(() => setStatus("idle"), 2000);
    }
  }, [constraints, profile, threadId, analysisMode, llmProvider, maxCyclesOverride, messages.length, addMessage, onAnalysisComplete]);

  const handleTextSubmit = useCallback(async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || isLoading || submittingRef.current) return;
    submittingRef.current = true;
    if (!overrideText) setInput("");
    addMessage({ role: "user", content: text, summary: `You: "${text.slice(0, 40)}${text.length > 40 ? "..." : ""}"` });
    try {
      if (pendingProcessData && /^(yes|confirm|ok|looks? good|correct|run|analyze)\.?$/i.test(text)) {
        await runAnalysis(pendingProcessData); return;
      }
      // After analysis has run, use the confirmed process data as context for edits
      const activeProcessData = pendingProcessData ?? (hasResults ? currentProcessData : null);

      setStatus("extracting");
      const result = await extractText({ text, analysis_mode: analysisMode, current_process_data: activeProcessData ?? undefined, ui_messages: uiMessages, constraints, profile, llm_provider: llmProvider ?? null });
      if (result.is_error) {
        addMessage({ role: "assistant", content: result.message, isError: true });
        setStatus("error"); setTimeout(() => setStatus("idle"), 2000); return;
      }
      setStatus(result.needs_input ? "needs_clarification" : "idle");
      addMessage({ role: "assistant", content: result.message, summary: `Assistant: "${result.message.slice(0, 40)}${result.message.length > 40 ? "..." : ""}"` });
      if (result.process_data) {
        setPendingProcessData(result.process_data);
        onProcessExtracted?.(result.process_data);
        if (!result.needs_input) {
          setStatus("idle");
          // Mark as pending edit so the re-analyse button appears (only after first analysis)
          if (hasResults) setHasPendingEdit(true);
        } else if (hasResults) {
          // needs_input=true but we still have updated data — show re-analyse button
          setHasPendingEdit(true);
        }
      }
      if (result.improvement_suggestions) addMessage({ role: "assistant", content: result.improvement_suggestions, summary: "Assistant: improvement suggestions" });
    } catch (err) {
      addMessage({ role: "assistant", content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`, isError: true });
      setStatus("error"); setTimeout(() => setStatus("idle"), 2000);
    } finally {
      submittingRef.current = false;
    }
  }, [input, isLoading, pendingProcessData, hasResults, currentProcessData, analysisMode, uiMessages, constraints, profile, addMessage, runAnalysis, onProcessExtracted]);

  const handleFileUpload = useCallback(async (file: File) => {
    addMessage({ role: "user", content: `Uploaded: ${file.name}`, summary: `You: uploaded ${file.name}` });
    setStatus("extracting");
    try {
      const result = await extractFile(file, analysisMode, llmProvider);
      setStatus("idle");
      addMessage({ role: "assistant", content: result.message });
      if (result.process_data) { setPendingProcessData(result.process_data); onProcessExtracted?.(result.process_data); }
    } catch (err) {
      addMessage({ role: "assistant", content: `Upload error: ${err instanceof Error ? err.message : "Unknown error"}`, isError: true });
      setStatus("error"); setTimeout(() => setStatus("idle"), 2000);
    }
  }, [analysisMode, llmProvider, addMessage, onProcessExtracted]);

  // Expose run analysis trigger for parent (via Header button)
  const handleRunAnalysis = useCallback(() => {
    if (pendingProcessData && !isLoading) runAnalysis(pendingProcessData);
  }, [pendingProcessData, isLoading, runAnalysis]);

  return (
    <div
      className={cn(
        "flex flex-col h-full rounded-xl overflow-hidden transition-all duration-300",
        // Phase 1: glowing border; Phase 2: plain surface
        hasResults
          ? "border border-dark-border bg-dark-surface"
          : "border border-dark-border bg-dark-card shadow-chat-glow"
      )}
    >
      {/* Status bar */}
      <div className={cn(
        "px-4 py-2 border-b text-xs flex items-center justify-between transition-colors flex-shrink-0",
        pendingProcessData
          ? "bg-accent-muted border-accent/20"
          : "bg-dark-surface border-dark-border"
      )}>
        <div className="flex items-center gap-2">
          <span className={cn("font-medium", pendingProcessData ? "text-accent" : "text-ink-faint")}>
            {pendingProcessData ? `Loaded: ${pendingProcessData.name}` : "No process loaded"}
          </span>
          {pendingProcessData && !hasResults && (
            <ProcessBuildingIndicator processName={pendingProcessData.name} />
          )}
        </div>
        {analysisRuns.length > 0 && (
          <span className="text-ink-faint">{analysisRuns.length} run{analysisRuns.length !== 1 ? "s" : ""}</span>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} collapsed={i < collapsedBefore} onExpand={() => setCollapsedBefore(0)} />
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-dark-card border border-dark-border rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-ink-faint animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-ink-faint animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-ink-faint animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Run analysis button — shown before first analysis, or after an edit is confirmed */}
      {pendingProcessData && !isLoading && (!hasResults || hasPendingEdit) && (
        <div className="px-4 pb-2 flex-shrink-0">
          <button
            onClick={handleRunAnalysis}
            className="w-full py-2 text-sm font-semibold rounded-lg bg-accent text-dark-bg hover:bg-accent/90 hover:shadow-btn-accent transition-all duration-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            {hasResults ? `Re-analyse — ${pendingProcessData.name}` : `Run Analysis — ${pendingProcessData.name}`}
          </button>
        </div>
      )}

      {status !== "idle" && (
        <div className="px-4 pb-2 flex-shrink-0">
          <StatusChip status={status} />
        </div>
      )}

      {/* Input bar */}
      <div className="border-t border-dark-border p-3 flex gap-2 items-center bg-dark-surface flex-shrink-0">
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          title="Upload a file (PDF, Word, Excel, CSV, PowerPoint, image)"
          aria-label="Upload file"
          className="text-ink-faint hover:text-ink-muted disabled:opacity-40 transition-colors flex-shrink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent rounded"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="12" y1="18" x2="12" y2="12" />
            <line x1="9" y1="15" x2="15" y2="15" />
          </svg>
        </button>
        <input
          type="file"
          ref={fileInputRef}
          className="hidden"
          accept=".csv,.xlsx,.xls,.pdf,.docx"
          onChange={(e) => { const file = e.target.files?.[0]; if (file) handleFileUpload(file); e.target.value = ""; }}
        />
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleTextSubmit(); } }}
          disabled={isLoading}
          placeholder={pendingProcessData ? `Edit ${pendingProcessData.name} or type "run" to analyze...` : "Describe your process..."}
          className="flex-1 text-sm border border-dark-border rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 disabled:opacity-50 bg-dark-card text-ink placeholder:text-ink-faint transition-colors focus-visible:outline-none"
        />
        <button
          onClick={() => handleTextSubmit()}
          disabled={isLoading || !input.trim()}
          aria-label="Send message"
          className="text-accent hover:text-accent/80 disabled:opacity-40 transition-colors flex-shrink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent rounded"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
      <p className="px-4 pb-2 text-xs text-ink-faint flex-shrink-0">
        Attach a file using the icon above &mdash; PDF, Word, Excel, CSV, PowerPoint, or image
      </p>
    </div>
  );
}
