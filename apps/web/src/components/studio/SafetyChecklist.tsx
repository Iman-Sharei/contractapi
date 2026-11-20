import { Icon } from "@/components/ui/Icon";
import { safetyChecks } from "@/lib/safetyChecks";
import type { ApiSpecDraft } from "@/lib/types";
import styles from "./pages.module.css";

/** Plain-language warnings about a contract (wizard, editor and API page share it). */
export function SafetyChecklist({ spec, title = "Before you publish" }: { spec: ApiSpecDraft; title?: string }) {
  const findings = safetyChecks(spec);
  if (findings.length === 0) {
    return (
      <p className={styles.safeOk} data-testid="safety-checks-ok">
        <Icon name="shield" size={16} /> No safety concerns found for this contract.
      </p>
    );
  }
  return (
    <div className={styles.safety} data-testid="safety-checks" role="note">
      <h3>{title}</h3>
      <ul>
        {findings.map((f) => (
          <li key={f.message} className={f.level === "warn" ? styles.safeWarn : styles.safeInfo}>
            <Icon name={f.level === "warn" ? "alert" : "info"} size={15} />
            <span>{f.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
