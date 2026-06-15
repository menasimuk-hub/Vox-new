import { frontpageApiFetch } from "@/lib/api";
import { clientGeoPayload, detectGeoHint, type GeoHint } from "@/lib/geo";

export type TalkToUsStartResponse = {
  call_id: string;
  lead_code?: string;
  status?: string;
  voice_provider?: string;
  vapi?: {
    configured?: boolean;
    public_key?: string;
    assistant_id?: string;
    system_prompt?: string;
    first_message?: string;
    variable_values?: Record<string, string>;
  };
  telnyx?: {
    configured?: boolean;
    agent_id?: string;
    web_calls_enabled?: boolean;
    first_message?: string;
    custom_headers?: Record<string, string>;
  };
};

export async function startTalkToUsCall(input: {
  contact_name: string;
  company_name: string;
  email: string;
  phone: string;
  geo?: GeoHint;
}) {
  const geo = input.geo || (await detectGeoHint());
  return frontpageApiFetch<TalkToUsStartResponse>("/frontpage/talk-to-us/start-call", {
    method: "POST",
    body: JSON.stringify({
      contact_name: input.contact_name.trim(),
      company_name: input.company_name.trim() || "—",
      email: input.email.trim(),
      phone: input.phone.trim(),
      source: "frontpage_talk_to_us",
      ...clientGeoPayload(geo),
    }),
  });
}

export async function completeTalkToUsCall(
  callId: string,
  payload: {
    transcript_text?: string;
    agent_response_text?: string;
    duration_seconds?: number;
    provider_call_id?: string;
  },
) {
  return frontpageApiFetch(`/frontpage/talk-to-us/complete-call/${encodeURIComponent(callId)}/json`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchTalkToUsConfig() {
  return frontpageApiFetch<{
    voice_provider?: string;
    vapi?: { configured?: boolean };
    telnyx?: { configured?: boolean };
  }>("/frontpage/talk-to-us/config");
}

export async function loadVapi() {
  const mod = await import("@vapi-ai/web");
  return mod.default;
}

export async function loadTelnyxRtc() {
  const mod = await import("@telnyx/webrtc");
  return mod.TelnyxRTC;
}
