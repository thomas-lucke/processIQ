"use client";

import { useCallback, useEffect, useState } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Edge,
  Node,
  useNodesState,
  useEdgesState,
} from "reactflow";
import "reactflow/dist/style.css";
import type { GraphSchema, Severity } from "@/lib/types";

const SEVERITY_COLORS: Record<Severity, string> = {
  high: "#ef4444",
  medium: "#f97316",
  core_value: "#22c55e",
  recommendation_affected: "#22d3ee",
  normal: "#334155",
};

const SEVERITY_LABELS: Record<Severity, string> = {
  high: "Bottleneck",
  medium: "At risk",
  core_value: "Core value",
  recommendation_affected: "Recommendation impact",
  normal: "Normal",
};

interface ProcessGraphProps {
  schema: GraphSchema;
  highlightedSteps?: string[];
}

function buildReactFlowData(
  schema: GraphSchema,
  showAfter: boolean,
  highlightedSteps: Set<string>
): { nodes: Node[]; edges: Edge[] } {
  const sourceNodes = showAfter ? schema.after_nodes : schema.before_nodes;

  const nodes: Node[] = sourceNodes.map((n) => {
    const isHighlighted = highlightedSteps.has(n.step_name);
    return {
      id: n.step_name,
      position: { x: n.x * 220, y: n.y * 130 },
      data: { label: n.step_name, hoverText: n.hover_text, severity: n.severity },
      style: {
        backgroundColor: SEVERITY_COLORS[n.severity],
        color: "#e2e8f0",
        borderRadius: 8,
        fontSize: 12,
        fontWeight: 500,
        border: isHighlighted ? "2px solid #fbbf24" : "1px solid rgba(255,255,255,0.1)",
        padding: "8px 12px",
        width: Math.max(120, n.time_pct * 2.5),
        textAlign: "center" as const,
        boxShadow: isHighlighted
          ? "0 0 0 3px rgba(251,191,36,0.3), 0 2px 8px rgba(0,0,0,0.5)"
          : "0 2px 8px rgba(0,0,0,0.4)",
        transition: "box-shadow 0.2s, border 0.2s",
      },
    };
  });

  const edges: Edge[] = schema.edges.map((e) => ({
    id: `${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    type: "smoothstep",
    animated: false,
    style: { stroke: "#3d5270", strokeWidth: 1.5 },
    markerEnd: { type: "arrowclosed" as const, color: "#3d5270" },
  }));

  return { nodes, edges };
}

export function ProcessGraph({ schema, highlightedSteps = [] }: ProcessGraphProps) {
  const [showAfter, setShowAfter] = useState(false);
  const highlightSet = new Set(highlightedSteps);

  const { nodes: initialNodes, edges: initialEdges } = buildReactFlowData(schema, false, highlightSet);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    const { nodes: newNodes } = buildReactFlowData(schema, showAfter, highlightSet);
    setNodes(newNodes);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showAfter, highlightedSteps.join(","), schema]);

  const toggleAfter = useCallback((next: boolean) => setShowAfter(next), []);

  const hasAfterDiff =
    JSON.stringify(schema.before_nodes.map((n) => n.severity)) !==
    JSON.stringify(schema.after_nodes.map((n) => n.severity));

  return (
    <div className="space-y-3">
      {/* Toggle */}
      {hasAfterDiff && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-ink-muted">View:</span>
          <div className="flex rounded-lg overflow-hidden border border-dark-border text-xs">
            <button
              onClick={() => toggleAfter(false)}
              className={`px-3 py-1.5 transition-colors ${
                !showAfter
                  ? "bg-accent text-dark-bg font-semibold"
                  : "bg-dark-card text-ink-muted hover:bg-dark-hover"
              }`}
            >
              Current state
            </button>
            <button
              onClick={() => toggleAfter(true)}
              className={`px-3 py-1.5 transition-colors border-l border-dark-border ${
                showAfter
                  ? "bg-accent text-dark-bg font-semibold"
                  : "bg-dark-card text-ink-muted hover:bg-dark-hover"
              }`}
            >
              After top recommendation
            </button>
          </div>
        </div>
      )}

      {/* Highlighted steps info bar */}
      {highlightedSteps.length > 0 && (
        <div className="text-xs text-amber-400 bg-amber-950/40 border border-amber-800/50 rounded-lg px-3 py-1.5 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
          Highlighting: {highlightedSteps.join(", ")}
        </div>
      )}

      {/* Graph */}
      <div className="border border-dark-border rounded-xl overflow-hidden" style={{ height: 480 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e2d45" gap={20} variant={BackgroundVariant.Dots} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs text-ink-muted items-center">
        {(Object.entries(SEVERITY_COLORS) as [Severity, string][]).map(([key, color]) => (
          <div key={key} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
            {SEVERITY_LABELS[key]}
          </div>
        ))}
        <div className="flex items-center gap-1.5 ml-1 pl-3 border-l border-dark-border">
          <span className="inline-block w-3 h-3 rounded-full flex-shrink-0 bg-amber-400 ring-2 ring-amber-500/50" />
          Highlighted
        </div>
        <span className="ml-auto text-ink-faint italic">Node width = time share</span>
      </div>
    </div>
  );
}
