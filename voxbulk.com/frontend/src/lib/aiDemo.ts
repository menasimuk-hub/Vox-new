import { apiFetch } from "@/lib/api";
import { loadTelnyxRtc } from "@/lib/talkToUs";

export { loadTelnyxRtc };

export type AiDemoVerifyResponse = {
  session_id: string;
  request_id: string;
  contact_name: string;
  company_name: string;
  email: string;
  language: string;
  has_memory: boolean;
  memory: Record<string, unknown>;
  services: string[];
  soft_cap_minutes: number;
};

export type AiDemoStartResponse = {
  session_id: string;
  call_id?: string | null;
  lead_code?: string | null;
  voice_provider?: string;
  soft_cap_minutes?: number;
  active_service_code?: string | null;
  telnyx?: {
    configured?: boolean;
    agent_id?: string;
    web_calls_enabled?: boolean;
    first_message?: string;
    custom_headers?: Record<string, string> | Array<{ name: string; value: string }>;
  };
};

/** Telnyx WebRTC expects [{name, value}] — plain objects break call media. */
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

export type AiDemoUiEvent = {
  id?: string;
  type?: string;
  service?: string;
  data?: unknown;
  url?: string;
  label?: string;
  summary?: string;
  cta?: string;
  at?: string;
};

export async function submitDemoRequest(input: {
  contact_name: string;
  email: string;
  company_name: string;
  whatsapp: string;
  website: string;
  preferred_language: string;
  message: string;
}) {
  return apiFetch<{ ok: boolean; id?: string; status?: string; skipped?: boolean }>(
    "/ai-demo/requests",
    {
      method: "POST",
      body: JSON.stringify({
        ...input,
        website_hp: "",
      }),
    },
  );
}

export async function verifyDemoToken(token: string) {
  return apiFetch<AiDemoVerifyResponse>(
    `/ai-demo/verify?token=${encodeURIComponent(token)}`,
  );
}

export async function startDemoSession(sessionId: string) {
  return apiFetch<AiDemoStartResponse>("/ai-demo/start-session", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function completeDemoSession(input: {
  session_id: string;
  summary?: string;
  transcript?: string;
  duration_seconds?: number;
}) {
  return apiFetch("/ai-demo/complete", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function pollDemoEvents(sessionId: string, afterId?: string | null) {
  const q = afterId ? `?after_id=${encodeURIComponent(afterId)}` : "";
  return apiFetch<{ events: AiDemoUiEvent[] }>(
    `/ai-demo/events/${encodeURIComponent(sessionId)}${q}`,
  );
}

export async function resendDemoLink(requestId: string, sig: string) {
  return apiFetch<{ ok: boolean }>(
    `/ai-demo/resend?request=${encodeURIComponent(requestId)}&sig=${encodeURIComponent(sig)}`,
    { method: "POST" },
  );
}

export const DEMO_SERVICES = [
  { code: "recruitment", label: "Recruitment" },
  { code: "surveys", label: "Surveys" },
  { code: "feedback", label: "Feedback" },
  { code: "expo", label: "Expo" },
  { code: "smart_card", label: "Smart Card" },
] as const;
