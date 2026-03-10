/**
 * Domain types mirroring the Python Pydantic models.
 * Keep in sync with src/processiq/models/ and api/schemas.py.
 */

export type Industry =
  | "financial_services"
  | "healthcare"
  | "manufacturing"
  | "retail"
  | "technology"
  | "government"
  | "education"
  | "other";

export type CompanySize = "startup" | "small" | "mid_market" | "enterprise";

export type RevenueRange =
  | "under_100k"
  | "100k_to_500k"
  | "500k_to_1m"
  | "1m_to_5m"
  | "5m_to_20m"
  | "20m_to_100m"
  | "over_100m"
  | "prefer_not_to_say";

export type RegulatoryEnvironment =
  | "minimal"
  | "moderate"
  | "strict"
  | "highly_regulated";

export interface BusinessProfile {
  industry?: Industry | null;
  custom_industry?: string;
  company_size?: CompanySize | null;
  annual_revenue?: RevenueRange;
  regulatory_environment?: RegulatoryEnvironment;
  typical_constraints?: string[];
  preferred_frameworks?: string[];
  previous_improvements?: string[];
  rejected_approaches?: string[];
  notes?: string;
}

export interface Constraints {
  budget_limit?: number | null;
  no_layoffs?: boolean;
  no_new_hires?: boolean;
  regulatory_requirements?: string[];
  timeline_weeks?: number | null;
  technology_restrictions?: string[];
  custom_constraints?: string[];
}

export interface ProcessStep {
  step_name: string;
  average_time_hours: number;
  resources_needed: number;
  error_rate_pct?: number;
  cost_per_instance?: number;
  estimated_fields?: string[];
  depends_on?: string[];
  group_id?: string | null;
  group_type?: "alternative" | "parallel" | null;
  step_type?: "normal" | "conditional" | "loop";
  notes?: string;
}

export interface ProcessData {
  name: string;
  description?: string;
  steps: ProcessStep[];
}

export interface Issue {
  title: string;
  description: string;
  affected_steps?: string[];
  severity: "high" | "medium" | "low";
  root_cause_hypothesis?: string;
  evidence?: string[];
}

export interface Recommendation {
  title: string;
  addresses_issue: string;
  description: string;
  expected_benefit: string;
  estimated_roi?: string;
  risks?: string[];
  feasibility: "easy" | "moderate" | "complex";
  affected_steps?: string[];
  prerequisites?: string[];
  plain_explanation?: string;
  concrete_next_steps?: string[];
}

export interface NotAProblem {
  step_name: string;
  why_not_a_problem: string;
  appears_problematic_because?: string;
}

export interface AnalysisInsight {
  process_summary: string;
  patterns?: string[];
  issues?: Issue[];
  recommendations?: Recommendation[];
  not_problems?: NotAProblem[];
  follow_up_questions?: string[];
  confidence_notes?: string;
  investigation_findings?: string[];
  reasoning?: string;
  context_sources?: string[];
}

// ---------------------------------------------------------------------------
// Graph / Visualization
// ---------------------------------------------------------------------------

export type Severity =
  | "high"
  | "medium"
  | "core_value"
  | "recommendation_affected"
  | "normal";

export interface GraphNode {
  step_name: string;
  x: number;
  y: number;
  time_pct: number;
  severity: Severity;
  hover_text: string;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphSchema {
  before_nodes: GraphNode[];
  after_nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// API request / response shapes (mirror api/schemas.py)
// ---------------------------------------------------------------------------

export interface UIMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AnalyzeRequest {
  process: ProcessData;
  constraints?: Constraints | null;
  profile?: BusinessProfile | null;
  thread_id?: string | null;
  user_id?: string | null;
  analysis_mode?: string | null;
  llm_provider?: "anthropic" | "openai" | "ollama" | null;
  feedback_history?: Record<string, Record<string, unknown>> | null;
  max_cycles_override?: number | null;
}

export interface AnalyzeResponse {
  message: string;
  analysis_insight?: AnalysisInsight | null;
  graph_schema?: GraphSchema | null;
  thread_id?: string | null;
  is_error: boolean;
  error_code?: string | null;
  reasoning_trace: string[];
  context_sources: string[];
}

export interface ExtractTextRequest {
  text: string;
  analysis_mode?: string | null;
  additional_context?: string;
  current_process_data?: ProcessData | null;
  ui_messages?: UIMessage[] | null;
  constraints?: Constraints | null;
  profile?: BusinessProfile | null;
  llm_provider?: "anthropic" | "openai" | "ollama" | null;
}

export interface ExtractResponse {
  message: string;
  process_data?: ProcessData | null;
  needs_input: boolean;
  suggested_questions: string[];
  improvement_suggestions?: string | null;
  is_error: boolean;
  error_code?: string | null;
}

export interface ContinueRequest {
  thread_id: string;
  user_message: string;
  analysis_mode?: string | null;
}

export interface ContinueResponse {
  message: string;
  process_data?: ProcessData | null;
  analysis_insight?: AnalysisInsight | null;
  thread_id?: string | null;
  needs_input: boolean;
  is_error: boolean;
  error_code?: string | null;
}

export interface ProfileResponse {
  profile: BusinessProfile | null;
}

export interface FeedbackRequest {
  accepted: string[];
  rejected: string[];
  reasons: string[];
}

export interface FeedbackResponse {
  status: string;
}

// ---------------------------------------------------------------------------
// Sessions (Library view) — mirrors api/schemas.py AnalysisSessionSummary
// ---------------------------------------------------------------------------

export interface AnalysisSessionSummary {
  session_id: string;
  process_name: string;
  process_description: string;
  industry: string;
  timestamp: string;
  step_names: string[];
  bottlenecks_found: string[];
  suggestions_offered: string[];
  suggestions_accepted: string[];
  suggestions_rejected: string[];
}

export interface SessionsResponse {
  sessions: AnalysisSessionSummary[];
}
