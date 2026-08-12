/** Client-side text inject into a live Telnyx AI WebRTC call. */

export type DemoAgentCall = {
  state?: string;
  id?: string;
  sendConversationMessage?: (message: string, attachments?: string[]) => Promise<unknown> | unknown;
  telnyxIDs?: {
    telnyxCallControlId?: string;
    telnyxSessionId?: string;
    telnyxLegId?: string;
  };
  options?: Record<string, unknown>;
  session?: {
    execute?: (msg: unknown) => Promise<unknown> | unknown;
    executeRaw?: (text: string) => void;
    connection?: { sendRawText?: (text: string) => void };
  };
};

export type DemoAgentSendResult = {
  ok: boolean;
  reason:
    | "sent"
    | "sent_raw"
    | "queued"
    | "empty"
    | "no_call"
    | "not_live"
    | "missing_method"
    | "rejected"
    | "threw";
  callControlId?: string | null;
  preview?: string;
  error?: string;
  via?: string;
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

function digString(obj: unknown, keys: string[]): string | null {
  if (!obj || typeof obj !== "object") return null;
  const rec = obj as Record<string, unknown>;
  for (const key of keys) {
    const v = rec[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return null;
}

/** Telnyx populates this on answer; dig through getters + options + nested params. */
export function readCallControlId(call: DemoAgentCall | null | undefined): string | null {
  if (!call) return null;
  try {
    const fromGetter = digString(call.telnyxIDs, ["telnyxCallControlId", "telnyx_call_control_id"]);
    if (fromGetter) return fromGetter;
  } catch {
    /* ignore */
  }
  const fromOpts = digString(call.options, [
    "telnyxCallControlId",
    "telnyx_call_control_id",
    "callControlId",
    "call_control_id",
  ]);
  if (fromOpts) return fromOpts;
  const nested = call.options && typeof call.options === "object" ? (call.options as Record<string, unknown>) : null;
  if (nested) {
    for (const v of Object.values(nested)) {
      const hit = digString(v, ["telnyxCallControlId", "telnyx_call_control_id", "call_control_id"]);
      if (hit) return hit;
    }
  }
  // Some SDK builds stash answer params under remoteStream / peer / _*
  const rec = call as unknown as Record<string, unknown>;
  for (const key of ["params", "answer", "dialogParams", "_options"] as const) {
    const bag = rec[key];
    const hit = digString(bag, ["telnyxCallControlId", "telnyx_call_control_id", "call_control_id"]);
    if (hit) return hit;
  }
  return null;
}

function recordProbe(probe: DemoAgentSendProbe) {
  if (typeof window === "undefined") return;
  window.__voxDemoAgentSend = probe;
  const log = window.__voxDemoAgentSendLog || [];
  log.push(probe);
  window.__voxDemoAgentSendLog = log.slice(-20);
}

function newItemId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `vox-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** Fire-and-forget user text over the Verto socket (same shape as SDK ConversationMessage). */
export function sendRawAiUserText(call: DemoAgentCall, text: string): boolean {
  const connection = call.session?.connection;
  const sendRaw = connection?.sendRawText || call.session?.executeRaw;
  if (typeof sendRaw !== "function") return false;
  const payload = {
    jsonrpc: "2.0",
    id: newItemId(),
    method: "ai_conversation",
    params: {
      type: "conversation.item.create",
      previous_item_id: null,
      item: {
        id: newItemId(),
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    },
  };
  sendRaw.call(connection || call.session, JSON.stringify(payload));
  return true;
}

/**
 * SDK sendConversationMessage → session.execute waits for a JSON-RPC reply.
 * Telnyx often never answers ai_conversation, so awaiting hangs and Next never
 * reaches Leo. Cap the wait; prefer raw fire-and-forget when available.
 */
async function sendViaSdk(call: DemoAgentCall, text: string, timeoutMs = 900): Promise<{ ok: boolean; error?: string }> {
  const send = call.sendConversationMessage;
  if (typeof send !== "function") return { ok: false, error: "missing_method" };
  try {
    let timedOut = false;
    await Promise.race([
      Promise.resolve(send.call(call, text)).then(() => undefined),
      sleep(timeoutMs).then(() => {
        timedOut = true;
      }),
    ]);
    if (timedOut) return { ok: true, error: "sdk_timeout_ok" };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

/** Flush queued user texts to Leo. Prefer raw socket; SDK with timeout as backup. */
export async function flushDemoAgentMessages(
  call: DemoAgentCall | null | undefined,
  queue: string[],
): Promise<DemoAgentSendResult> {
  if (!queue.length) {
    return { ok: false, reason: "empty" };
  }
  if (!call) {
    return { ok: false, reason: "no_call", preview: queue[0]?.slice(0, 80) };
  }
  const ccid = readCallControlId(call);
  if (!callLooksLive(call)) {
    return {
      ok: false,
      reason: "not_live",
      callControlId: ccid,
      preview: queue[0]?.slice(0, 80),
    };
  }

  let last: DemoAgentSendResult = { ok: false, reason: "empty" };
  const pending = queue.splice(0, queue.length);
  for (const text of pending) {
    const preview = text.slice(0, 120);
    let errMsg = "";
    let via = "";
    let sent = false;

    // Raw first — does not wait for a Telnyx JSON-RPC reply (SDK execute often hangs).
    try {
      if (sendRawAiUserText(call, text)) {
        sent = true;
        via = "raw_ai_conversation";
      }
    } catch (err) {
      errMsg = err instanceof Error ? err.message : String(err);
    }

    if (!sent) {
      const sdk = await sendViaSdk(call, text);
      if (sdk.ok) {
        sent = true;
        via = sdk.error === "sdk_timeout_ok" ? "sendConversationMessage_timeout" : "sendConversationMessage";
      } else if (sdk.error && sdk.error !== "missing_method") {
        errMsg = errMsg || sdk.error;
      }
    }

    if (sent) {
      last = {
        ok: true,
        reason: via.startsWith("raw") ? "sent_raw" : "sent",
        callControlId: ccid,
        preview,
        via,
      };
      recordProbe({ ...last, at: new Date().toISOString(), message: text });
    } else {
      last = {
        ok: false,
        reason: typeof call.sendConversationMessage === "function" ? "threw" : "missing_method",
        callControlId: ccid,
        preview,
        error: errMsg || undefined,
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
