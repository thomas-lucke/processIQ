/**
 * Typed API client for the ProcessIQ FastAPI backend.
 * All fetch calls live here — never call fetch directly from components.
 */

import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ContinueRequest,
  ContinueResponse,
  ExtractResponse,
  ExtractTextRequest,
  GraphSchema,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(
  path: string,
  options: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
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
    body: JSON.stringify(request),
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
