"use client";

import { useState, type HTMLAttributes } from "react";
import { copyText } from "@/lib/copy";
import { Icon } from "./Icon";
import { ui } from "./primitives";

/** Dark code panel with optional language tabs and a copy button. */
export function CodeBlock<T extends string>({
  code,
  title,
  tabs,
  tab,
  onTab,
  ...pre
}: {
  code: string;
  title?: string;
  tabs?: readonly { id: T; label: string }[];
  tab?: T;
  onTab?: (id: T) => void;
} & HTMLAttributes<HTMLPreElement>) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    if (await copyText(code)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  }
  return (
    <div className={ui.codeBlock}>
      <div className={ui.codeHead}>
        {tabs && onTab ? (
          <div className={ui.codeTabs} role="tablist" aria-label="Language">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={t.id === tab}
                className={ui.codeTab}
                onClick={() => onTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        ) : (
          <span>{title}</span>
        )}
        <button type="button" className={ui.codeCopy} onClick={copy}>
          <Icon name={copied ? "check" : "copy"} size={13} />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre {...pre}>
        <code>{code}</code>
      </pre>
    </div>
  );
}
