/** Runs one action: success → toast, failure → banner. Shared by every settings section. */
export type RunAction = (action: () => Promise<unknown>, ok: string) => void;
