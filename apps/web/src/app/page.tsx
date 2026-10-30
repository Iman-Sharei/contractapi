import Link from "next/link";
import styles from "./page.module.css";

const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export default function HomePage() {
  return (
    <main className={styles.page}>
      <header className={styles.nav}>
        <div className={styles.brand}>dataapi</div>
        <Link className={styles.navLink} href="/studio">
          Open Studio
        </Link>
      </header>

      <section className={styles.hero}>
        <p className={styles.kicker}>Postgres → designed FastAPI</p>
        <h1 className={styles.title}>dataapi</h1>
        <p className={styles.lede}>
          Spec-first APIs for data teams. Opt-in tables, explicit field allowlists, safe filters,
          read-only by default — not another schema mirror.
        </p>
        <div className={styles.ctaRow}>
          <Link className={styles.cta} href="/studio/new">
            Design an API
          </Link>
          <Link className={styles.ghost} href="/studio">
            My APIs
          </Link>
          <a className={styles.ghost} href={`${apiBase}/docs`} target="_blank" rel="noreferrer">
            Backend docs
          </a>
        </div>
      </section>

      <section className={styles.rail} aria-label="Studio flow">
        <article>
          <h2>1 · Catalog</h2>
          <p>See saved contracts, what’s live under /data, activate or delete.</p>
        </article>
        <article>
          <h2>2 · Wizard</h2>
          <p>Connect → sources → shape → guards → review — then open the editor.</p>
        </article>
        <article>
          <h2>3 · Diff</h2>
          <p>Compare OpenAPI of two saved specs before you promote a change.</p>
        </article>
      </section>
    </main>
  );
}
