import { publicApiFetch } from "@/lib/api";

export type AiDemoStartResponse = {
  session_id: string;
  soft_cap_minutes?: number;
  selected_services?: string[];
  real_dashboard?: boolean;
  dashboard_url?: string | null;
  telnyx?: {
    configured?: boolean;
    agent_id?: string;
    web_calls_enabled?: boolean;
    first_message?: string;
    custom_headers?: Record<string, string> | Array<{ name: string; value: string }>;
  };
};

export type AiDemoUiEvent = {
  id?: string;
  type?: string;
  service?: string;
  route?: string;
  action?: string;
  section?: string;
  target?: string;
  delay_ms?: number;
  summary?: string;
  recommendation?: string;
  data?: unknown;
};

export function normalizeTelnyxCustomHeaders(
  raw: Record<string, string> | Array<{ name: string; value: string }> | undefined,
): Array<{ name: string; value: string }> {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw.filter((h) => String(h?.name || "").trim() && String(h?.value || "").trim());
  }
  return Object.entries(raw)
    .map(([name, value]) => {
      const clean = String(value || "").trim();
      if (!clean) return null;
      const headerName = name.startsWith("X-") ? name : `X-${name}`;
      return { name: headerName, value: clean };
    })
    .filter((h): h is { name: string; value: string } => h != null);
}

export async function startDemoSession(sessionId: string, selectedServices?: string[]) {
  return publicApiFetch<AiDemoStartResponse>("/ai-demo/start-session", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      selected_services: selectedServices || [],
    }),
  });
}

export async function completeDemoSession(input: {
  session_id: string;
  summary?: string;
  transcript?: string;
  duration_seconds?: number;
}) {
  return publicApiFetch("/ai-demo/complete", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function pollDemoEvents(sessionId: string, afterId?: string | null) {
  const q = afterId ? `?after_id=${encodeURIComponent(afterId)}` : "";
  return publicApiFetch<{ events: AiDemoUiEvent[] }>(
    `/ai-demo/events/${encodeURIComponent(sessionId)}${q}`,
  );
}

export function readCachedDemoStart(sessionId: string): AiDemoStartResponse | null {
  try {
    const raw = sessionStorage.getItem(`voxbulk_ai_demo_${sessionId}`);
    if (!raw) return null;
    return JSON.parse(raw) as AiDemoStartResponse;
  } catch {
    return null;
  }
}

export function clearCachedDemoStart(sessionId: string) {
  try {
    sessionStorage.removeItem(`voxbulk_ai_demo_${sessionId}`);
  } catch {
    /* ignore */
  }
}

export async function loadTelnyxRtc() {
  const mod = await import("@telnyx/webrtc");
  return mod.TelnyxRTC;
}
