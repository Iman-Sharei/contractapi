"use client";

import { ApiSurfaceCard } from "../editor/ApiSurfaceCard";
import { ConnectionCard } from "../editor/ConnectionCard";
import type { EditorState } from "../editor/useEditorState";
import styles from "../pages.module.css";

export function SettingsTab({ s }: { s: EditorState }) {
  return (
    <div className={styles.settingsStack}>
      <ConnectionCard s={s} />
      <ApiSurfaceCard s={s} />
    </div>
  );
}
