// TODO: wire to real API — this file exists for UI development and testing only.
// Remove or replace with real data once all panels are connected to the backend.

import type { AnalysisInsight, GraphSchema, ProcessData } from "./types";

export const MOCK_PROCESS_DATA: ProcessData = {
  name: "Invoice Approval Process",
  description: "End-to-end invoice approval from submission to payment",
  steps: [
    { step_name: "Invoice Submission", average_time_hours: 0.5, resources_needed: 1, error_rate_pct: 5, cost_per_instance: 20 },
    { step_name: "Initial Review", average_time_hours: 4, resources_needed: 1, error_rate_pct: 12, cost_per_instance: 80 },
    { step_name: "Department Approval", average_time_hours: 16, resources_needed: 2, error_rate_pct: 8, cost_per_instance: 200, depends_on: ["Initial Review"] },
    { step_name: "Finance Validation", average_time_hours: 8, resources_needed: 1, error_rate_pct: 15, cost_per_instance: 120, depends_on: ["Department Approval"] },
    { step_name: "CFO Sign-off", average_time_hours: 24, resources_needed: 1, error_rate_pct: 3, cost_per_instance: 400, depends_on: ["Finance Validation"] },
    { step_name: "Payment Processing", average_time_hours: 2, resources_needed: 1, error_rate_pct: 2, cost_per_instance: 40, depends_on: ["CFO Sign-off"] },
  ],
};

export const MOCK_INSIGHT: AnalysisInsight = {
  process_summary:
    "The invoice approval process is significantly over-resourced for its volume. The CFO sign-off bottleneck is causing 3-day average delays, inflating cost-per-invoice to ~$860. Two structural issues are driving the bulk of the problem.",
  patterns: [
    "Sequential approvals with no parallel tracks add 48+ hours of wait time",
    "Department approval has the highest error-rate-to-cost ratio in the chain",
    "Finance validation is redundant given the initial review scope",
  ],
  issues: [
    {
      title: "CFO sign-off creates single-point bottleneck",
      description:
        "All invoices above €500 require CFO approval regardless of amount, creating a 24-hour average wait on a single resource.",
      affected_steps: ["CFO Sign-off"],
      severity: "high",
      root_cause_hypothesis: "Approval policy was not tiered when the company scaled past 50 employees.",
      evidence: [
        "CFO sign-off averages 24h vs 4h for comparable steps",
        "No delegation exists for invoices under €5,000",
      ],
    },
    {
      title: "Finance validation duplicates initial review",
      description:
        "Finance Validation re-checks 70% of the same fields as Initial Review, with a higher error rate (15% vs 12%).",
      affected_steps: ["Finance Validation", "Initial Review"],
      severity: "high",
      root_cause_hypothesis: "Processes were designed by separate teams without overlap analysis.",
      evidence: ["Field-by-field comparison shows 72% overlap in validation criteria"],
    },
    {
      title: "Department approval SLA undefined",
      description: "No SLA exists for Department Approval, leading to average 16h delays with high variance.",
      affected_steps: ["Department Approval"],
      severity: "medium",
    },
  ],
  recommendations: [
    {
      title: "Implement tiered approval thresholds",
      addresses_issue: "CFO sign-off creates single-point bottleneck",
      description:
        "Define three approval tiers: < €1k auto-approve, €1k–€10k department head, > €10k CFO. Eliminates ~85% of CFO queue.",
      expected_benefit: "Reduce average cycle time from 72h to 18h for invoices under €10k",
      estimated_roi: "~€28,000/month in staff time recovered",
      feasibility: "easy",
      affected_steps: ["CFO Sign-off", "Department Approval"],
      concrete_next_steps: [
        "Define threshold bands with finance team",
        "Update approval policy document",
        "Configure approval routing in ERP",
        "Communicate changes to all department heads",
      ],
      risks: ["Requires CFO buy-in on threshold amounts"],
    },
    {
      title: "Merge finance validation into initial review",
      addresses_issue: "Finance validation duplicates initial review",
      description:
        "Consolidate the two review steps into a single structured checklist completed once by a trained finance analyst.",
      expected_benefit: "Remove one full step, saving €120/invoice and reducing process steps from 6 to 5",
      feasibility: "moderate",
      affected_steps: ["Finance Validation", "Initial Review"],
      concrete_next_steps: [
        "Map all validation criteria from both steps",
        "Create unified checklist",
        "Train 2 analysts on combined scope",
        "Run parallel for 2 weeks before cutover",
      ],
    },
    {
      title: "Set 4-hour SLA for department approval",
      addresses_issue: "Department approval SLA undefined",
      description: "Introduce a 4-hour response SLA with auto-escalation to department deputy after 4h.",
      expected_benefit: "Reduce department approval average from 16h to under 5h",
      feasibility: "easy",
      affected_steps: ["Department Approval"],
    },
  ],
  not_problems: [
    {
      step_name: "Invoice Submission",
      why_not_a_problem: "Error rate of 5% is within acceptable range for self-service submission. Further automation would likely yield < 1% efficiency gain.",
      appears_problematic_because: "It's the first step and often blamed for downstream errors",
    },
  ],
  follow_up_questions: [
    "What is the monthly invoice volume? This affects whether automation investment is justified.",
    "Are there regulatory requirements driving the current CFO sign-off policy?",
    "Does your ERP support conditional approval routing natively?",
  ],
  confidence_notes:
    "High confidence on bottleneck identification. Moderate confidence on ROI estimates — based on industry benchmarks, not your actual staff costs.",
};

