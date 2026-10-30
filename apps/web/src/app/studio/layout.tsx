import type { Metadata } from "next";
import { StudioNav } from "@/components/studio/StudioNav";
import styles from "@/components/studio/flow.module.css";

export const metadata: Metadata = {
  title: "Studio · contractapi",
  description: "Design, activate, and operate Postgres → FastAPI contracts.",
};

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.page}>
      <StudioNav />
      <main id="studio-main">{children}</main>
    </div>
  );
}
