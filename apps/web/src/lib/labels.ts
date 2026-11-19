/** Plain-language labels shared by the wizard and the editor (audience: non-experts). */
import type { ApiSpecDraft } from "./types";

type Auth = ApiSpecDraft["app"]["auth"];

export const AUTH_OPTIONS: { value: Auth; label: string; help: string }[] = [
  {
    value: "api_key",
    label: "API key (recommended)",
    help: "Callers send a secret key with every request. You create and revoke keys in Studio.",
  },
  {
    value: "jwt",
    label: "Login tokens (JWT)",
    help: "For apps that already sign users in. Lets you limit fields by role and rows per user.",
  },
  {
    value: "none",
    label: "Public — no key",
    help: "Anyone who knows the address can read the data. Only for public or demo data.",
  },
];

export function authHelp(auth: Auth): string {
  return AUTH_OPTIONS.find((o) => o.value === auth)?.help ?? "";
}

export const WRITE_METHODS = ["POST", "PATCH", "DELETE"] as const;

/** New APIs start at 1.0.0 (not the tool's own version). */
export const DEFAULT_API_VERSION = "1.0.0";
