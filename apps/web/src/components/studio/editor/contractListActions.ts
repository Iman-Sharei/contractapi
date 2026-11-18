"use client";

import type { FieldValidation, RbacRoleDraft, WebhookDraft } from "@/lib/types";
import { type EditorCore } from "./useEditorCore";

export function contractListActions(c: EditorCore) {
  const { spec, endpoint, patchApp, updateEndpoint } = c;

  function patchWebhook(index: number, patch: Partial<WebhookDraft>) {
    const hooks = [...(spec.app.webhooks ?? [])];
    if (!hooks[index]) return;
    hooks[index] = { ...hooks[index], ...patch };
    patchApp({ webhooks: hooks });
  }

  function addWebhook() {
    const hooks = [...(spec.app.webhooks ?? [])];
    hooks.push({
      url: "",
      events: ["create", "update", "delete"],
      secret: "",
      timeout_seconds: 3,
    });
    patchApp({ webhooks: hooks });
  }

  function removeWebhook(index: number) {
    patchApp({ webhooks: (spec.app.webhooks ?? []).filter((_, i) => i !== index) });
  }

  function addRbacRole() {
    const roles = [...(spec.app.rbac ?? [])];
    let role = "analyst";
    let i = 2;
    while (roles.some((r) => r.role === role)) role = `role_${i++}`;
    const endpoints: Record<string, string[]> = {};
    for (const ep of spec.endpoints) {
      endpoints[ep.name] = [...ep.fields];
    }
    roles.push({ role, endpoints });
    patchApp({ rbac: roles });
  }

  function updateRbacRole(index: number, patch: Partial<RbacRoleDraft>) {
    const roles = [...(spec.app.rbac ?? [])];
    if (!roles[index]) return;
    roles[index] = { ...roles[index], ...patch };
    patchApp({ rbac: roles });
  }

  function removeRbacRole(index: number) {
    patchApp({ rbac: (spec.app.rbac ?? []).filter((_, i) => i !== index) });
  }

  function toggleRbacField(roleIndex: number, epName: string, field: string) {
    const roles = [...(spec.app.rbac ?? [])];
    const role = roles[roleIndex];
    if (!role) return;
    const current = new Set(role.endpoints[epName] ?? []);
    if (current.has(field)) current.delete(field);
    else current.add(field);
    roles[roleIndex] = {
      ...role,
      endpoints: { ...role.endpoints, [epName]: [...current] },
    };
    patchApp({ rbac: roles });
  }

  function addValidation() {
    if (!endpoint) return;
    const field = endpoint.fields[0] ?? "id";
    const next: FieldValidation = { field, format: "email" };
    updateEndpoint({ validations: [...(endpoint.validations ?? []), next] });
  }

  function updateValidation(index: number, patch: Partial<FieldValidation>) {
    if (!endpoint) return;
    const list = [...(endpoint.validations ?? [])];
    if (!list[index]) return;
    list[index] = { ...list[index], ...patch };
    updateEndpoint({ validations: list });
  }

  function removeValidation(index: number) {
    if (!endpoint) return;
    updateEndpoint({
      validations: (endpoint.validations ?? []).filter((_, i) => i !== index),
    });
  }

  return { patchWebhook, addWebhook, removeWebhook, addRbacRole, updateRbacRole, removeRbacRole, toggleRbacField, addValidation, updateValidation, removeValidation };
}
