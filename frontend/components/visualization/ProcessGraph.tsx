"use client";

import { useCallback, useEffect, useState } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Edge,
  Handle,
  MarkerType,
  MiniMap,
  Node,
  NodeProps,
  Position,
  useEdgesState,
  useNodesState,
} from "reactflow";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — CSS side-effect import, no type declarations needed
import "reactflow/dist/style.css";
import type { GraphSchema, Severity } from "@/lib/types";

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const COL_SPACING = 180;  // px per x unit (horizontal step spacing)
const ROW_SPACING = 140;  // px per y unit (lane spacing for branching processes)

// ---------------------------------------------------------------------------
// Color scheme: 3 states only
// ---------------------------------------------------------------------------

const SEVERITY_FILL: Record<Severity, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  core_value: "#22c55e",
  recommendation_affected: "#22c55e",
  normal: "#22c55e",
};

const SEVERITY_MINIMAP: Record<Severity, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  core_value: "#22c55e",
  recommendation_affected: "#22c55e",
  normal: "#22c55e",
};

// ---------------------------------------------------------------------------
// Custom node: circle with hover tooltip
// ---------------------------------------------------------------------------

interface ProcessNodeData {
  label: string;
  hoverText: string;
  severity: Severity;
  size: number;          // diameter in px
  isHighlighted: boolean;
  showRecOutline: boolean;  // yellow ring for recommendation_affected in after-view
}

