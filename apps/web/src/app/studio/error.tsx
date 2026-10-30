"use client";

import Link from "next/link";
import styles from "@/components/studio/flow.module.css";

export default function StudioError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className={styles.panel} role="alert">
      <h1 className={styles.title}>Something went wrong</h1>
      <p>{error.message || "Unexpected Studio error."}</p>
      <div className={styles.toolbar}>
        <button type="button" className={styles.primary} onClick={reset}>
          Try again
        </button>
        <Link className={styles.secondary} href="/studio">
          Catalog
        </Link>
      </div>
    </section>
  );
}
