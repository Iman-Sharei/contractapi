"use client";

import { useEffect, useState } from "react";
import { Icon } from "./Icon";
import { buttonClass, cx } from "./primitives";

const KEY = "contractapi-theme";

function currentTheme(): "light" | "dark" {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Switches light/dark and remembers the choice in this browser only. */
export function ThemeToggle({ withLabel = false, className }: { withLabel?: boolean; className?: string }) {
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);
  useEffect(() => setTheme(currentTheme()), []);

  function toggle() {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* private mode: the choice lasts for this page only */
    }
    setTheme(next);
  }

  const label = theme === "dark" ? "Light mode" : "Dark mode";
  return (
    <button
      type="button"
      onClick={toggle}
      className={cx(buttonClass("ghost", "md", !withLabel), className)}
      aria-label={withLabel ? undefined : label}
      title={label}
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} />
      {withLabel && label}
    </button>
  );
}
