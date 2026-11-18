"use client";

import { getApiBase } from "@/lib/api";
import { tableKey } from "@/lib/tableKey";
import { pathError } from "@/lib/pathRules";
import type { ApiSpecDraft, DatabaseDriver } from "@/lib/types";
import { ALL_FILTER_OPS, ALL_METHODS } from "@/lib/types";
import styles from "./studio.module.css";
import { isWarehouseDriver, useEditorState } from "./editor/useEditorState";
import { SecurityTab } from "./editor/SecurityTab";
import { RelationsTab } from "./editor/RelationsTab";
import { PlayTab } from "./editor/PlayTab";

export function StudioShell(props: { initialName?: string; embedded?: boolean }) {
  const s = useEditorState(props);
  const { embedded, dbUrl, setDbUrl, dbDriver, schema, setSchema, tables, selectedTable, setSelectedTable, spec, activeEndpoint, setActiveEndpoint, specName, setSpecName, savedNames, message, error, validation, editorTab, setEditorTab, yamlText, pending, dirty, showDbUrl, setShowDbUrl, contractOpen, setContractOpen, sqlDraft, setSqlDraft, selected, endpoint, localYaml, setStatus, onCopy, patchApp, updateEndpoint, removeEndpoint, onIntrospect, onDriverChange, addEndpointFromTable, addSqlEndpoint, toggleField, toggleMethod, onValidate, onActivate, onSave, onLoad, refreshSaved, onDiscoverSql, onRefreshYaml } = s;
  return (
    <div
      className={styles.shell}
      style={embedded ? { maxWidth: "none", padding: 0 } : undefined}
      aria-busy={pending || undefined}
    >
      {!embedded && (
        <div className={styles.topActions} style={{ marginBottom: 12 }}>
          <span className={styles.pill}>{pending ? "Working…" : dirty ? "Unsaved" : "Editor"}</span>
          <a className={styles.linkBtn} href={`${getApiBase()}/data/docs`} target="_blank" rel="noreferrer">
            Live /data docs
          </a>
          <a
            className={styles.linkBtn}
            href={`${getApiBase()}/data/graphql`}
            target="_blank"
            rel="noreferrer"
            title="Requires pip install 'contractapi[graphql]'. Reads: table + SQL GETs. Mutations: table POST/PATCH/DELETE."
          >
            GraphQL
          </a>
        </div>
      )}

      <section className={styles.settingsCard}>
        <div className={styles.settingsHead}>
          <h2>Connection</h2>
          <div className={styles.settingsActions}>
            <button type="button" className={styles.primary} onClick={onIntrospect} disabled={pending}>
              {tables.length === 0 ? "Introspect schema" : "Re-introspect"}
            </button>
            <button type="button" className={styles.secondary} onClick={onSave} disabled={pending}>
              Save
            </button>
            <button type="button" className={styles.secondary} onClick={refreshSaved}>
              List
            </button>
          </div>
        </div>
        <div className={styles.fieldGrid}>
          <label>
            <span className={styles.fieldLabel}>Driver</span>
            <select
              value={dbDriver}
              onChange={(e) => onDriverChange(e.target.value as DatabaseDriver)}
            >
              <option value="postgres">Postgres</option>
              <option value="duckdb">DuckDB</option>
              <option value="snowflake">Snowflake</option>
              <option value="bigquery">BigQuery</option>
            </select>
          </label>
          <label className={styles.span2}>
            <span className={styles.fieldLabel}>
              {dbDriver === "postgres"
                ? "Postgres URL"
                : dbDriver === "duckdb"
                  ? "DuckDB URL"
                  : dbDriver === "snowflake"
                    ? "Snowflake URL"
                    : "BigQuery URL"}
            </span>
            <div className={styles.inputWithBtn}>
              <input
                type={showDbUrl ? "text" : "password"}
                value={dbUrl}
                onChange={(e) => setDbUrl(e.target.value)}
                spellCheck={false}
                autoComplete="off"
                placeholder={
                  dbDriver === "duckdb"
                    ? "duckdb:///:memory: or duckdb:///./file.duckdb"
                    : dbDriver === "snowflake"
                      ? "snowflake://user:pass@account/db/schema"
                      : dbDriver === "bigquery"
                        ? "bigquery://project/dataset"
                        : undefined
                }
              />
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={() => setShowDbUrl((v) => !v)}
                aria-pressed={showDbUrl}
              >
                {showDbUrl ? "Hide" : "Show"}
              </button>
            </div>
          </label>
          <label>
            <span className={styles.fieldLabel}>Schema</span>
            <input
              value={schema}
              onChange={(e) => setSchema(e.target.value)}
              disabled={dbDriver === "duckdb"}
            />
          </label>
          <label>
            <span className={styles.fieldLabel}>Spec name</span>
            <input value={specName} onChange={(e) => setSpecName(e.target.value)} />
          </label>
          <label>
            <span className={styles.fieldLabel}>Auth</span>
            <select
              value={spec.app.auth}
              onChange={(e) => patchApp({ auth: e.target.value as ApiSpecDraft["app"]["auth"] })}
            >
              <option value="api_key">API key</option>
              <option value="jwt">JWT + RBAC</option>
              <option value="none">None (dev)</option>
            </select>
          </label>
          <label>
            <span className={styles.fieldLabel}>API prefix</span>
            <input
              value={spec.app.api_prefix ?? ""}
              onChange={(e) => patchApp({ api_prefix: e.target.value })}
              placeholder="empty = no version"
              spellCheck={false}
            />
          </label>
        </div>
        {isWarehouseDriver(dbDriver) && (
          <p className={styles.hint}>
            {dbDriver === "duckdb" && (
              <>
                DuckDB is GA (<code>pip install &apos;contractapi[duckdb]&apos;</code>). Prefer SQL /
                aggregate endpoints. Table introspect stays Postgres-only.
              </>
            )}
            {dbDriver === "snowflake" && (
              <>
                Snowflake needs <code>pip install &apos;contractapi[snowflake]&apos;</code>. Define
                table/SQL endpoints with known fields.
              </>
            )}
            {dbDriver === "bigquery" && (
              <>
                BigQuery needs <code>pip install &apos;contractapi[bigquery]&apos;</code>. Define
                table/SQL endpoints with known fields.
              </>
            )}
          </p>
        )}
      </section>

      <section className={styles.settingsCard}>
        <div className={styles.settingsHead}>
          <h2>API surface</h2>
        </div>
        <div className={styles.fieldGrid}>
          <label className={styles.span2}>
            <span className={styles.fieldLabel}>Title</span>
            <input value={spec.app.title} onChange={(e) => patchApp({ title: e.target.value })} />
          </label>
          <label>
            <span className={styles.fieldLabel}>Version</span>
            <input value={spec.app.version} onChange={(e) => patchApp({ version: e.target.value })} />
          </label>
          <label className={styles.span3}>
            <span className={styles.fieldLabel}>Description</span>
            <input
              value={spec.app.description}
              onChange={(e) => patchApp({ description: e.target.value })}
            />
          </label>
        </div>

        <div className={styles.toggleRow}>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={spec.app.read_only}
              onChange={(e) => patchApp({ read_only: e.target.checked })}
            />
            <span>Read-only</span>
          </label>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={spec.app.cache?.enabled ?? true}
              onChange={(e) =>
                patchApp({
                  cache: {
                    enabled: e.target.checked,
                    ttl_seconds: spec.app.cache?.ttl_seconds ?? 30,
                  },
                })
              }
            />
            <span>Cache</span>
          </label>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={spec.app.rate_limit.enabled}
              onChange={(e) =>
                patchApp({
                  rate_limit: {
                    ...spec.app.rate_limit,
                    enabled: e.target.checked,
                  },
                })
              }
            />
            <span>Rate limit</span>
          </label>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={spec.app.idempotency?.enabled ?? true}
              onChange={(e) =>
                patchApp({
                  idempotency: {
                    enabled: e.target.checked,
                    required_for_writes: spec.app.idempotency?.required_for_writes ?? false,
                    ttl_seconds: spec.app.idempotency?.ttl_seconds ?? 86400,
                  },
                })
              }
            />
            <span>Idempotency</span>
          </label>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={spec.app.idempotency?.required_for_writes ?? false}
              onChange={(e) =>
                patchApp({
                  idempotency: {
                    enabled: spec.app.idempotency?.enabled ?? true,
                    required_for_writes: e.target.checked,
                    ttl_seconds: spec.app.idempotency?.ttl_seconds ?? 86400,
                  },
                })
              }
            />
            <span>Idempotency required</span>
          </label>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={spec.app.compression ?? true}
              onChange={(e) => patchApp({ compression: e.target.checked })}
            />
            <span>Gzip</span>
          </label>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={spec.app.audit_enabled ?? true}
              onChange={(e) => patchApp({ audit_enabled: e.target.checked })}
            />
            <span>Audit</span>
          </label>
        </div>

        <div className={styles.fieldGrid}>
          <label>
            <span className={styles.fieldLabel}>Cache TTL (s)</span>
            <input
              type="number"
              min={0}
              value={spec.app.cache?.ttl_seconds ?? 30}
              onChange={(e) =>
                patchApp({
                  cache: {
                    enabled: spec.app.cache?.enabled ?? true,
                    ttl_seconds: Number(e.target.value) || 0,
                  },
                })
              }
            />
          </label>
          <label>
            <span className={styles.fieldLabel}>Rate / min</span>
            <input
              type="number"
              min={1}
              value={spec.app.rate_limit.requests_per_minute}
              onChange={(e) =>
                patchApp({
                  rate_limit: {
                    ...spec.app.rate_limit,
                    requests_per_minute: Number(e.target.value) || 1,
                  },
                })
              }
            />
          </label>
          <label>
            <span className={styles.fieldLabel}>Idempotency TTL (s)</span>
            <input
              type="number"
              min={0}
              value={spec.app.idempotency?.ttl_seconds ?? 86400}
              onChange={(e) =>
                patchApp({
                  idempotency: {
                    enabled: spec.app.idempotency?.enabled ?? true,
                    required_for_writes: spec.app.idempotency?.required_for_writes ?? false,
                    ttl_seconds: Number(e.target.value) || 0,
                  },
                })
              }
            />
          </label>
        </div>
      </section>

      {savedNames.length > 0 && (
        <div className={styles.endpointTabs}>
          {savedNames.map((name) => (
            <button key={name} type="button" className={styles.tab} onClick={() => onLoad(name)}>
              load:{name}
            </button>
          ))}
        </div>
      )}

      {(message || error) && (
        <div
          className={error ? styles.bannerError : styles.bannerOk}
          role={error ? "alert" : "status"}
        >
          {error ?? message}
        </div>
      )}

      <div className={contractOpen ? styles.grid : styles.gridYamlCollapsed}>
        <aside className={styles.panel}>
          <div className={styles.panelHead}>
            <h2>Schema</h2>
            <span>{tables.length}</span>
          </div>
          <ul className={styles.tableList}>
            {tables.map((t) => (
              <li key={tableKey(t)}>
                <button
                  type="button"
                  className={selectedTable === tableKey(t) ? styles.tableActive : styles.tableBtn}
                  onClick={() => setSelectedTable(tableKey(t))}
                >
                  <span>
                    {t.name}
                    {t.kind === "view" ? " · view" : ""}
                  </span>
                  {t.sensitive_columns.length > 0 && (
                    <em title="Sensitive columns">{t.sensitive_columns.length}</em>
                  )}
                </button>
              </li>
            ))}
            {tables.length === 0 && <li className={styles.empty}>Introspect to load tables/views.</li>}
          </ul>
          <div className={styles.stackBtns}>
            {selected && (
              <button
                type="button"
                className={styles.secondary}
                onClick={() => addEndpointFromTable(selected)}
              >
                Add endpoint from {selected.kind === "view" ? "view" : "table"}
              </button>
            )}
            {tables.length === 0 && (
              <button type="button" className={styles.secondary} onClick={onIntrospect} disabled={pending}>
                Re-introspect database
              </button>
            )}
            <button type="button" className={styles.secondary} onClick={addSqlEndpoint}>
              Add SQL / metrics endpoint
            </button>
          </div>
        </aside>

        <section className={styles.panelWide}>
          <div className={styles.panelHead}>
            <h2>Endpoints</h2>
            <div className={styles.rowGap}>
              <button type="button" className={styles.secondary} onClick={onValidate} disabled={pending}>
                Validate
              </button>
              <button type="button" className={styles.primary} onClick={onActivate} disabled={pending}>
                Activate
              </button>
            </div>
          </div>

          <div className={styles.endpointTabs}>
            {spec.endpoints.map((ep) => (
              <button
                key={ep.name}
                type="button"
                className={activeEndpoint === ep.name ? styles.tabActive : styles.tab}
                onClick={() => {
                  setActiveEndpoint(ep.name);
                  const t =
                    tables.find((x) => x.schema === ep.schema && x.name === ep.table) ??
                    tables.find((x) => x.name === ep.table);
                  if (t) setSelectedTable(tableKey(t));
                }}
              >
                {ep.sql ? "Σ " : ""}
                {ep.path}
              </button>
            ))}
            {spec.endpoints.length === 0 && (
              <p className={styles.empty}>Add a table/view endpoint or a custom SQL endpoint.</p>
            )}
          </div>

          {!endpoint && spec.endpoints.length > 0 && (
            <div className={styles.emptyState}>
              <p>Select an endpoint tab above to edit its contract.</p>
              <button
                type="button"
                className={styles.primary}
                onClick={() => setActiveEndpoint(spec.endpoints[0]?.name ?? null)}
              >
                Open {spec.endpoints[0]?.path ?? "first endpoint"}
              </button>
            </div>
          )}

          {!endpoint && spec.endpoints.length === 0 && (
            <div className={styles.emptyState}>
              <p>
                No endpoints yet. Introspect the database on the left, pick a table, then add an
                endpoint — or use the New API wizard.
              </p>
              {tables.length === 0 && (
                <button type="button" className={styles.primary} onClick={onIntrospect} disabled={pending}>
                  Introspect schema
                </button>
              )}
            </div>
          )}

          {endpoint && (
            <>
              <div className={styles.endpointTabs}>
                {(
                  [
                    ["contract", "Contract"],
                    ["security", "Security"],
                    ["relations", "Relations"],
                    ["sql", "SQL"],
                    ["play", "Try it"],
                    ["yaml", "YAML"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className={editorTab === id ? styles.tabActive : styles.tab}
                    aria-pressed={editorTab === id}
                    onClick={() => setEditorTab(id)}
                  >
                    {label}
                  </button>
                ))}
                <button type="button" className={styles.dangerBtn} onClick={removeEndpoint}>
                  Remove
                </button>
              </div>

              {editorTab === "contract" && (
                <div className={styles.editorBlock}>
                  <div className={styles.metaGrid}>
                    <label>
                      Name (id)
                      <input
                        value={endpoint.name}
                        onChange={(e) => updateEndpoint({ name: e.target.value })}
                        spellCheck={false}
                      />
                    </label>
                    <label>
                      Path (URL)
                      <input
                        value={endpoint.path}
                        onChange={(e) => updateEndpoint({ path: e.target.value })}
                        spellCheck={false}
                        aria-invalid={Boolean(pathError(endpoint.path, spec.app.api_prefix ?? ""))}
                      />
                      {pathError(endpoint.path, spec.app.api_prefix ?? "") && (
                        <span className={styles.errLine} role="alert">
                          {pathError(endpoint.path, spec.app.api_prefix ?? "")}
                        </span>
                      )}
                    </label>
                    <label>
                      Primary key
                      <select
                        value={endpoint.primary_key}
                        onChange={(e) => updateEndpoint({ primary_key: e.target.value })}
                      >
                        {endpoint.fields.map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Pagination mode
                      <select
                        value={endpoint.pagination?.mode ?? "cursor"}
                        onChange={(e) =>
                          updateEndpoint({
                            pagination: {
                              enabled: endpoint.pagination?.enabled ?? true,
                              mode: e.target.value as "cursor" | "offset",
                              default_limit: endpoint.pagination?.default_limit ?? 20,
                              max_limit: endpoint.pagination?.max_limit ?? 100,
                            },
                          })
                        }
                      >
                        <option value="cursor">Cursor</option>
                        <option value="offset">Offset</option>
                      </select>
                    </label>
                    <label>
                      Default limit
                      <input
                        type="number"
                        min={1}
                        value={endpoint.pagination?.default_limit ?? 20}
                        onChange={(e) =>
                          updateEndpoint({
                            pagination: {
                              enabled: endpoint.pagination?.enabled ?? true,
                              mode: endpoint.pagination?.mode ?? "cursor",
                              default_limit: Number(e.target.value) || 1,
                              max_limit: endpoint.pagination?.max_limit ?? 100,
                            },
                          })
                        }
                      />
                    </label>
                    <label>
                      Max limit
                      <input
                        type="number"
                        min={1}
                        value={endpoint.pagination?.max_limit ?? 100}
                        onChange={(e) =>
                          updateEndpoint({
                            pagination: {
                              enabled: endpoint.pagination?.enabled ?? true,
                              mode: endpoint.pagination?.mode ?? "cursor",
                              default_limit: endpoint.pagination?.default_limit ?? 20,
                              max_limit: Number(e.target.value) || 1,
                            },
                          })
                        }
                      />
                    </label>
                    <label className={styles.span2}>
                      Description
                      <input
                        value={endpoint.description ?? ""}
                        onChange={(e) => updateEndpoint({ description: e.target.value })}
                      />
                    </label>
                  </div>
                  <label className={styles.check}>
                    <input
                      type="checkbox"
                      checked={endpoint.pagination?.enabled ?? true}
                      onChange={(e) =>
                        updateEndpoint({
                          pagination: {
                            enabled: e.target.checked,
                            mode: endpoint.pagination?.mode ?? "cursor",
                            default_limit: endpoint.pagination?.default_limit ?? 20,
                            max_limit: endpoint.pagination?.max_limit ?? 100,
                          },
                        })
                      }
                    />
                    Pagination enabled
                  </label>
                  <label className={styles.check}>
                    <input
                      type="checkbox"
                      checked={endpoint.allow_sensitive ?? false}
                      onChange={(e) => updateEndpoint({ allow_sensitive: e.target.checked })}
                    />
                    Allow sensitive columns
                  </label>

                  {!endpoint.sql && (
                    <>
                      <h3>Methods</h3>
                      <div className={styles.allowlist}>
                        {ALL_METHODS.map((m) => (
                          <button
                            key={m}
                            type="button"
                            className={[
                              styles.chip,
                              endpoint.methods.includes(m) ? styles.chipOn : "",
                            ].join(" ")}
                            onClick={() => toggleMethod(m)}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </>
                  )}

                  <h3>Fields</h3>
                  <div className={styles.allowlist}>
                    {(selected?.columns ?? endpoint.fields.map((name) => ({ name, sensitive: false, primary_key: name === endpoint.primary_key, type: "", nullable: true }))).map(
                      (col) => {
                        const name = typeof col === "string" ? col : col.name;
                        const on = endpoint.fields.includes(name);
                        const sensitive = typeof col === "object" && col.sensitive;
                        return (
                          <button
                            key={name}
                            type="button"
                            className={[
                              styles.chip,
                              on ? styles.chipOn : "",
                              sensitive ? styles.chipWarn : "",
                            ].join(" ")}
                            onClick={() => toggleField(name, "fields")}
                          >
                            {name}
                          </button>
                        );
                      },
                    )}
                  </div>

                  <div className={styles.twoCol}>
                    <div>
                      <h3>Filters</h3>
                      <div className={styles.allowlist}>
                        {endpoint.fields.map((f) => (
                          <button
                            key={f}
                            type="button"
                            className={[
                              styles.chip,
                              endpoint.filters.includes(f) ? styles.chipOn : "",
                            ].join(" ")}
                            onClick={() => toggleField(f, "filters")}
                          >
                            {f}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h3>Sortable</h3>
                      <div className={styles.allowlist}>
                        {endpoint.fields.map((f) => (
                          <button
                            key={f}
                            type="button"
                            className={[
                              styles.chip,
                              endpoint.sortable.includes(f) ? styles.chipOn : "",
                            ].join(" ")}
                            onClick={() => toggleField(f, "sortable")}
                          >
                            {f}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {!endpoint.sql && (
                    <div>
                      <h3>Writable fields</h3>
                      <div className={styles.allowlist}>
                        {endpoint.fields
                          .filter((f) => f !== endpoint.primary_key)
                          .map((f) => (
                            <button
                              key={f}
                              type="button"
                              className={[
                                styles.chip,
                                (endpoint.writable_fields ?? []).includes(f) ? styles.chipOn : "",
                              ].join(" ")}
                              onClick={() => toggleField(f, "writable_fields")}
                            >
                              {f}
                            </button>
                          ))}
                      </div>
                    </div>
                  )}

                  <h3>Filter operators</h3>
                  <div className={styles.allowlist}>
                    {ALL_FILTER_OPS.map((op) => {
                      const on = (endpoint.filter_operators ?? [...ALL_FILTER_OPS]).includes(op);
                      return (
                        <button
                          key={op}
                          type="button"
                          className={[styles.chip, on ? styles.chipOn : ""].join(" ")}
                          onClick={() => {
                            const cur = new Set(endpoint.filter_operators ?? [...ALL_FILTER_OPS]);
                            if (cur.has(op)) cur.delete(op);
                            else cur.add(op);
                            updateEndpoint({ filter_operators: [...cur] });
                          }}
                        >
                          {op}
                        </button>
                      );
                    })}
                  </div>

                  <div className={styles.rowGap}>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.bulk_enabled ?? true}
                        disabled={!!endpoint.sql}
                        onChange={(e) => updateEndpoint({ bulk_enabled: e.target.checked })}
                      />
                      Bulk POST
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.async_writes ?? false}
                        disabled={!!endpoint.sql}
                        onChange={(e) => updateEndpoint({ async_writes: e.target.checked })}
                      />
                      Async 202 writes
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.csv_export ?? true}
                        onChange={(e) => updateEndpoint({ csv_export: e.target.checked })}
                      />
                      CSV export
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.ndjson_export ?? false}
                        onChange={(e) => updateEndpoint({ ndjson_export: e.target.checked })}
                      />
                      NDJSON export
                    </label>
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={endpoint.parquet_export ?? false}
                        onChange={(e) => updateEndpoint({ parquet_export: e.target.checked })}
                      />
                      Parquet export (requires pyarrow)
                    </label>
                  </div>
                </div>
              )}

              {editorTab === "security" && <SecurityTab s={s} />}

              {editorTab === "relations" && <RelationsTab s={s} />}

              {editorTab === "sql" && (
                <div className={styles.editorBlock}>
                  <p className={styles.hint}>
                    Use raw SQL <em>or</em> Aggregation DSL (GROUP BY metrics). Writes and relations
                    are disabled for both.
                  </p>
                  <h3>Aggregation DSL</h3>
                  <p className={styles.hint}>
                    Prefer this for count/sum/avg without writing SQL. Clears raw SQL when applied.
                  </p>
                  <div className={styles.twoCol}>
                    <label>
                      Table
                      <input
                        value={endpoint.aggregate?.table ?? selected?.name ?? endpoint.table ?? ""}
                        onChange={(e) =>
                          updateEndpoint({
                            aggregate: {
                              table: e.target.value,
                              schema:
                                endpoint.aggregate?.schema ??
                                selected?.schema ??
                                endpoint.schema ??
                                "public",
                              group_by: endpoint.aggregate?.group_by ?? [],
                              metrics: endpoint.aggregate?.metrics ?? [
                                { name: "row_count", op: "count" },
                              ],
                            },
                            sql: null,
                          })
                        }
                        placeholder="orders"
                      />
                    </label>
                    <label>
                      Schema
                      <input
                        value={endpoint.aggregate?.schema ?? endpoint.schema ?? "public"}
                        onChange={(e) =>
                          updateEndpoint({
                            aggregate: {
                              table:
                                endpoint.aggregate?.table ??
                                selected?.name ??
                                endpoint.table ??
                                "table",
                              schema: e.target.value,
                              group_by: endpoint.aggregate?.group_by ?? [],
                              metrics: endpoint.aggregate?.metrics ?? [
                                { name: "row_count", op: "count" },
                              ],
                            },
                            sql: null,
                          })
                        }
                      />
                    </label>
                  </div>
                  <label>
                    Group by (comma-separated)
                    <input
                      value={(endpoint.aggregate?.group_by ?? []).join(", ")}
                      onChange={(e) => {
                        const group_by = e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean);
                        updateEndpoint({
                          aggregate: {
                            table:
                              endpoint.aggregate?.table ??
                              selected?.name ??
                              endpoint.table ??
                              "table",
                            schema:
                              endpoint.aggregate?.schema ??
                              selected?.schema ??
                              endpoint.schema ??
                              "public",
                            group_by,
                            metrics: endpoint.aggregate?.metrics ?? [
                              { name: "row_count", op: "count" },
                            ],
                          },
                          sql: null,
                          pagination: {
                            enabled: true,
                            mode: "offset",
                            default_limit: endpoint.pagination?.default_limit ?? 50,
                            max_limit: endpoint.pagination?.max_limit ?? 200,
                          },
                        });
                      }}
                      placeholder="status, customer_id"
                    />
                  </label>
                  <label>
                    Metrics YAML-ish (name:op[:field] per line)
                    <textarea
                      className={styles.sqlBox}
                      rows={3}
                      value={(endpoint.aggregate?.metrics ?? [])
                        .map((m) =>
                          m.field ? `${m.name}:${m.op}:${m.field}` : `${m.name}:${m.op}`,
                        )
                        .join("\n")}
                      onChange={(e) => {
                        const metrics = e.target.value
                          .split("\n")
                          .map((ln) => ln.trim())
                          .filter(Boolean)
                          .map((ln) => {
                            const [name, op, field] = ln.split(":").map((s) => s.trim());
                            return {
                              name: name || "metric",
                              op: (op || "count") as "count" | "sum" | "avg" | "min" | "max",
                              field: field || null,
                            };
                          });
                        updateEndpoint({
                          aggregate: {
                            table:
                              endpoint.aggregate?.table ??
                              selected?.name ??
                              endpoint.table ??
                              "table",
                            schema:
                              endpoint.aggregate?.schema ??
                              selected?.schema ??
                              endpoint.schema ??
                              "public",
                            group_by: endpoint.aggregate?.group_by ?? [],
                            metrics: metrics.length
                              ? metrics
                              : [{ name: "row_count", op: "count" }],
                          },
                          sql: null,
                        });
                      }}
                      placeholder={"order_count:count\nrevenue:sum:amount"}
                    />
                  </label>
                  <button
                    type="button"
                    className={styles.secondary}
                    onClick={() => {
                      updateEndpoint({ aggregate: null });
                      setStatus("Cleared aggregation DSL — use raw SQL below if needed.");
                    }}
                  >
                    Clear aggregation
                  </button>

                  <h3>Raw SQL</h3>
                  <textarea
                    className={styles.sqlBox}
                    value={endpoint.aggregate ? "" : endpoint.sql ?? sqlDraft}
                    disabled={!!endpoint.aggregate}
                    onChange={(e) => {
                      setSqlDraft(e.target.value);
                      updateEndpoint({ sql: e.target.value, aggregate: null });
                    }}
                    rows={10}
                    spellCheck={false}
                    placeholder={
                      endpoint.aggregate
                        ? "(disabled while Aggregation DSL is set)"
                        : "SELECT …"
                    }
                  />
                  <div className={styles.rowGap}>
                    <button
                      type="button"
                      className={styles.primary}
                      onClick={onDiscoverSql}
                      disabled={pending || !!endpoint.aggregate}
                    >
                      Discover columns
                    </button>
                    <button
                      type="button"
                      className={styles.secondary}
                      onClick={() => {
                        const table = selected?.name ?? endpoint.table;
                        if (!table || table === "_sql") {
                          setStatus(null, "Select a table before converting from SQL.");
                          return;
                        }
                        updateEndpoint({
                          sql: null,
                          aggregate: null,
                          table,
                          schema: selected?.schema ?? endpoint.schema,
                        });
                        setStatus(`Converted to table endpoint on ${table}.`);
                      }}
                    >
                      Convert to table endpoint
                    </button>
                  </div>
                  <h3>SQL params</h3>
                  <p className={styles.hint}>
                    Bind <code>:name</code> placeholders. Example:{" "}
                    <code>name=min_total,type=float,default=0</code>
                  </p>
                  <textarea
                    className={styles.sqlBox}
                    rows={3}
                    value={(endpoint.sql_params ?? [])
                      .map(
                        (p) =>
                          `${p.name},type=${p.type}${p.required ? ",required" : ""}${
                            p.default != null && p.default !== "" ? `,default=${p.default}` : ""
                          }`,
                      )
                      .join("\n")}
                    onChange={(e) => {
                      const params = e.target.value
                        .split("\n")
                        .map((line) => line.trim())
                        .filter(Boolean)
                        .map((line) => {
                          const parts = line.split(",").map((x) => x.trim());
                          const name = parts[0]?.replace(/^name=/, "") || "param";
                          const typePart = parts.find((p) => p.startsWith("type="))?.slice(5) || "string";
                          const defPart = parts.find((p) => p.startsWith("default="))?.slice(8);
                          const required = parts.includes("required");
                          const type = (["string", "int", "float", "bool"].includes(typePart)
                            ? typePart
                            : "string") as "string" | "int" | "float" | "bool";
                          let def: string | number | boolean | null = defPart ?? null;
                          if (defPart != null && type === "int") def = Number(defPart);
                          if (defPart != null && type === "float") def = Number(defPart);
                          if (defPart != null && type === "bool") def = ["1", "true", "yes"].includes(defPart.toLowerCase());
                          return { name, type, required, default: def };
                        });
                      updateEndpoint({ sql_params: params });
                    }}
                    spellCheck={false}
                  />
                  <label className={styles.check}>
                    <input
                      type="checkbox"
                      checked={endpoint.ndjson_export ?? true}
                      onChange={(e) => updateEndpoint({ ndjson_export: e.target.checked })}
                    />
                    NDJSON export
                  </label>
                </div>
              )}

              {editorTab === "play" && <PlayTab s={s} />}

              {editorTab === "yaml" && (
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
              )}
            </>
          )}

          {validation && (
            <div className={styles.validation}>
              <strong>{validation.valid ? "Valid" : "Invalid"}</strong>
              {validation.errors.map((e) => (
                <div key={e} className={styles.errLine}>
                  {e}
                </div>
              ))}
              {validation.warnings.map((w) => (
                <div key={w} className={styles.warnLine}>
                  {w}
                </div>
              ))}
            </div>
          )}
        </section>

        <aside className={contractOpen ? styles.panel : styles.panelCollapsed}>
          <div className={styles.panelHead}>
            <h2>Contract</h2>
            <div className={styles.rowGap}>
              <button
                type="button"
                className={styles.ghostBtn}
                aria-expanded={contractOpen}
                onClick={() => setContractOpen((v) => !v)}
              >
                {contractOpen ? "Hide YAML" : "Show YAML"}
              </button>
              {contractOpen && (
                <button
                  type="button"
                  className={styles.ghostBtn}
                  onClick={() => onCopy(yamlText || localYaml, "YAML")}
                >
                  Copy
                </button>
              )}
            </div>
          </div>
          {contractOpen && <pre className={styles.yaml}>{yamlText || localYaml}</pre>}
          {!contractOpen && (
            <p className={styles.empty}>YAML panel collapsed — expand to inspect the live contract.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
