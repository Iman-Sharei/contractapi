import { safetyChecks } from "@/lib/safetyChecks";
import type { ApiSpecDraft } from "@/lib/types";

/** Plain-language warnings about a contract (wizard, editor and API page share it). */
export function SafetyChecklist({ spec, title = "Before you publish" }: { spec: ApiSpecDraft; title?: string }) {
  const findings = safetyChecks(spec);
  if (findings.length === 0) {
    return <p data-testid="safety-checks-ok">✅ No safety concerns found for this contract.</p>;
  }
  return (
    <div data-testid="safety-checks" role="note">
      <h3>{title}</h3>
      <ul>
        {findings.map((f) => (
          <li key={f.message}>
            {f.level === "warn" ? "⚠️ " : "ℹ️ "}
            {f.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
