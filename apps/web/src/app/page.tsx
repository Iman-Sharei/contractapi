import { Brand } from "@/components/studio/StudioFrame";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ButtonLink } from "@/components/ui/primitives";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import styles from "./page.module.css";

const STEPS: { icon: IconName; title: string; text: string }[] = [
  { icon: "database", title: "Connect", text: "Enter your database's address, name and login. Nothing is shared yet." },
  { icon: "table", title: "Choose", text: "Tick tables and columns. Passwords, tokens and keys stay hidden automatically." },
  { icon: "zap", title: "Publish & use", text: "Get a live address, a key, interactive docs and code for curl, Python and pandas." },
];

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: "shield", title: "Safe by default", text: "Read-only, private columns hidden, rate limits and an audit log — switched on from the start." },
  { icon: "key", title: "Keys or login tokens", text: "Hand out API keys per app, or use JWT with roles and per-row access." },
  { icon: "book", title: "Docs that write themselves", text: "Every API gets interactive OpenAPI docs, a Postman collection and a Python client." },
  { icon: "search", title: "Filter, sort, page", text: "Callers filter by allowed fields, search, sort and follow next-page links." },
  { icon: "compare", title: "Versions you can trust", text: "Every save is kept. Compare versions and see breaking changes before you publish." },
  { icon: "code", title: "Custom SQL when needed", text: "Turn a safe SELECT or a totals query into an endpoint with typed parameters." },
];

export default function HomePage() {
  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <Brand />
        <div className={styles.navRight}>
          <ThemeToggle />
          <ButtonLink href="/studio" variant="secondary">
            Open Studio
          </ButtonLink>
        </div>
      </header>

      <main>
        <section className={styles.hero}>
          <div className={styles.heroText}>
            <span className={styles.pill}>
              <Icon name="sparkles" size={14} /> For data people — no code needed
            </span>
            <h1 className={styles.title}>
              Turn your database into a <span className={styles.gradient}>secure API</span>
            </h1>
            <p className={styles.lede}>
              Connect a database, tick the tables and columns to share, and publish. You get a
              standard REST API with keys, documentation and ready-to-run code — read-only, with
              private columns hidden by default.
            </p>
            <div className={styles.ctaRow}>
              <ButtonLink href="/studio/new" variant="primary" size="lg" icon="plus">
                Create an API
              </ButtonLink>
              <ButtonLink href="/studio" variant="secondary" size="lg">
                My APIs
              </ButtonLink>
            </div>
          </div>

          <div className={styles.preview} aria-hidden>
            <div className={styles.previewBar}>
              <span />
              <span />
              <span />
              <em>customers · live</em>
            </div>
            <pre className={styles.previewCode}>
              <span className={styles.c1}>$</span> curl https://api.example.com/apis/shop/customers?limit=2 \{"\n"}
              {"    "}-H <span className={styles.c2}>&quot;X-API-Key: dk_••••••&quot;</span>
              {"\n\n"}
              {"{"}
              {"\n  "}
              <span className={styles.c3}>&quot;items&quot;</span>: [{"\n    "}
              {"{ "}
              <span className={styles.c3}>&quot;id&quot;</span>: 1, <span className={styles.c3}>&quot;name&quot;</span>:{" "}
              <span className={styles.c2}>&quot;Ada Lovelace&quot;</span>
              {" },"}
              {"\n    "}
              {"{ "}
              <span className={styles.c3}>&quot;id&quot;</span>: 2, <span className={styles.c3}>&quot;name&quot;</span>:{" "}
              <span className={styles.c2}>&quot;Alan Turing&quot;</span>
              {" }"}
              {"\n  ],\n  "}
              <span className={styles.c3}>&quot;next_cursor&quot;</span>: <span className={styles.c2}>&quot;eyJpZCI6Mn0&quot;</span>
              {"\n}"}
            </pre>
            <div className={styles.previewFoot}>
              <span className={styles.ok}>
                <Icon name="lock" size={13} /> password_hash hidden
              </span>
              <span className={styles.ok}>
                <Icon name="shield" size={13} /> read-only
              </span>
            </div>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="how">
          <h2 id="how" className={styles.sectionTitle}>
            Three steps from table to API
          </h2>
          <ol className={styles.steps}>
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span className={styles.stepIcon}>
                  <Icon name={s.icon} size={20} />
                </span>
                <span className={styles.stepNum}>Step {i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.section} aria-labelledby="features">
          <h2 id="features" className={styles.sectionTitle}>
            Everything a standard API needs, from one screen
          </h2>
          <div className={styles.features}>
            {FEATURES.map((f) => (
              <article key={f.title}>
                <Icon name={f.icon} size={18} />
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.band}>
          <h2>Ready to share your data safely?</h2>
          <p>Your first API takes about a minute.</p>
          <ButtonLink href="/studio/new" variant="primary" size="lg" icon="arrowRight">
            Start now
          </ButtonLink>
        </section>
      </main>

      <footer className={styles.footer}>
        <span>contractapi — secure APIs from your database</span>
      </footer>
    </div>
  );
}
