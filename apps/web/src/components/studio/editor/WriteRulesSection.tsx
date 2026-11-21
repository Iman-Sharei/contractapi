"use client";

import { useState } from "react";
import { Hint, Switch } from "@/components/ui/primitives";
import type { ColumnValues, TimestampsConfig } from "@/lib/types";
import { formatColumnValues, nestableRelations, parseColumnValues, toggleNested } from "@/lib/writeRules";
import styles from "./editor.module.css";
import { type EditorState } from "./useEditorState";

const WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE"];

function ValuesBox({
  label,
  help,
  value,
  onChange,
  testId,
}: {
  label: string;
  help: string;
  value: ColumnValues | undefined;
  onChange: (v: ColumnValues) => void;
  testId: string;
}) {
  const [text, setText] = useState(() => formatColumnValues(value));
  const [errors, setErrors] = useState<string[]>([]);
  return (
    <label>
      {label}
      <textarea
        rows={3}
        value={text}
        spellCheck={false}
        placeholder="status = pending"
        data-testid={testId}
        onChange={(e) => {
          setText(e.target.value);
          const parsed = parseColumnValues(e.target.value);
          setErrors(parsed.errors);
          if (!parsed.errors.length) onChange(parsed.values);
        }}
      />
      {errors.length ? (
        <Hint role="alert" className={styles.hintError}>
          {errors.join(" · ")}
        </Hint>
      ) : (
        <Hint>{help}</Hint>
      )}
    </label>
  );
}

/** Rules the API applies on every write: who sets which column, what is stored together. */
export function WriteRulesSection({ s }: { s: EditorState }) {
  const { endpoint, selected, updateEndpoint } = s;
  if (!endpoint || endpoint.sql || endpoint.aggregate) return null;
  const writes = endpoint.methods.some((m) => WRITE_METHODS.includes(m));
  // Timestamps go in ordinary columns: not the id, not private ones (password_hash, …).
  const columns = (selected?.columns.filter((c) => !c.sensitive).map((c) => c.name) ?? endpoint.fields).filter(
    (c) => c !== endpoint.primary_key,
  );
  const ts = endpoint.timestamps ?? {};
  const setTs = (patch: Partial<TimestampsConfig>) => {
    const next = { ...ts, ...patch };
    updateEndpoint({ timestamps: next.created_at || next.updated_at ? next : null });
  };
  const sd = endpoint.soft_delete;
  const nestable = nestableRelations(endpoint);
  const canDelete = endpoint.methods.includes("DELETE");

  return (
    <>
      <h3>Write rules</h3>
      {!writes && <Hint>Allow create, update or delete for this endpoint to use these rules.</Hint>}
      <fieldset disabled={!writes} className={styles.plainFieldset}>
        <div className={styles.twoCol}>
          {(["created_at", "updated_at"] as const).map((key) => (
            <label key={key}>
              {key === "created_at" ? "Set the creation time in" : "Set the last-change time in"}
              <select
                value={ts[key] ?? ""}
                data-testid={`rules-${key}`}
                onChange={(e) => setTs({ [key]: e.target.value || null })}
              >
                <option value="">(not set by the API)</option>
                {columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <Hint>
                {key === "created_at"
                  ? "Filled once, when a row is created."
                  : "Filled on every create and update, so edit conflicts (ETag) work even if the database does not update it."}
              </Hint>
            </label>
          ))}
        </div>
        <div className={styles.twoCol}>
          <ValuesBox
            key={`d-${endpoint.name}`}
            label="Default values (used when a caller leaves the field out)"
            help="One per line: column = value. Callers may still send their own value."
            value={endpoint.defaults}
            onChange={(defaults) => updateEndpoint({ defaults })}
            testId="rules-defaults"
          />
          <ValuesBox
            key={`f-${endpoint.name}`}
            label="Fixed values (always written by the API)"
            help="One per line: column = value. Callers cannot send or change these columns."
            value={endpoint.fixed_values}
            onChange={(fixed_values) => updateEndpoint({ fixed_values })}
            testId="rules-fixed"
          />
        </div>

        {(endpoint.bulk_enabled ?? true) && (
          <Switch
            label="Bulk create: all or nothing"
            description="If one row of a bulk create fails, none are saved. Off: valid rows are saved and the rest are reported."
            checked={endpoint.bulk_atomic ?? false}
            onChange={(e) => updateEndpoint({ bulk_atomic: e.target.checked })}
            data-testid="rules-bulk-atomic"
          />
        )}

        {nestable.length > 0 && (
          <>
            <h4>Create related rows together</h4>
            {nestable.map((rel) => (
              <Switch
                key={rel.name}
                label={`Accept "${rel.name}" in a create`}
                description={`A create may include a list of ${rel.name}; the row and its ${rel.name} are saved together, or not at all.`}
                checked={(endpoint.nested_writes ?? []).includes(rel.name)}
                disabled={!endpoint.methods.includes("POST") || !!endpoint.async_writes}
                onChange={(e) => updateEndpoint({ nested_writes: toggleNested(endpoint, rel.name, e.target.checked) })}
                data-testid={`rules-nested-${rel.name}`}
              />
            ))}
            {endpoint.async_writes && <Hint>Turn off async writes to create related rows together.</Hint>}
          </>
        )}

        {sd && (
          <>
            <h4>Deleted rows</h4>
            <Switch
              label="Allow restoring deleted rows"
              description={`Adds POST ${endpoint.path}/{id}/restore. Same permission as delete.`}
              checked={sd.restore ?? false}
              disabled={!canDelete}
              onChange={(e) => updateEndpoint({ soft_delete: { ...sd, restore: e.target.checked } })}
              data-testid="rules-restore"
            />
            <Switch
              label="Reuse values of deleted rows"
              description="A create with the same unique value as a deleted row (e.g. its email) brings that row back with the new values, instead of failing. It is the same record: its id and history (e.g. its orders) come back too. Only the caller's own rows."
              checked={sd.reuse_deleted ?? false}
              onChange={(e) => updateEndpoint({ soft_delete: { ...sd, reuse_deleted: e.target.checked } })}
              data-testid="rules-reuse-deleted"
            />
            {!canDelete && <Hint>Allow DELETE to offer restore.</Hint>}
          </>
        )}
      </fieldset>
    </>
  );
}
