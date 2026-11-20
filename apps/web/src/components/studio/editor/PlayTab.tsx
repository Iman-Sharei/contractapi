"use client";

import { ALL_METHODS } from "@/lib/types";
import { CodeBlock } from "@/components/ui/CodeBlock";
import styles from "./editor.module.css";
import { type EditorState } from "./useEditorState";

export function PlayTab({ s }: { s: EditorState }) {
  const { spec, pending, playMethod, setPlayMethod, playPath, setPlayPath, playQuery, setPlayQuery, playBody, setPlayBody, playBearer, setPlayBearer, playRoles, setPlayRoles, playExpiresMin, setPlayExpiresMin, playClaims, setPlayClaims, playResult, endpoint, draftSpec, snippets, onTry } = s;
  if (!endpoint) return null; // rendered only for a selected endpoint
  return (
    <>
    <div className={styles.editorBlock}>
      <div className={styles.metaGrid}>
        <label>
          Method
          <select value={playMethod} onChange={(e) => setPlayMethod(e.target.value)}>
            {ALL_METHODS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.span2}>
          Path (inside this API)
          <input value={playPath} onChange={(e) => setPlayPath(e.target.value)} />
        </label>
        <label className={styles.span2}>
          Query string
          <input
            value={playQuery}
            onChange={(e) => setPlayQuery(e.target.value)}
            placeholder="limit=5&fields=id,name"
          />
        </label>
        {(playMethod === "POST" || playMethod === "PATCH" || playMethod === "PUT") && (
          <label className={styles.span2}>
            JSON body
            <textarea
              className={styles.sqlBox}
              rows={4}
              value={playBody}
              onChange={(e) => setPlayBody(e.target.value)}
            />
          </label>
        )}
        {spec.app.auth === "jwt" && (
          <>
            <label className={styles.span2}>
              Bearer token
              <input value={playBearer} onChange={(e) => setPlayBearer(e.target.value)} />
            </label>
            <label>
              JWT roles
              <input
                value={playRoles}
                onChange={(e) => {
                  setPlayRoles(e.target.value);
                  setPlayBearer(""); // new roles → mint a new test token
                }}
                placeholder="analyst, admin"
              />
            </label>
            <label className={styles.span2}>
              Claims (JSON, for row-level testing)
              <input
                value={playClaims}
                onChange={(e) => {
                  setPlayClaims(e.target.value);
                  setPlayBearer(""); // new claims → mint a new test token
                }}
                placeholder='{"tenant_id": "acme"}'
                spellCheck={false}
                data-testid="play-claims"
              />
            </label>
            <label>
              Token expires (min)
              <input
                type="number"
                min={1}
                value={playExpiresMin}
                onChange={(e) => setPlayExpiresMin(Number(e.target.value) || 15)}
              />
            </label>
          </>
        )}
      </div>
      <div className={styles.rowGap}>
        <button type="button" className={styles.primary} onClick={onTry} disabled={pending}>
          Send
        </button>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            const prefix = draftSpec.app.api_prefix || "";
            setPlayPath(`${prefix}${endpoint.path}`);
            setPlayMethod("GET");
            setPlayQuery("limit=5");
          }}
        >
          Fill from endpoint
        </button>
      </div>
      <pre className={styles.playOut}>{playResult || "Response appears here after Send."}</pre>
      <h3>Same request as code</h3>
      <CodeBlock code={snippets.curl} title="curl" />
      <CodeBlock code={snippets.python} title="Python + pandas" />
    </div>
    </>
  );
}