function ProcessNode({ data }: NodeProps<ProcessNodeData>) {
  const [hovered, setHovered] = useState(false);
  const fill = SEVERITY_FILL[data.severity] ?? "#22c55e";

  const borderStyle = data.isHighlighted
    ? "3px solid #fbbf24"
    : data.showRecOutline && data.severity === "recommendation_affected"
    ? "3px solid #facc15"
    : data.severity === "high" || data.severity === "medium"
    ? "2px solid rgba(255,255,255,0.3)"
    : "2px solid rgba(255,255,255,0.15)";

  const shadow = data.isHighlighted
    ? "0 0 0 4px rgba(251,191,36,0.25), 0 4px 16px rgba(0,0,0,0.6)"
    : "0 2px 12px rgba(0,0,0,0.5)";

  // Tooltip lines — hoverText uses <br> separator from Python
  const tooltipLines = data.hoverText.split("<br>");

  return (
    <div
      style={{ position: "relative", width: data.size, height: data.size }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Handles for left-to-right flow */}
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />

      {/* Circle */}
      <div
        style={{
          width: data.size,
          height: data.size,
          borderRadius: "50%",
          backgroundColor: fill,
          border: borderStyle,
          boxShadow: shadow,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "default",
          transition: "box-shadow 0.15s, border 0.15s",
        }}
      />

      {/* Label below */}
      <div
        style={{
          position: "absolute",
          top: data.size + 6,
          left: "50%",
          transform: "translateX(-50%)",
          whiteSpace: "nowrap",
          fontSize: 11,
          fontWeight: 500,
          color: "#cbd5e1",
          pointerEvents: "none",
          maxWidth: 160,
          overflow: "hidden",
          textOverflow: "ellipsis",
          textAlign: "center",
        }}
      >
        {data.label}
      </div>

      {/* Hover tooltip */}
      {hovered && (
        <div
          style={{
            position: "absolute",
            bottom: data.size + 10,
            left: "50%",
            transform: "translateX(-50%)",
            backgroundColor: "#1e293b",
            border: "1px solid #475569",
            borderRadius: 8,
            padding: "8px 12px",
            zIndex: 9999,
            whiteSpace: "nowrap",
            pointerEvents: "none",
            boxShadow: "0 4px 20px rgba(0,0,0,0.7)",
          }}
        >
          {tooltipLines.map((line, i) => (
            <div
              key={i}
              style={{
                fontSize: i === 0 ? 12 : 11,
                fontWeight: i === 0 ? 600 : 400,
                color: i === 0 ? "#f1f5f9" : "#94a3b8",
                lineHeight: "1.6",
              }}
            >
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const NODE_TYPES = { processNode: ProcessNode };

// ---------------------------------------------------------------------------
// Size calculation — matches Python _node_size()
// ---------------------------------------------------------------------------

const SEVERITY_SIZE_BOOST: Record<Severity, number> = {
  high: 20,
  medium: 10,
  core_value: 0,
  recommendation_affected: 0,
  normal: 0,
};
const MIN_NODE_SIZE = 28;
const MAX_NODE_SIZE = 70;

function nodeSize(timePct: number, severity: Severity): number {
  const base = Math.round(timePct * 1.2) + MIN_NODE_SIZE;
  const boost = SEVERITY_SIZE_BOOST[severity] ?? 0;
  return Math.min(MAX_NODE_SIZE, base + boost);
}

// ---------------------------------------------------------------------------
// Build ReactFlow nodes and edges from GraphSchema
// ---------------------------------------------------------------------------

function buildReactFlowData(
  schema: GraphSchema,
  showAfter: boolean,
  highlightedSteps: Set<string>
): { nodes: Node[]; edges: Edge[] } {
  const sourceNodes = showAfter ? schema.after_nodes : schema.before_nodes;

  const nodes: Node[] = sourceNodes.map((n) => {
    const size = nodeSize(n.time_pct, n.severity);
    return {
      id: n.step_name,
      type: "processNode",
      // x = horizontal position, y = lane (0 for linear, fractional for parallel)
      position: { x: n.x * COL_SPACING - size / 2, y: n.y * ROW_SPACING - size / 2 },
      data: {
        label: n.step_name,
        hoverText: n.hover_text,
        severity: n.severity,
        size,
        isHighlighted: highlightedSteps.has(n.step_name),
        showRecOutline: showAfter,
      } satisfies ProcessNodeData,
    };
  });

  const edges: Edge[] = schema.edges.map((e) => ({
    id: `${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    type: "smoothstep",
    animated: false,
    style: { stroke: "#3d5270", strokeWidth: 1.5 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#3d5270" },
  }));

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Compute container height from the node y-range
// ---------------------------------------------------------------------------

function computeHeight(schema: GraphSchema, showAfter: boolean): number {
  const sourceNodes = showAfter ? schema.after_nodes : schema.before_nodes;
  if (sourceNodes.length === 0) return 220;
  const maxY = Math.max(...sourceNodes.map((n) => n.y));
  // One row = ROW_SPACING; add padding for label below node + top/bottom margin
  return Math.max(220, (maxY + 1) * ROW_SPACING + 100);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ProcessGraphProps {
  schema: GraphSchema;
  highlightedSteps?: string[];
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

  const containerHeight = computeHeight(schema, showAfter);

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
      <div
        className="border border-dark-border rounded-xl overflow-hidden"
        style={{ height: containerHeight }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          nodeTypes={NODE_TYPES}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e2d45" gap={20} variant={BackgroundVariant.Dots} />
          <Controls showInteractive={false} />
          <MiniMap
            nodeColor={(n) => {
              const data = n.data as ProcessNodeData;
              return SEVERITY_MINIMAP[data.severity] ?? "#22c55e";
            }}
            maskColor="rgba(15, 23, 42, 0.7)"
            style={{ backgroundColor: "#0f172a", border: "1px solid #1e293b" }}
          />
        </ReactFlow>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-ink-muted items-center">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-full flex-shrink-0 bg-red-500" />
          Bottleneck
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-full flex-shrink-0 bg-amber-500" />
          Needs attention
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-full flex-shrink-0 bg-green-500" />
          Running well
        </div>
        {hasAfterDiff && (
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full flex-shrink-0 ring-2 ring-yellow-400 bg-green-500" />
            Fix planned
          </div>
        )}
        <span className="ml-auto text-ink-faint italic">Node size = time share</span>
      </div>
    </div>
  );
}
