import type {
  EventStats,
  PluginInfo,
  RecentEvent,
  WebhookAcceptedResponse,
} from './types';

/**
 * Base URL of the FastAPI backend. Defaults to the standard local `uvicorn`
 * address from the README; override with a `.env.local` (`VITE_API_BASE_URL=...`)
 * when the backend runs somewhere else (e.g. the `api` service in Docker Compose).
 */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000';

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, apiKey: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'X-API-Key': apiKey,
      ...(init?.headers ?? {}),
    },
  });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new ApiError(resp.status, `${resp.status} ${detail}`);
  }

  return (await resp.json()) as T;
}

export function fetchRecentEvents(apiKey: string, limit = 50): Promise<RecentEvent[]> {
  return request<RecentEvent[]>(`/events/recent?limit=${limit}`, apiKey);
}

export function fetchEventStats(apiKey: string): Promise<EventStats> {
  return request<EventStats>('/events/stats', apiKey);
}

export function fetchPlugins(apiKey: string): Promise<PluginInfo[]> {
  return request<PluginInfo[]>('/plugins', apiKey);
}

export interface TestEventInput {
  camera_id: string;
  event_type: string;
  confidence: number;
  zone: string;
}

export function submitTestEvent(
  apiKey: string,
  input: TestEventInput,
): Promise<WebhookAcceptedResponse> {
  const payload = {
    camera_id: input.camera_id,
    event_type: input.event_type,
    confidence: input.confidence,
    bounding_box: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 },
    timestamp: new Date().toISOString(),
    metadata: { zone: input.zone, source: 'admin-dashboard-test-form' },
  };

  return request<WebhookAcceptedResponse>('/webhooks/events?adapter=generic_json', apiKey, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export { ApiError };
