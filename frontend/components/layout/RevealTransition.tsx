"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Health = "critical" | "at-risk" | "healthy";

interface RevealTransitionProps {
  health: Health;
  onComplete: () => void;
}

/**
 * Three-step reveal animation fired once when the first analysis completes:
 * 1. Full-canvas cyan flash (150ms) — subtle "system ping"
 * 2. Health score badge appears center-screen (600ms) — the "payoff moment"
 * 3. Callback fires → parent transitions to two-column layout (300ms CSS transition)
 *
 * Check this component manually after implementation — it is the most complex
 * animation sequence and may need timing adjustments on your device.
 */
export function RevealTransition({ health, onComplete }: RevealTransitionProps) {
  // Phase: "flash" → "badge" → "done"
  const [phase, setPhase] = useState<"flash" | "badge" | "done">("flash");

  useEffect(() => {
    // Step 1: flash for 150ms
    const flashTimer = setTimeout(() => {
      setPhase("badge");
    }, 150);

    // Step 2: badge visible for 600ms, then trigger layout transition
    const badgeTimer = setTimeout(() => {
      setPhase("done");
      onComplete();
    }, 150 + 600);

    return () => {
      clearTimeout(flashTimer);
      clearTimeout(badgeTimer);
    };
  }, [onComplete]);

  if (phase === "done") return null;

  const healthConfig: Record<Health, { label: string; color: string; bg: string; border: string }> = {
    critical: {
      label: "Critical Issues Found",
      color: "text-status-danger",
      bg: "bg-red-950/90",
      border: "border-status-danger/60",
    },
    "at-risk": {
      label: "Improvement Opportunities",
      color: "text-status-warning",
      bg: "bg-amber-950/90",
      border: "border-status-warning/60",
    },
    healthy: {
      label: "Process Is Healthy",
      color: "text-status-success",
      bg: "bg-emerald-950/90",
      border: "border-status-success/60",
    },
  };

  const config = healthConfig[health];

  return (
    // Full-page overlay — pointer-events-none so it doesn't block interaction
    <div className="fixed inset-0 z-50 pointer-events-none">
      {/* Step 1: Flash overlay */}
      <div
        className={cn(
          "absolute inset-0 transition-opacity",
          phase === "flash" ? "opacity-100" : "opacity-0"
        )}
        style={{
          background: "rgba(25,183,192,0.03)",
          transition: "opacity 150ms ease",
        }}
      />

      {/* Step 2: Health score badge — centered, appears after flash */}
      {phase === "badge" && (
        <div
          className="absolute"
          style={{
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            animation: "healthScoreAppear 600ms ease-in-out forwards",
          }}
        >
          <div className={cn(
            "px-10 py-6 rounded-2xl border-2 shadow-2xl backdrop-blur-sm",
            config.bg,
            config.border,
          )}>
            <p className="text-xs font-semibold text-ink-faint uppercase tracking-wider mb-2 text-center">
              Analysis complete
            </p>
            <p className={cn("text-2xl font-bold text-center", config.color)}>
              {config.label}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Computes health from AnalysisInsight — extracted here so RevealTransition
 * can be called with a plain string type (no insight import needed at call site).
 */
export function computeHealth(highIssues: number, totalIssues: number): Health {
  if (highIssues >= 2) return "critical";
  if (highIssues === 1 || totalIssues >= 3) return "at-risk";
  return "healthy";
}
