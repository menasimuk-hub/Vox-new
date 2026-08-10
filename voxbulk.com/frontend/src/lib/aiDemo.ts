import { frontpageApiFetch } from "@/lib/api";
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
    custom_headers?: Record<string, string>;
  };
};

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
  return frontpageApiFetch<{ ok: boolean; id?: string; status?: string; skipped?: boolean }>(
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
  return frontpageApiFetch<AiDemoVerifyResponse>(
    `/ai-demo/verify?token=${encodeURIComponent(token)}`,
  );
}

export async function startDemoSession(sessionId: string) {
  return frontpageApiFetch<AiDemoStartResponse>("/ai-demo/start-session", {
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
  return frontpageApiFetch("/ai-demo/complete", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function pollDemoEvents(sessionId: string, afterId?: string | null) {
  const q = afterId ? `?after_id=${encodeURIComponent(afterId)}` : "";
  return frontpageApiFetch<{ events: AiDemoUiEvent[] }>(
    `/ai-demo/events/${encodeURIComponent(sessionId)}${q}`,
  );
}

export async function resendDemoLink(requestId: string, sig: string) {
  return frontpageApiFetch<{ ok: boolean }>(
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
