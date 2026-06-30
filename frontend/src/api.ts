import type {
  ChatMessageRequest,
  ChatMessageResponse,
  PipelineStatusResponse,
  PrivacyReportResponse,
  StartSessionResponse,
  StepDecisionRequest,
  StepDecisionResponse,
  UploadFileRequest,
} from './types';

const BASE = import.meta.env.VITE_API_URL ?? '';

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  startSession(): Promise<StartSessionResponse> {
    return req('POST', '/session/start');
  },

  runPipeline(sessionId: string, body: UploadFileRequest): Promise<PipelineStatusResponse> {
    return req('POST', `/pipeline/run?session_id=${encodeURIComponent(sessionId)}`, body);
  },

  sendChatMessage(body: ChatMessageRequest): Promise<ChatMessageResponse> {
    return req('POST', '/chat/message', body);
  },

  submitStepDecision(body: StepDecisionRequest): Promise<StepDecisionResponse> {
    return req('POST', '/plan/step-decision', body);
  },

  getPrivacyReport(sessionId: string): Promise<PrivacyReportResponse> {
    return req('GET', `/privacy/report/${encodeURIComponent(sessionId)}`);
  },

  endSession(sessionId: string): Promise<{ status: string; final_report: string }> {
    return req('DELETE', `/session/${encodeURIComponent(sessionId)}`);
  },
};

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(',')[1] ?? result);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function tryParsePlan(raw: string | null): import('./types').CoachPlan | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && 'plan_id' in parsed && Array.isArray(parsed.steps)) {
      return parsed as import('./types').CoachPlan;
    }
    // Attempt to find JSON inside a larger text blob
    const match = raw.match(/\{[\s\S]*"plan_id"[\s\S]*\}/);
    if (match) {
      const inner = JSON.parse(match[0]);
      if (inner && Array.isArray(inner.steps)) return inner as import('./types').CoachPlan;
    }
  } catch {
    // not JSON — coach returned plain text
  }
  return null;
}
