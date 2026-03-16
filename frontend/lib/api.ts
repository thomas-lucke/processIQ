/**
 * Typed API client for the ProcessIQ FastAPI backend.
 * All fetch calls live here — never call fetch directly from components.
 */

import type {
  AnalysisInsight,
  AnalyzeRequest,
  AnalyzeResponse,
  BusinessProfile,
  ContinueRequest,
  ContinueResponse,
  ExtractResponse,
  ExtractTextRequest,
  FeedbackRequest,
  FeedbackResponse,
  GraphSchema,
  ProcessData,
  ProfileResponse,
  SessionsResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const USER_ID_KEY = "processiq_user_id";

/**
 * Get or create a persistent user ID stored in localStorage.
 * This provides cross-session identity without authentication.
 */
export function getUserId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem(USER_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(USER_ID_KEY, id);
  }
  return id;
}

async function apiFetch<T>(
  path: string,
  options: RequestInit
): Promise<T> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(userId ? { "X-User-Id": userId } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json() as Promise<T>;
}

export async function analyzeProcess(
  request: AnalyzeRequest
): Promise<AnalyzeResponse> {
  return apiFetch<AnalyzeResponse>("/analyze", {
    method: "POST",
    body: JSON.stringify({ ...request, user_id: getUserId() || request.user_id }),
  });
}

export async function extractText(
  request: ExtractTextRequest
): Promise<ExtractResponse> {
  return apiFetch<ExtractResponse>("/extract", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function extractFile(
  file: File,
  analysisMode?: string | null,
  llmProvider?: string | null
): Promise<ExtractResponse> {
  const form = new FormData();
  form.append("file", file);
  if (analysisMode) form.append("analysis_mode", analysisMode);
  if (llmProvider) form.append("llm_provider", llmProvider);

  const res = await fetch(`${API_BASE}/extract-file`, {
    method: "POST",
    body: form,
    // No Content-Type header — browser sets multipart/form-data boundary automatically
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json() as Promise<ExtractResponse>;
}

export async function continueConversation(
  request: ContinueRequest
): Promise<ContinueResponse> {
  return apiFetch<ContinueResponse>("/continue", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function getGraphSchema(threadId: string): Promise<GraphSchema> {
  return apiFetch<GraphSchema>(`/graph-schema/${threadId}`, {
    method: "GET",
  });
}

export async function healthCheck(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/health", { method: "GET" });
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export async function getProfile(): Promise<ProfileResponse> {
  const userId = getUserId();
  return apiFetch<ProfileResponse>(`/profile/${userId}`, {
    method: "GET",
  });
}

export async function saveProfile(
  profile: BusinessProfile
): Promise<ProfileResponse> {
  const userId = getUserId();
  return apiFetch<ProfileResponse>(`/profile/${userId}`, {
    method: "PUT",
    body: JSON.stringify(profile),
  });
}

/**
 * Delete all stored data for the current user (profile + analysis history),
 * then clear the localStorage UUID so the next request starts fresh.
 */
export async function deleteUserData(): Promise<void> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/profile/${userId}`, {
    method: "DELETE",
    headers: { "X-User-Id": userId },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  localStorage.removeItem(USER_ID_KEY);
}

// ---------------------------------------------------------------------------
// Feedback
// ---------------------------------------------------------------------------

export async function submitFeedback(
  sessionId: string,
  feedback: FeedbackRequest
): Promise<FeedbackResponse> {
  return apiFetch<FeedbackResponse>(`/feedback/${sessionId}`, {
    method: "POST",
    body: JSON.stringify({ ...feedback, user_id: getUserId() }),
  });
}

// ---------------------------------------------------------------------------
// Sessions (Library)
// ---------------------------------------------------------------------------

export async function getUserSessions(): Promise<SessionsResponse> {
  const userId = getUserId();
  return apiFetch<SessionsResponse>(`/sessions/${userId}`, { method: "GET" });
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

/**
 * Request a PDF export from the backend and return the blob.
 * The PDF is rendered server-side by WeasyPrint (vector, selectable text).
 */
export async function exportPdf(
  insight: AnalysisInsight,
  processData: ProcessData | null | undefined
): Promise<Blob> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/export/pdf`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(userId ? { "X-User-Id": userId } : {}),
    },
    body: JSON.stringify({ insight, process_data: processData ?? null }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.blob();
}

/**
 * Request a CSV export for a session from the backend.
 * Requires an active session (thread_id) with a completed analysis.
 */
export async function exportCsv(threadId: string): Promise<Blob> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/export/csv/${threadId}`, {
    method: "GET",
    headers: userId ? { "X-User-Id": userId } : {},
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.blob();
}
