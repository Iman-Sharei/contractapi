"use client";

import styles from "../studio.module.css";
import { emptyJwt, type EditorState } from "./useEditorState";

export function JwtSection({ s }: { s: EditorState }) {
  const { spec, patchApp } = s;
  return (
    <>
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

    </>
  );
}
