import type { APIRequestContext } from "@playwright/test";

/**
 * Remove everything an e2e test created in the signed-in Studio: stop the live API, delete its
 * saved design and revoke keys named after it. Best-effort, so a failed test still cleans up.
 */
export async function removeApi(request: APIRequestContext, name: string) {
  const q = encodeURIComponent(name);
  await request.post(`/api/studio/deactivate?name=${q}`, { data: {} }).catch(() => undefined);
  await request.delete(`/api/studio/specs/${q}`).catch(() => undefined);
  const listed = await request.get("/api/studio/keys").catch(() => null);
  if (!listed?.ok()) return;
  const { keys } = (await listed.json()) as { keys: { id: string; name: string; revoked: boolean }[] };
  for (const k of keys) {
    if (!k.revoked && k.name.startsWith(name)) {
      await request.delete(`/api/studio/keys/${encodeURIComponent(k.id)}`).catch(() => undefined);
    }
  }
}
