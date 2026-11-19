"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./flow.module.css";

const SECTIONS = ["new", "diff", "ops", "tools"];

const links = [
  {
    href: "/studio",
    label: "My APIs",
    // An API page (/studio/<name>) belongs to "My APIs" — but not the other sections.
    match: (p: string) =>
      p === "/studio" || (/^\/studio\/[^/]+$/.test(p) && !SECTIONS.includes(p.split("/")[2])),
  },
  { href: "/studio/new", label: "New API", match: (p: string) => p.startsWith("/studio/new") },
  { href: "/studio/diff", label: "Compare", match: (p: string) => p.startsWith("/studio/diff") },
  { href: "/studio/ops", label: "Keys & settings", match: (p: string) => p.startsWith("/studio/ops") },
  { href: "/studio/tools", label: "Tools", match: (p: string) => p.startsWith("/studio/tools") },
];

export function StudioNav() {
  const pathname = usePathname();
  return (
    <header className={styles.nav}>
      <a href="#studio-main" className={styles.skip}>
        Skip to content
      </a>
      <Link href="/" className={styles.brand}>
        contractapi
      </Link>
      <nav className={styles.navLinks} aria-label="Studio">
        {links.map((l) => {
          const active = l.match(pathname);
          return (
            <Link
              key={l.href}
              href={l.href}
              className={active ? styles.navOn : styles.navOff}
              aria-current={active ? "page" : undefined}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
      <button
        type="button"
        className={styles.ghost}
        onClick={async () => {
          await fetch("/api/session", { method: "DELETE" });
          window.location.assign("/login");
        }}
      >
        Sign out
      </button>
    </header>
  );
}
