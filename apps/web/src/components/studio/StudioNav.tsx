"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { getApiBase } from "@/lib/api";
import styles from "./flow.module.css";

const links = [
  { href: "/studio", label: "My APIs", match: (p: string) => p === "/studio" || /^\/studio\/[^/]+$/.test(p) },
  { href: "/studio/new", label: "New", match: (p: string) => p.startsWith("/studio/new") },
  { href: "/studio/diff", label: "Diff", match: (p: string) => p.startsWith("/studio/diff") },
  { href: "/studio/ops", label: "Ops", match: (p: string) => p.startsWith("/studio/ops") },
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
      <a
        className={styles.docs}
        href={`${getApiBase()}/data/docs`}
        target="_blank"
        rel="noreferrer"
      >
        Live docs <span className={styles.srOnly}>(opens in new tab)</span>
      </a>
    </header>
  );
}
