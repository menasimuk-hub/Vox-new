import { describe, expect, it } from "vitest";
import {
  classifySyncOutcome,
  shouldApplyListResult,
  syncOutcomeToastMessage,
} from "./sync-ui";

describe("shouldApplyListResult", () => {
  it("accepts only the current generation", () => {
    expect(shouldApplyListResult(3, 3)).toBe(true);
    expect(shouldApplyListResult(2, 3)).toBe(false);
    expect(shouldApplyListResult(4, 3)).toBe(false);
  });
});

describe("classifySyncOutcome", () => {
  it("marks clean sync as success", () => {
    expect(classifySyncOutcome({ ok: true, syncedAccounts: 2, fetched: 5, errors: [] })).toBe(
      "success",
    );
  });

  it("marks mixed account results as partial", () => {
    expect(
      classifySyncOutcome({
        ok: false,
        partial: true,
        syncedAccounts: 1,
        fetched: 2,
        errors: ["a@x: boom"],
      }),
    ).toBe("partial");
    expect(
      classifySyncOutcome({
        ok: false,
        syncedAccounts: 1,
        fetched: 0,
        errors: ["a@x: boom"],
      }),
    ).toBe("partial");
  });

  it("marks total failure as error", () => {
    expect(
      classifySyncOutcome({
        ok: false,
        syncedAccounts: 0,
        fetched: 0,
        errors: ["a@x: boom"],
      }),
    ).toBe("error");
  });
});

describe("syncOutcomeToastMessage", () => {
  it("prefers server message then sensible defaults", () => {
    expect(syncOutcomeToastMessage({ message: "Synced 1/1" }, "success")).toBe("Synced 1/1");
    expect(syncOutcomeToastMessage({}, "success")).toBe("All accounts synced.");
    expect(syncOutcomeToastMessage({}, "partial")).toBe("Sync finished with some account errors.");
    expect(syncOutcomeToastMessage({ errors: ["imap down"] }, "error")).toBe("imap down");
  });
});
