import Link from "next/link";
import styles from "@/components/studio/flow.module.css";

export default function StudioNotFound() {
  return (
    <section className={styles.panel}>
      <h1 className={styles.title}>Page not found</h1>
      <p>That Studio route does not exist.</p>
      <Link className={styles.secondary} href="/studio">
        ← My APIs
      </Link>
    </section>
  );
}
