import Link from "next/link";
import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.page}>
      <header className={styles.nav}>
        <div className={styles.brand}>contractapi</div>
        <Link className={styles.navLink} href="/studio">
          Open Studio
        </Link>
      </header>

      <section className={styles.hero}>
        <p className={styles.kicker}>For data people, no code needed</p>
        <h1 className={styles.title}>Turn your database into a secure API</h1>
        <p className={styles.lede}>
          Connect a database, tick the tables and columns to share, and publish. You get a standard
          REST API with keys, documentation and ready-to-run code — read-only and private columns
          hidden by default.
        </p>
        <div className={styles.ctaRow}>
          <Link className={styles.cta} href="/studio/new">
            Create an API
          </Link>
          <Link className={styles.ghost} href="/studio">
            My APIs
          </Link>
        </div>
      </section>

      <section className={styles.rail} aria-label="How it works">
        <article>
          <h2>1 · Connect</h2>
          <p>Enter your database&apos;s address, name and login. Nothing is shared yet.</p>
        </article>
        <article>
          <h2>2 · Choose</h2>
          <p>Pick tables and columns. Passwords, tokens and keys stay hidden automatically.</p>
        </article>
        <article>
          <h2>3 · Publish &amp; use</h2>
          <p>Get a live address, a key, interactive docs and code for curl, Python and pandas.</p>
        </article>
      </section>
    </main>
  );
}
