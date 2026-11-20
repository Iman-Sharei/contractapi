"use client";

import { Card, CardBody, CardHeader, EmptyState } from "@/components/ui/primitives";
import styles from "../pages.module.css";

const SKIP = ["ts", "timestamp", "action", "event", "type"];

/** Recent audit events (newest first). Meta never holds secrets — the server strips them. */
export function ActivityCard({ events }: { events: Record<string, unknown>[] }) {
  if (events.length === 0) {
    return (
      <EmptyState icon="book" title="No activity yet">
        Changes, publishes and key events show up here as they happen.
      </EmptyState>
    );
  }
  return (
    <Card>
      <CardHeader icon="book" title="Recent activity" description="The latest changes and sign-ins on this server." />
      <CardBody className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {events
              .slice()
              .reverse()
              .map((e, i) => {
                const ts =
                  typeof e.ts === "number"
                    ? new Date(e.ts * 1000).toLocaleString()
                    : typeof e.timestamp === "string"
                      ? e.timestamp
                      : "—";
                const meta = JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => !SKIP.includes(k))));
                return (
                  <tr key={i}>
                    <td className={styles.nowrap}>{ts}</td>
                    <td>
                      <code>{String(e.action ?? e.event ?? e.type ?? "—")}</code>
                    </td>
                    <td className={styles.metaCell}>{meta.slice(0, 180)}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
