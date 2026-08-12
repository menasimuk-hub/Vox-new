import { describe, expect, it, vi } from "vitest";

import {
  callLooksLive,
  enqueueDemoAgentMessage,
  flushDemoAgentMessages,
  readCallControlId,
  type DemoAgentCall,
} from "./ai-demo-agent-send";
import { DEMO_TOUR_BEATS, demoTourAdvanceMessage } from "./ai-demo-tour";

describe("ai-demo-agent-send", () => {
  it("callLooksLive only accepts active-like states", () => {
    expect(callLooksLive({ state: "active" })).toBe(true);
    expect(callLooksLive({ state: "answered" })).toBe(true);
    expect(callLooksLive({ state: "new" })).toBe(false);
    expect(callLooksLive(null)).toBe(false);
  });

  it("readCallControlId reads telnyxIDs", () => {
    expect(readCallControlId({ telnyxIDs: { telnyxCallControlId: " v3:abc " } })).toBe("v3:abc");
    expect(readCallControlId({})).toBeNull();
  });

  it("Next click path calls sendConversationMessage with I clicked Next", async () => {
    const sent: string[] = [];
    const call: DemoAgentCall = {
      state: "active",
      telnyxIDs: { telnyxCallControlId: "v3:test-call" },
      sendConversationMessage: vi.fn(async (msg: string) => {
        sent.push(msg);
      }),
    };
    const queue: string[] = [];
    const nextBeat = DEMO_TOUR_BEATS[1];
    expect(nextBeat).toBeTruthy();
    const msg = demoTourAdvanceMessage(nextBeat!);
    enqueueDemoAgentMessage(queue, msg);
    const result = await flushDemoAgentMessages(call, queue);

    expect(result.ok).toBe(true);
    expect(result.reason).toBe("sent");
    expect(result.callControlId).toBe("v3:test-call");
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatch(/^I clicked Next\./);
    expect(call.sendConversationMessage).toHaveBeenCalledTimes(1);
    expect(queue).toHaveLength(0);
  });

  it("queues when call is not live yet", async () => {
    const call: DemoAgentCall = {
      state: "trying",
      sendConversationMessage: vi.fn(),
    };
    const queue = ["I clicked Next."];
    const result = await flushDemoAgentMessages(call, queue);
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("not_live");
    expect(queue).toEqual(["I clicked Next."]);
    expect(call.sendConversationMessage).not.toHaveBeenCalled();
  });

  it("reports missing_method when SDK method and raw socket absent", async () => {
    const queue = ["I clicked Next."];
    const result = await flushDemoAgentMessages({ state: "active" }, queue);
    expect(result.ok).toBe(false);
    expect(result.reason).toBe("missing_method");
    expect(queue).toEqual(["I clicked Next."]);
  });

  it("falls back to raw ai_conversation socket", async () => {
    const sent: string[] = [];
    const call: DemoAgentCall = {
      state: "active",
      session: {
        connection: {
          sendRawText: (raw: string) => {
            sent.push(raw);
          },
        },
      },
    };
    const queue = ["I clicked Next. Spotlight is Overview."];
    const result = await flushDemoAgentMessages(call, queue);
    expect(result.ok).toBe(true);
    expect(result.reason).toBe("sent_raw");
    expect(sent).toHaveLength(1);
    expect(sent[0]).toContain("ai_conversation");
    expect(sent[0]).toContain("I clicked Next");
  });

  it("prefers raw over hanging SDK sendConversationMessage", async () => {
    const sent: string[] = [];
    const call: DemoAgentCall = {
      state: "active",
      sendConversationMessage: vi.fn(
        () =>
          new Promise(() => {
            /* never resolves — mirrors Telnyx execute hang */
          }),
      ),
      session: {
        connection: {
          sendRawText: (raw: string) => {
            sent.push(raw);
          },
        },
      },
    };
    const queue = ["I clicked Next."];
    const result = await flushDemoAgentMessages(call, queue);
    expect(result.ok).toBe(true);
    expect(result.reason).toBe("sent_raw");
    expect(sent).toHaveLength(1);
    expect(call.sendConversationMessage).not.toHaveBeenCalled();
    expect(queue).toHaveLength(0);
  });
});
