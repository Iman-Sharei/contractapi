"use client";

import { useCallback, useEffect, useState } from "react";
import { activateSpec, deactivateSpec, deleteSpec, listActiveApis, loadSpec } from "@/lib/api";
import { LIVE_CHANGED_EVENT } from "@/lib/events";

/** Is this API running? Plus the start/stop/delete actions for its page. */
export function useLiveStatus(name: string) {
  const [isLive, setIsLive] = useState(false);
  const [known, setKnown] = useState(false);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const active = await listActiveApis();
      setIsLive(active.apis.some((a) => a.name === name));
      setKnown(true);
    } catch {
      /* the badge is best-effort */
    }
    setTick((t) => t + 1);
  }, [name]);

  useEffect(() => {
    void refresh();
    const onChanged = () => void refresh();
    window.addEventListener(LIVE_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(LIVE_CHANGED_EVENT, onChanged);
  }, [refresh]);

  /** Starts the saved version (no unsaved edits). */
  const makeLive = useCallback(async () => {
    const loaded = await loadSpec(name);
    await activateSpec(loaded.spec, name);
    await refresh();
  }, [name, refresh]);

  /** Stops only this API; others keep running. */
  const stop = useCallback(async () => {
    await deactivateSpec(name);
    await refresh();
  }, [name, refresh]);

  const remove = useCallback(async () => {
    if (isLive) await deactivateSpec(name);
    await deleteSpec(name);
  }, [name, isLive]);

  return { isLive, known, tick, refresh, makeLive, stop, remove };
}
