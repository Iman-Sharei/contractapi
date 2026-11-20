"use client";

import { Button, Card, CardBody, CardHeader, EmptyState } from "@/components/ui/primitives";
import { downloadOpenApi, downloadPostman, downloadSdk } from "@/lib/api";
import type { SpecListItem } from "@/lib/types";
import styles from "../pages.module.css";
import type { RunAction } from "./shared";

export function DownloadsCard({ specs, pending, run }: { specs: SpecListItem[]; pending: boolean; run: RunAction }) {
  if (specs.length === 0) {
    return (
      <EmptyState icon="file" title="Nothing to download yet">
        Save an API first; its Postman collection, Python client and OpenAPI file appear here.
      </EmptyState>
    );
  }
  return (
    <Card>
      <CardHeader
        icon="file"
        title="Downloads"
        description="Ready-made clients and descriptions of each API, for your team or other tools."
      />
      <CardBody>
        <ul className={styles.keyList}>
          {specs.map((s) => (
            <li key={s.name}>
              <div className={styles.keyInfo}>
                <strong>{s.title || s.name}</strong>
                <span className={styles.muted}>
                  <code>{s.name}</code>
                </span>
              </div>
              <span className={styles.downloadBtns}>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={pending}
                  onClick={() => run(() => downloadPostman(s.name), `Downloaded the Postman collection for ${s.name}.`)}
                >
                  Postman
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={pending}
                  onClick={() => run(() => downloadSdk(s.name), `Downloaded the Python client for ${s.name}.`)}
                >
                  Python client
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={pending}
                  onClick={() => run(() => downloadOpenApi(s.name, "json"), `Downloaded OpenAPI JSON for ${s.name}.`)}
                >
                  OpenAPI JSON
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={pending}
                  onClick={() => run(() => downloadOpenApi(s.name, "yaml"), `Downloaded OpenAPI YAML for ${s.name}.`)}
                >
                  OpenAPI YAML
                </Button>
              </span>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
