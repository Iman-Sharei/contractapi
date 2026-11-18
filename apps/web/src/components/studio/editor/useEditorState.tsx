"use client";

/** Editor state + actions for Studio's contract editor (shared by StudioShell and tabs). */
import { endpointActions } from "./endpointActions";
import { relationActions } from "./relationActions";
import { contractListActions } from "./contractListActions";
import { ioActions } from "./ioActions";
import { useEditorCore } from "./useEditorCore";

// Module-level helpers stay importable from here.
export { emptyJwt, PG_DEFAULT_URL, DUCKDB_DEFAULT_URL, SNOWFLAKE_DEFAULT_URL, BIGQUERY_DEFAULT_URL, isWarehouseDriver, emptySpec, slugify, type EditorTab } from "./useEditorCore";

export function useEditorState({
  initialName,
  embedded = false,
}: {
  initialName?: string;
  embedded?: boolean;
}) {
  const core = useEditorCore({ initialName, embedded });
  return {
    ...core,
    ...endpointActions(core),
    ...relationActions(core),
    ...contractListActions(core),
    ...ioActions(core),
  };
}

export type EditorState = ReturnType<typeof useEditorState>;
