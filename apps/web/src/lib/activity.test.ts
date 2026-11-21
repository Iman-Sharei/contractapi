import { describe, expect, it } from "vitest";
import { eventTime, eventWhat, eventWhere, eventWho } from "./activity";

describe("activity rows", () => {
  it("reads ISO and epoch times, never shows a blank for a real time", () => {
    expect(eventTime({ ts: "2026-11-21T19:10:14+00:00" })).not.toBe("—");
    expect(eventTime({ ts: 1795287000 })).not.toBe("—");
    expect(eventTime({})).toBe("—");
  });
  it("says what happened, who did it and where", () => {
    const studio = { action: "studio.spec.promote", sub: "ada@corp.com", meta: { name: "shop", target: "shop_production" } };
    expect([eventWhat(studio), eventWho(studio), eventWhere(studio)]).toEqual([
      "Copied an API to another environment", "ada@corp.com", "shop → shop_production",
    ]);
    const write = { action: "delete", sub: "key:7ec94f813389", api: "shop", endpoint: "customers", resource_id: 6 };
    expect([eventWhat(write), eventWho(write), eventWhere(write)]).toEqual(["Deleted a row", "API key …7ec94f", "shop / customers #6"]);
    expect(eventWho({ sub: "studio-key" })).toBe("Studio key");
    expect(eventWhat({ action: "something.new" })).toBe("something.new");
  });
});
