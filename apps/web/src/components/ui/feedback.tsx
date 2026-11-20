"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Icon } from "./Icon";
import { Button, cx, ui } from "./primitives";

type ConfirmOptions = {
  title: string;
  body?: ReactNode;
  confirmLabel?: string;
  /** "danger" for stop/delete/replace; "primary" otherwise. */
  tone?: "danger" | "primary";
};

type Toast = { id: number; message: ReactNode; tone: "success" | "danger" };

type Feedback = {
  confirm: (o: ConfirmOptions) => Promise<boolean>;
  toast: (message: ReactNode, tone?: Toast["tone"]) => void;
};

const Ctx = createContext<Feedback | null>(null);

function useFeedback(): Feedback {
  const v = useContext(Ctx);
  if (!v) throw new Error("FeedbackProvider is missing");
  return v;
}

/** `await confirm({...})` → true when the user pressed the confirm button. */
export const useConfirm = () => useFeedback().confirm;
export const useToast = () => useFeedback().toast;

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const resolver = useRef<((ok: boolean) => void) | null>(null);
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const confirm = useCallback((o: ConfirmOptions) => {
    resolver.current?.(false);
    setOpts(o);
    // Open after React rendered the new text.
    requestAnimationFrame(() => dialog.current?.showModal());
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const close = (ok: boolean) => {
    dialog.current?.close();
    resolver.current?.(ok);
    resolver.current = null;
  };

  const toast = useCallback((message: ReactNode, tone: Toast["tone"] = "success") => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-2), { id, message, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  const danger = opts?.tone !== "primary";
  return (
    <Ctx.Provider value={{ confirm, toast }}>
      {children}
      <dialog
        ref={dialog}
        className={ui.dialog}
        aria-labelledby="confirm-title"
        onCancel={(e) => {
          e.preventDefault();
          close(false);
        }}
        onClick={(e) => {
          if (e.target === dialog.current) close(false); // backdrop click
        }}
        data-testid="confirm-dialog"
      >
        {opts && (
          <>
            <div className={ui.dialogBody}>
              <span
                className={cx(ui.dialogIcon, danger ? ui["tone-danger"] : ui["tone-accent"])}
                aria-hidden
              >
                <Icon name={danger ? "alert" : "info"} size={20} />
              </span>
              <div>
                <h2 id="confirm-title">{opts.title}</h2>
                {opts.body && <p>{opts.body}</p>}
              </div>
            </div>
            <div className={ui.dialogActions}>
              <Button variant="secondary" onClick={() => close(false)} autoFocus>
                Cancel
              </Button>
              <Button
                variant={danger ? "danger" : "primary"}
                onClick={() => close(true)}
                data-testid="confirm-ok"
              >
                {opts.confirmLabel ?? "Confirm"}
              </Button>
            </div>
          </>
        )}
      </dialog>
      <div className={ui.toasts} aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={cx(ui.toast, ui[`tone-${t.tone}`])} role={t.tone === "danger" ? "alert" : undefined}>
            <Icon name={t.tone === "danger" ? "alert" : "checkCircle"} size={17} />
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