export const MOCK_GRAPH_SCHEMA: GraphSchema = {
  before_nodes: [
    { step_name: "Invoice Submission", x: 0, y: 0, time_pct: 1, severity: "normal", hover_text: "Invoice Submission: 0.5h, €20" },
    { step_name: "Initial Review", x: 1, y: 0, time_pct: 8, severity: "medium", hover_text: "Initial Review: 4h, €80, error rate 12%" },
    { step_name: "Department Approval", x: 2, y: 0, time_pct: 30, severity: "medium", hover_text: "Department Approval: 16h, €200" },
    { step_name: "Finance Validation", x: 3, y: 0, time_pct: 15, severity: "high", hover_text: "Finance Validation: 8h, €120, error rate 15%" },
    { step_name: "CFO Sign-off", x: 4, y: 0, time_pct: 45, severity: "high", hover_text: "CFO Sign-off: 24h, €400 — bottleneck" },
    { step_name: "Payment Processing", x: 5, y: 0, time_pct: 4, severity: "core_value", hover_text: "Payment Processing: 2h, €40" },
  ],
  after_nodes: [
    { step_name: "Invoice Submission", x: 0, y: 0, time_pct: 1, severity: "normal", hover_text: "Invoice Submission: 0.5h, €20" },
    { step_name: "Unified Review", x: 1, y: 0, time_pct: 12, severity: "normal", hover_text: "Unified Review (merged): 4h, €80" },
    { step_name: "Department Approval", x: 2, y: 0, time_pct: 10, severity: "normal", hover_text: "Department Approval: 4h SLA, €200" },
    { step_name: "CFO Sign-off (tiered)", x: 3, y: 0, time_pct: 8, severity: "recommendation_affected", hover_text: "CFO Sign-off: only invoices > €10k" },
    { step_name: "Payment Processing", x: 4, y: 0, time_pct: 4, severity: "core_value", hover_text: "Payment Processing: 2h, €40" },
  ],
  edges: [
    { source: "Invoice Submission", target: "Initial Review" },
    { source: "Initial Review", target: "Department Approval" },
    { source: "Department Approval", target: "Finance Validation" },
    { source: "Finance Validation", target: "CFO Sign-off" },
    { source: "CFO Sign-off", target: "Payment Processing" },
  ],
};

// Constraint chips for ContextStrip (derived from Constraints type)
export const MOCK_CONSTRAINT_CHIPS = [
  "No layoffs",
  "Budget < €50k",
  "Timeline: 8 weeks",
];
