"use client";

import { Card, CardBody, CardHeader, EmptyState } from "@/components/ui/primitives";
import { eventTime, eventWhat, eventWhere, eventWho, type AuditEvent } from "@/lib/activity";
import styles from "../pages.module.css";

/** Recent audit events (newest first). Meta never holds secrets — the server strips them. */
export function ActivityCard({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState icon="book" title="No activity yet">
        Changes, publishes and key events show up here as they happen.
      </EmptyState>
    );
  }
  return (
    <Card>
      <CardHeader icon="book" title="Recent activity" description="Who changed what, newest first." />
      <CardBody className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>What</th>
              <th>Where</th>
            </tr>
          </thead>
          <tbody>
            {events
              .slice()
              .reverse()
              .map((e, i) => (
                <tr key={i}>
                  <td className={styles.nowrap}>{eventTime(e)}</td>
                  <td>{eventWho(e)}</td>
                  <td>{eventWhat(e)}</td>
                  <td className={styles.metaCell}>{eventWhere(e)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
