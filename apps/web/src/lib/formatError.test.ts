import { describe, expect, it } from "vitest";
import { formatApiError } from "./formatError";

describe("formatApiError", () => {
  it("uses string detail", () => {
    expect(formatApiError({ detail: "nope" }, 400, "Bad")).toBe("nope");
  });

  it("flattens validation array detail", () => {
    const msg = formatApiError(
      {
        detail: [
          { loc: ["body", "name"], msg: "field required" },
          { loc: ["body", "path"], msg: "invalid" },
        ],
      },
      422,
      "Unprocessable",
    );
    expect(msg).toContain("body.name: field required");
    expect(msg).toContain("body.path: invalid");
  });

  it("uses problem+json title", () => {
    expect(
      formatApiError({ title: "Unauthorized", detail: "missing key" }, 401, "Unauthorized"),
    ).toBe("Unauthorized: missing key");
  });
});
