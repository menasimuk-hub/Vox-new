/** Client-side text inject into a live Telnyx AI WebRTC call. */

export type DemoAgentCall = {
  state?: string;
  sendConversationMessage?: (message: string, attachments?: string[]) => Promise<unknown> | unknown;
  telnyxIDs?: {
    telnyxCallControlId?: string;
    telnyxSessionId?: string;
    telnyxLegId?: string;
  };
};

export type DemoAgentSendResult = {
  ok: boolean;
  reason: "sent" | "queued" | "empty" | "no_call" | "not_live" | "missing_method" | "rejected" | "threw";
  callControlId?: string | null;
  preview?: string;
  error?: string;
};

export type DemoAgentSendProbe = DemoAgentSendResult & {
  at: string;
  message: string;
};

declare global {
  interface Window {
    __voxDemoAgentSend?: DemoAgentSendProbe;
    __voxDemoAgentSendLog?: DemoAgentSendProbe[];
  }
}

export function callLooksLive(call: DemoAgentCall | null | undefined): boolean {
  const state = String(call?.state || "").toLowerCase();
  return state === "active" || state === "answered" || state === "held";
}

export function readCallControlId(call: DemoAgentCall | null | undefined): string | null {
  const id = String(call?.telnyxIDs?.telnyxCallControlId || "").trim();
  return id || null;
}

function recordProbe(probe: DemoAgentSendProbe) {
  if (typeof window === "undefined") return;
  window.__voxDemoAgentSend = probe;
  const log = window.__voxDemoAgentSendLog || [];
  log.push(probe);
  window.__voxDemoAgentSendLog = log.slice(-20);
}

/** Flush queued user texts via call.sendConversationMessage. Returns last result. */
export async function flushDemoAgentMessages(
  call: DemoAgentCall | null | undefined,
  queue: string[],
): Promise<DemoAgentSendResult> {
  if (!queue.length) {
    return { ok: false, reason: "empty" };
  }
  if (!call) {
    const result: DemoAgentSendResult = { ok: false, reason: "no_call", preview: queue[0]?.slice(0, 80) };
    return result;
  }
  if (!callLooksLive(call)) {
    return {
      ok: false,
      reason: "not_live",
      callControlId: readCallControlId(call),
      preview: queue[0]?.slice(0, 80),
    };
  }
  const send = call.sendConversationMessage;
  if (typeof send !== "function") {
    return {
      ok: false,
      reason: "missing_method",
      callControlId: readCallControlId(call),
      preview: queue[0]?.slice(0, 80),
    };
  }

  let last: DemoAgentSendResult = { ok: false, reason: "empty" };
  const pending = queue.splice(0, queue.length);
  for (const text of pending) {
    const preview = text.slice(0, 120);
    try {
      await Promise.resolve(send.call(call, text));
      last = {
        ok: true,
        reason: "sent",
        callControlId: readCallControlId(call),
        preview,
      };
      recordProbe({ ...last, at: new Date().toISOString(), message: text });
    } catch (err) {
      last = {
        ok: false,
        reason: "threw",
        callControlId: readCallControlId(call),
        preview,
        error: err instanceof Error ? err.message : String(err),
      };
      recordProbe({ ...last, at: new Date().toISOString(), message: text });
      queue.unshift(text);
      break;
    }
  }
  return last;
}

export function enqueueDemoAgentMessage(queue: string[], msg: string, max = 6): string[] {
  const text = String(msg || "").trim();
  if (!text) return queue;
  queue.push(text);
  if (queue.length > max) {
    queue.splice(0, queue.length - max);
  }
  return queue;
}
