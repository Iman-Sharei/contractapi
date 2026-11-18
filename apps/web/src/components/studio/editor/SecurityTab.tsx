"use client";

import { getDataApiKey } from "@/lib/api";
import { SafetyChecklist } from "../SafetyChecklist";
import { VALIDATION_FORMATS, WEBHOOK_EVENTS } from "@/lib/types";
import styles from "../studio.module.css";
import { emptyJwt, type EditorState } from "./useEditorState";

export function SecurityTab({ s }: { s: EditorState }) {
  const { spec, endpoint, patchApp, updateEndpoint, patchWebhook, addWebhook, removeWebhook, addRbacRole, updateRbacRole, removeRbacRole, toggleRbacField, addValidation, updateValidation, removeValidation } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
    <div className={styles.editorBlock}>
      <SafetyChecklist spec={spec} />
      <h3>Endpoint access</h3>
      <label>
        Required roles (comma-separated)
        <input
          value={(endpoint.roles ?? []).join(", ")}
          onChange={(e) =>
            updateEndpoint({
              roles: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          placeholder="analyst, admin"
        />
      </label>
      <label>
        ETag field
        <select
          value={endpoint.etag_field ?? ""}
          onChange={(e) =>
            updateEndpoint({ etag_field: e.target.value || null })
          }
        >
          <option value="">(hash body)</option>
          {endpoint.fields.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <div className={styles.twoCol}>
        <label>
          Soft-delete column
          <input
            value={endpoint.soft_delete?.column ?? ""}
            disabled={!!endpoint.sql}
            onChange={(e) =>
              updateEndpoint({
                soft_delete: e.target.value
                  ? { column: e.target.value }
                  : null,
              })
            }
            placeholder="deleted_at"
          />
        </label>
        <label>
          Row-level column
          <input
            value={endpoint.row_level?.column ?? ""}
            disabled={!!endpoint.sql}
            onChange={(e) =>
              updateEndpoint({
                row_level: e.target.value
                  ? {
                      column: e.target.value,
                      claim: endpoint.row_level?.claim ?? "sub",
                      required: endpoint.row_level?.required ?? true,
                    }
                  : null,
              })
            }
            placeholder="owner_id"
          />
        </label>
      </div>
      {endpoint.row_level && (
        <div className={styles.twoCol}>
          <label>
            JWT claim for row-level
            <input
              value={endpoint.row_level.claim}
              onChange={(e) =>
                updateEndpoint({
                  row_level: { ...endpoint.row_level!, claim: e.target.value },
                })
              }
            />
          </label>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={endpoint.row_level.required}
              onChange={(e) =>
                updateEndpoint({
                  row_level: {
                    ...endpoint.row_level!,
                    required: e.target.checked,
                  },
                })
              }
            />
            Require claim
          </label>
        </div>
      )}

      <h3>Field validations</h3>
      <p className={styles.hint}>
        Extra checks on write payloads (format, length, range). Applied in addition to DB
        constraints.
      </p>
      {(endpoint.validations ?? []).map((v, idx) => (
        <div key={idx} className={styles.relCard}>
          <div className={styles.twoCol}>
            <label>
              Field
              <select
                value={v.field}
                onChange={(e) => updateValidation(idx, { field: e.target.value })}
              >
                {endpoint.fields.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Format
              <select
                value={v.format ?? ""}
                onChange={(e) =>
                  updateValidation(idx, { format: e.target.value || null })
                }
              >
                <option value="">(none)</option>
                {VALIDATION_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className={styles.twoCol}>
            <label>
              Min length
              <input
                type="number"
                value={v.min_length ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    min_length: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Max length
              <input
                type="number"
                value={v.max_length ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    max_length: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <div className={styles.twoCol}>
            <label>
              ≥ (ge)
              <input
                type="number"
                value={v.ge ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    ge: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              ≤ (le)
              <input
                type="number"
                value={v.le ?? ""}
                onChange={(e) =>
                  updateValidation(idx, {
                    le: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <label>
            Pattern (regex)
            <input
              value={v.pattern ?? ""}
              onChange={(e) =>
                updateValidation(idx, { pattern: e.target.value || null })
              }
              placeholder="^[A-Z].*"
            />
          </label>
          <button
            type="button"
            className={styles.dangerBtn}
            onClick={() => removeValidation(idx)}
          >
            Remove rule
          </button>
        </div>
      ))}
      <button type="button" className={styles.secondary} onClick={addValidation}>
        + Add validation
      </button>

      <div className={styles.twoCol}>
        <label>
          Deprecation sunset (YYYY-MM-DD)
          <input
            value={endpoint.deprecation?.sunset ?? ""}
            onChange={(e) =>
              updateEndpoint({
                deprecation: {
                  deprecated: Boolean(e.target.value),
                  sunset: e.target.value || null,
                  successor: endpoint.deprecation?.successor ?? null,
                },
              })
            }
          />
        </label>
        <label>
          Successor path
          <input
            value={endpoint.deprecation?.successor ?? ""}
            onChange={(e) =>
              updateEndpoint({
                deprecation: {
                  deprecated: true,
                  sunset: endpoint.deprecation?.sunset ?? null,
                  successor: e.target.value || null,
                },
              })
            }
          />
        </label>
      </div>
      <label>
        IP allowlist (comma-separated IPs / prefixes)
        <input
          value={(spec.app.ip_allowlist ?? []).join(", ")}
          onChange={(e) =>
            patchApp({
              ip_allowlist: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          placeholder="127.0.0.1, 10.0.0."
        />
      </label>

      <h3>JWT config</h3>
      <p className={styles.hint}>
        Used when app auth is <code>jwt</code>. Signing secret stays in env{" "}
        <code>JWT_SECRET</code> — never in YAML.
      </p>
      <div className={styles.twoCol}>
        <label>
          Issuer
          <input
            value={spec.app.jwt?.issuer ?? "contractapi"}
            onChange={(e) =>
              patchApp({
                jwt: { ...(spec.app.jwt ?? emptyJwt()), issuer: e.target.value },
              })
            }
          />
        </label>
        <label>
          Audience
          <input
            value={spec.app.jwt?.audience ?? "contractapi-clients"}
            onChange={(e) =>
              patchApp({
                jwt: { ...(spec.app.jwt ?? emptyJwt()), audience: e.target.value },
              })
            }
          />
        </label>
      </div>
      <div className={styles.twoCol}>
        <label>
          Algorithm
          <select
            value={spec.app.jwt?.algorithm ?? "HS256"}
            onChange={(e) =>
              patchApp({
                jwt: { ...(spec.app.jwt ?? emptyJwt()), algorithm: e.target.value },
              })
            }
          >
            <option value="HS256">HS256</option>
            <option value="HS384">HS384</option>
            <option value="HS512">HS512</option>
          </select>
        </label>
        <label>
          Access TTL (minutes)
          <input
            type="number"
            min={1}
            max={1440}
            value={spec.app.jwt?.access_ttl_minutes ?? 15}
            onChange={(e) =>
              patchApp({
                jwt: {
                  ...(spec.app.jwt ?? emptyJwt()),
                  access_ttl_minutes: Number(e.target.value) || 15,
                },
              })
            }
          />
        </label>
      </div>
      <label>
        Refresh TTL (days)
        <input
          type="number"
          min={1}
          max={90}
          value={spec.app.jwt?.refresh_ttl_days ?? 7}
          onChange={(e) =>
            patchApp({
              jwt: {
                ...(spec.app.jwt ?? emptyJwt()),
                refresh_ttl_days: Number(e.target.value) || 7,
              },
            })
          }
        />
      </label>

      <h3>Webhooks</h3>
      <p className={styles.hint}>
        POST JSON on writes. Signature header <code>X-Contractapi-Signature</code> when
        secret is set.
      </p>
      {(spec.app.webhooks ?? []).map((wh, idx) => (
        <div key={idx} className={styles.relCard}>
          <label>
            URL
            <input
              value={wh.url}
              onChange={(e) => patchWebhook(idx, { url: e.target.value })}
              placeholder="https://hooks.example.com/contractapi"
            />
          </label>
          <div className={styles.toggleRow}>
            {WEBHOOK_EVENTS.map((ev) => (
              <label key={ev} className={styles.check}>
                <input
                  type="checkbox"
                  checked={(wh.events ?? []).includes(ev)}
                  onChange={(e) => {
                    const set = new Set(wh.events ?? []);
                    if (e.target.checked) set.add(ev);
                    else set.delete(ev);
                    patchWebhook(idx, { events: [...set] });
                  }}
                />
                {ev}
              </label>
            ))}
          </div>
          <div className={styles.twoCol}>
            <label>
              HMAC secret
              <input
                value={wh.secret ?? ""}
                onChange={(e) => patchWebhook(idx, { secret: e.target.value })}
              />
            </label>
            <label>
              Timeout (s)
              <input
                type="number"
                min={0.5}
                max={30}
                step={0.5}
                value={wh.timeout_seconds ?? 3}
                onChange={(e) =>
                  patchWebhook(idx, {
                    timeout_seconds: Number(e.target.value) || 3,
                  })
                }
              />
            </label>
          </div>
          <button
            type="button"
            className={styles.dangerBtn}
            onClick={() => removeWebhook(idx)}
          >
            Remove webhook
          </button>
        </div>
      ))}
      <button type="button" className={styles.secondary} onClick={addWebhook}>
        + Add webhook
      </button>

      <h3>RBAC field matrix</h3>
      <p className={styles.hint}>
        Per-role allowlists of response fields. Empty matrix = no extra filtering. Data
        key for try-it: <code>{getDataApiKey()}</code>
      </p>
      {(spec.app.rbac ?? []).map((role, idx) => (
        <div key={idx} className={styles.relCard}>
          <div className={styles.settingsHead}>
            <label>
              Role
              <input
                value={role.role}
                onChange={(e) => updateRbacRole(idx, { role: e.target.value })}
              />
            </label>
            <button
              type="button"
              className={styles.dangerBtn}
              onClick={() => removeRbacRole(idx)}
            >
              Remove
            </button>
          </div>
          {spec.endpoints.map((ep) => (
            <div key={ep.name}>
              <strong>{ep.name}</strong>
              <div className={styles.toggleRow}>
                {ep.fields.map((f) => (
                  <label key={f} className={styles.check}>
                    <input
                      type="checkbox"
                      checked={(role.endpoints[ep.name] ?? []).includes(f)}
                      onChange={() => toggleRbacField(idx, ep.name, f)}
                    />
                    {f}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
      <button type="button" className={styles.secondary} onClick={addRbacRole}>
        + Add RBAC role
      </button>
    </div>
    </>
  );
}
