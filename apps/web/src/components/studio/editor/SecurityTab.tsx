"use client";

import { SafetyChecklist } from "../SafetyChecklist";
import styles from "./editor.module.css";
import { type EditorState } from "./useEditorState";
import { AccessSection } from "./AccessSection";
import { JwtSection } from "./JwtSection";
import { PolicySection } from "./PolicySection";
import { RbacSection } from "./RbacSection";
import { ValidationsSection } from "./ValidationsSection";
import { WebhooksSection } from "./WebhooksSection";

export function SecurityTab({ s }: { s: EditorState }) {
  const { spec, endpoint } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
    <div className={styles.editorBlock}>
      <SafetyChecklist spec={spec} />
      <AccessSection s={s} />
      <ValidationsSection s={s} />

      <PolicySection s={s} />
      <JwtSection s={s} />
      <WebhooksSection s={s} />
      <RbacSection s={s} />
    </div>
    </>
  );
}
