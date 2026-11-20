"use client";

import { activateSpec, dumpYaml, getApiBase, issueToken, previewSql, saveSpec, tryDataRequest, validateSpec } from "@/lib/api";
import { LIVE_CHANGED_EVENT } from "@/lib/events";
import { type EditorCore } from "./useEditorCore";

export function ioActions(c: EditorCore) {
  const { dbUrl, dbDriver, spec, specName, setValidation, setEditorTab, setYamlText, startTransition, setDirty, playMethod, setPlayMethod, playPath, setPlayPath, playQuery, playBody, playBearer, setPlayBearer, playRoles, playExpiresMin, playClaims, setPlayResult, sqlDraft, endpoint, draftSpec, localYaml, setStatus, updateEndpoint } = c;

  function onValidate() {
    setStatus(null);
    startTransition(async () => {
      try {
        const result = await validateSpec(draftSpec, true);
        setValidation(result);
        setStatus(result.valid ? "Specification is valid." : "Specification has errors.");
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Validate failed");
      }
    });
  }

  function onActivate() {
    setStatus(null);
    if (draftSpec.endpoints.length === 0) {
      setStatus(null, "Add at least one endpoint before activating.");
      return;
    }
    startTransition(async () => {
      try {
        // Save first, so what is live is always the saved version (no hidden drafts).
        await saveSpec(specName, draftSpec);
        setDirty(false);
        await activateSpec(draftSpec, specName);
        setStatus(`Saved and live at ${getApiBase()}/apis/${specName}`);
        window.dispatchEvent(new Event(LIVE_CHANGED_EVENT));
        if (endpoint) {
          const prefix = draftSpec.app.api_prefix || "";
          setPlayPath(`${prefix}${endpoint.path}`);
          setPlayMethod("GET");
          setEditorTab("play");
        }
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Activate failed");
      }
    });
  }

  function onSave() {
    setStatus(null);
    startTransition(async () => {
      try {
        await saveSpec(specName, draftSpec);
        setDirty(false);
        window.dispatchEvent(new Event(LIVE_CHANGED_EVENT));
        setStatus(`Saved spec '${specName}'.`);
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "Save failed");
      }
    });
  }

  function onDiscoverSql() {
    if (!endpoint) return;
    const sql = endpoint.sql || sqlDraft;
    startTransition(async () => {
      try {
        const result = await previewSql(dbUrl, sql, dbDriver);
        const fields = result.columns;
        const pk = fields.includes("id") ? "id" : fields[0];
        updateEndpoint({
          sql,
          fields,
          primary_key: pk,
          sortable: [pk],
          filters: fields.filter((f) => f !== pk).slice(0, 5),
        });
        setStatus(`Discovered ${fields.length} columns from SQL.`);
      } catch (e) {
        setStatus(null, e instanceof Error ? e.message : "SQL preview failed");
      }
    });
  }

  function onRefreshYaml() {
    startTransition(async () => {
      try {
        const text = await dumpYaml(draftSpec);
        setYamlText(text);
        setStatus("YAML refreshed from server dump.");
      } catch {
        setYamlText(localYaml);
        setStatus(
          "Server YAML dump failed; local fallback YAML is incomplete.",
        );
      }
    });
  }

  function onTry() {
    if (["POST", "PATCH", "PUT"].includes(playMethod)) {
      try {
        JSON.parse(playBody);
      } catch {
        setPlayResult("Request body is not valid JSON. Fix the body before sending.");
        return;
      }
    }
    startTransition(async () => {
      try {
        let bearer = playBearer;
        let claims: Record<string, string | number | boolean> = {};
        if (playClaims.trim()) {
          try {
            const parsed: unknown = JSON.parse(playClaims);
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
            claims = parsed as Record<string, string | number | boolean>;
          } catch {
            setPlayResult('Claims must be a JSON object, e.g. {"tenant_id": "acme"}.');
            return;
          }
        }
        if (spec.app.auth === "jwt" && !bearer) {
          const roles = playRoles
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
          const tok = await issueToken(
            roles.length ? roles : ["analyst"],
            "studio-user",
            Number.isFinite(playExpiresMin) ? playExpiresMin : 15,
            claims,
            specName,
          );
          bearer = tok.access_token;
          setPlayBearer(bearer);
        }
        const result = await tryDataRequest({
          method: playMethod,
          path: playPath,
          query: playQuery,
          body: playBody,
          authMode: spec.app.auth,
          bearer,
          api: specName,
        });
        const headerLines = Object.entries(result.headers)
          .filter(([k]) =>
            ["etag", "link", "x-ratelimit-limit", "x-ratelimit-remaining", "x-trace-id", "content-type"].includes(
              k.toLowerCase(),
            ),
          )
          .map(([k, v]) => `${k}: ${v}`)
          .join("\n");
        setPlayResult(
          `HTTP ${result.status} (${result.ms}ms)\n${headerLines}\n\n${result.body.slice(0, 8000)}`,
        );
      } catch (e) {
        setPlayResult(e instanceof Error ? e.message : "Request failed");
      }
    });
  }

  return { onValidate, onActivate, onSave, onDiscoverSql, onRefreshYaml, onTry };
}
