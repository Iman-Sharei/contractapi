"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";
import { FeedbackProvider } from "@/components/ui/feedback";
import { buttonClass, cx } from "@/components/ui/primitives";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import styles from "./frame.module.css";

const SECTIONS = ["new", "diff", "ops", "tools"];

const LINKS: { href: string; label: string; icon: IconName; match: (p: string) => boolean }[] = [
  {
    href: "/studio",
    label: "My APIs",
    icon: "grid",
    // An API page (/studio/<name>) belongs to "My APIs" — the other sections don't.
    match: (p) => p === "/studio" || (/^\/studio\/[^/]+$/.test(p) && !SECTIONS.includes(p.split("/")[2])),
  },
  { href: "/studio/new", label: "New API", icon: "plus", match: (p) => p.startsWith("/studio/new") },
  { href: "/studio/diff", label: "Compare versions", icon: "compare", match: (p) => p.startsWith("/studio/diff") },
  { href: "/studio/ops", label: "Keys & settings", icon: "key", match: (p) => p.startsWith("/studio/ops") },
  { href: "/studio/tools", label: "Tools", icon: "tools", match: (p) => p.startsWith("/studio/tools") },
];

export function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className={styles.brand}>
      <span className={styles.logo} aria-hidden>
        <Icon name="layers" size={16} />
      </span>
      contractapi
    </Link>
  );
}

/** Studio app frame: sidebar on wide screens, top bar + slide-in menu on phones. */
export function StudioFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function signOut() {
    await fetch("/api/session", { method: "DELETE" });
    window.location.assign("/login");
  }

  return (
    <FeedbackProvider>
      <a href="#studio-main" className={styles.skip}>
        Skip to content
      </a>
      <div className={styles.frame}>
        <header className={styles.topbar}>
          <Brand href="/studio" />
          <button
            type="button"
            className={buttonClass("ghost", "md", true)}
            aria-label="Open menu"
            aria-expanded={open}
            aria-controls="studio-sidebar"
            onClick={() => setOpen(true)}
          >
            <Icon name="menu" size={20} />
          </button>
        </header>

        {open && <div className={styles.scrim} onClick={() => setOpen(false)} aria-hidden />}

        <aside id="studio-sidebar" className={cx(styles.sidebar, open && styles.sidebarOpen)}>
          <div className={styles.sidebarHead}>
            <Brand href="/studio" />
            <button
              type="button"
              className={cx(buttonClass("ghost", "sm", true), styles.closeBtn)}
              aria-label="Close menu"
              onClick={() => setOpen(false)}
            >
              <Icon name="x" />
            </button>
          </div>
          <nav aria-label="Studio" className={styles.nav}>
            {LINKS.map((l) => {
              const active = l.match(pathname);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  className={cx(styles.navItem, active && styles.navActive)}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon name={l.icon} size={17} />
                  {l.label}
                </Link>
              );
            })}
          </nav>
          <div className={styles.sidebarFoot}>
            <div className={styles.footRow}>
              <ThemeToggle withLabel className={styles.footBtn} />
              <button type="button" className={cx(buttonClass("ghost"), styles.footBtn)} onClick={signOut}>
                <Icon name="logout" />
                Sign out
              </button>
            </div>
          </div>
        </aside>

        <main id="studio-main" className={styles.main}>
          <div className={styles.content}>{children}</div>
        </main>
      </div>
    </FeedbackProvider>
  );
}
