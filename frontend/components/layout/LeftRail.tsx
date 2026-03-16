"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

interface LeftRailProps {
  activeNav: NavItem;
  onNavChange: (nav: NavItem) => void;
  settingsOpen: boolean;
  onSettingsToggle: () => void;
}

function IconAnalyze() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function IconLibrary() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function IconChevronLeft() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function IconChevronRight() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

// ProcessIQ icon mark — two overlapping rectangles suggesting a flow diagram
function IconMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2" y="6" width="8" height="6" rx="1.5" fill="#5a6272" opacity="0.9" />
      <rect x="14" y="12" width="8" height="6" rx="1.5" fill="#3d4450" opacity="0.7" />
      <line x1="10" y1="9" x2="14" y2="15" stroke="#5a6272" strokeWidth="1.5" strokeDasharray="2 2" />
    </svg>
  );
}

export type NavItem = "analyze" | "library" | "settings";

interface NavButtonProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  expanded: boolean;
  hasIndicator?: boolean;
  onClick: () => void;
}

function NavButton({ icon, label, active, expanded, hasIndicator, onClick }: NavButtonProps) {
  return (
    <button
      onClick={onClick}
      title={!expanded ? label : undefined}
      aria-label={label}
      className={cn(
        "relative flex items-center gap-3 w-full px-3 py-2.5 rounded-lg transition-all duration-100",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent",
        active
          ? "border-l-2 border-accent bg-dark-hover text-accent pl-[10px]"
          : "text-ink-muted hover:bg-dark-hover hover:text-ink border-l-2 border-transparent pl-[10px]"
      )}
    >
      <span className="flex-shrink-0 relative">
        {icon}
        {hasIndicator && (
          <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-accent" />
        )}
      </span>
      {expanded && (
        <span className="text-sm font-medium whitespace-nowrap overflow-hidden">{label}</span>
      )}
    </button>
  );
}

export function LeftRail({ activeNav, onNavChange, settingsOpen, onSettingsToggle }: LeftRailProps) {
  const [expanded, setExpanded] = useState(false);

  const COLLAPSED_WIDTH = 64;
  const EXPANDED_WIDTH = 260;

  return (
    <nav
      aria-label="Main navigation"
      className="flex-shrink-0 flex flex-col bg-dark-surface border-r border-dark-border overflow-hidden transition-all duration-[220ms] ease-out z-20"
      style={{ width: expanded ? EXPANDED_WIDTH : COLLAPSED_WIDTH }}
    >
      {/* Logo / icon mark */}
      <div className="flex items-center gap-3 px-3 py-4 border-b border-dark-border flex-shrink-0">
        <div className="flex-shrink-0">
          <IconMark size={28} />
        </div>
        {expanded && (
          <div className="overflow-hidden">
            <span className="text-sm font-bold text-ink tracking-tight whitespace-nowrap">ProcessIQ</span>
          </div>
        )}
        {/* Expand/collapse toggle */}
        <button
          onClick={() => setExpanded(!expanded)}
          className={cn(
            "ml-auto text-ink-faint hover:text-ink-muted transition-colors flex-shrink-0",
            !expanded && "mx-auto"
          )}
          title={expanded ? "Collapse rail" : "Expand rail"}
          aria-label={expanded ? "Collapse navigation" : "Expand navigation"}
        >
          {expanded ? <IconChevronLeft /> : <IconChevronRight />}
        </button>
      </div>

      {/* Nav items */}
      <div className="flex-1 flex flex-col gap-1 p-2 pt-3">
        <NavButton
          icon={<IconAnalyze />}
          label="Analyze"
          active={activeNav === "analyze"}
          expanded={expanded}
          onClick={() => onNavChange("analyze")}
        />
        <NavButton
          icon={<IconLibrary />}
          label="Library"
          active={activeNav === "library"}
          expanded={expanded}
          onClick={() => onNavChange("library")}
        />

        {/* Divider */}
        <div className="border-t border-dark-border my-1" />

        <NavButton
          icon={<IconSettings />}
          label="Settings"
          active={settingsOpen}
          expanded={expanded}
          hasIndicator={false}
          onClick={onSettingsToggle}
        />

      </div>

      {/* Bottom avatar placeholder */}
      <div className="border-t border-dark-border p-3 flex items-center gap-3">
        <div className="w-7 h-7 rounded-full bg-dark-hover border border-dark-border flex-shrink-0 flex items-center justify-center">
          <span className="text-xs text-ink-faint font-medium">U</span>
        </div>
        {expanded && (
          <span className="text-xs text-ink-muted truncate">Workspace</span>
        )}
      </div>
    </nav>
  );
}
