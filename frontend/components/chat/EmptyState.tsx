"use client";

// CSS-animated flow/network glyph — no emoji
function FlowGlyph() {
  return (
    <div className="relative w-16 h-16 mx-auto mb-6">
      <svg
        width="64"
        height="64"
        viewBox="0 0 64 64"
        fill="none"
        aria-hidden="true"
        className="overflow-visible"
      >
        {/* Connecting lines — drawn first so nodes render on top */}
        <line x1="16" y1="16" x2="32" y2="32" stroke="#19b7c0" strokeWidth="1.5" strokeDasharray="3 3" opacity="0.5" />
        <line x1="48" y1="16" x2="32" y2="32" stroke="#19b7c0" strokeWidth="1.5" strokeDasharray="3 3" opacity="0.5" />
        <line x1="32" y1="32" x2="32" y2="52" stroke="#19b7c0" strokeWidth="1.5" strokeDasharray="3 3" opacity="0.5" />

        {/* Nodes */}
        <circle cx="16" cy="16" r="5" fill="#141d2e" stroke="#19b7c0" strokeWidth="1.5" />
        <circle cx="48" cy="16" r="5" fill="#141d2e" stroke="#19b7c0" strokeWidth="1.5" />
        {/* Central node — slightly larger, pulsing */}
        <circle cx="32" cy="32" r="7" fill="#19b7c0" opacity="0.15" />
        <circle cx="32" cy="32" r="5" fill="#141d2e" stroke="#22d3ee" strokeWidth="2" />
        <circle cx="32" cy="32" r="2.5" fill="#22d3ee" />
        {/* Output node */}
        <circle cx="32" cy="52" r="5" fill="#141d2e" stroke="#19b7c0" strokeWidth="1.5" />

        {/* Outer pulse ring — animated via CSS */}
        <circle
          cx="32"
          cy="32"
          r="14"
          fill="none"
          stroke="#19b7c0"
          strokeWidth="1"
          opacity="0.2"
          className="pulse-dot"
        />
      </svg>
    </div>
  );
}

interface ExampleChipProps {
  text: string;
  onClick: (text: string) => void;
}

function ExampleChip({ text, onClick }: ExampleChipProps) {
  return (
    <button
      onClick={() => onClick(text)}
      className="w-full text-left text-sm text-ink-muted border border-dark-border rounded-lg px-4 py-3 bg-dark-card hover:bg-dark-hover hover:border-accent/30 hover:text-ink transition-all duration-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
    >
      <span className="text-ink-faint mr-2 text-xs">&ldquo;</span>
      {text}
      <span className="text-ink-faint ml-0.5 text-xs">&rdquo;</span>
    </button>
  );
}

const EXAMPLE_PROMPTS = [
  "Our invoice approval takes 3 days and involves 4 departments...",
  "We onboard new employees across 6 steps but keep losing track after step 3...",
  "Our customer support process involves triage, escalation, and resolution but the SLA keeps slipping...",
];

interface EmptyStateProps {
  onSelectPrompt: (text: string) => void;
}

export function EmptyState({ onSelectPrompt }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center text-center px-6 py-8 max-w-xl mx-auto">
      <FlowGlyph />

      <h2 className="text-3xl font-bold text-ink mb-3 tracking-tight leading-tight">
        Describe your business process
      </h2>
      <p className="text-[15px] text-ink-muted leading-relaxed mb-8 max-w-md">
        Start by walking me through your workflow &mdash; step by step, in plain language.
        I&rsquo;ll extract the structure, identify bottlenecks, and surface what&rsquo;s costing you time and money.
      </p>

      {/* Example prompt chips */}
      <div className="w-full space-y-2 mb-6">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <ExampleChip key={prompt} text={prompt} onClick={onSelectPrompt} />
        ))}
      </div>

      <p className="text-xs text-ink-faint">
        Be as specific as possible &mdash; include who does what, how long each step takes, and where things go wrong.
      </p>
    </div>
  );
}
