"use client";

import styles from "../studio.module.css";
import { type EditorState } from "./useEditorState";

export function YamlTab({ s }: { s: EditorState }) {
  const { yamlText, localYaml, onCopy, onRefreshYaml } = s;
  return (
    <>
    <div className={styles.editorBlock}>
      <div className={styles.rowGap}>
        <button type="button" className={styles.secondary} onClick={onRefreshYaml}>
          Refresh canonical YAML
        </button>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => onCopy(yamlText || localYaml, "YAML")}
        >
          Copy YAML
        </button>
      </div>
      <pre className={styles.yaml}>{yamlText || localYaml}</pre>
    </div>
    </>
  );
}
