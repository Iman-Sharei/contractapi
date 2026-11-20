"use client";

import { CodeBlock } from "@/components/ui/CodeBlock";
import { Button, Card, CardBody, CardHeader } from "@/components/ui/primitives";
import type { EditorState } from "../editor/useEditorState";

/** The whole API as one YAML file — what `contractapi serve` and Git use. */
export function FileTab({ s }: { s: EditorState }) {
  const { yamlText, localYaml, onRefreshYaml, pending, dirty } = s;
  return (
    <Card>
      <CardHeader
        icon="file"
        title="API file (YAML)"
        description={
          dirty
            ? "Includes your unsaved changes. Save to keep them."
            : "Everything about this API in one file — review it, copy it into Git, or run it with the contractapi command."
        }
        actions={
          <Button size="sm" variant="secondary" icon="refresh" onClick={onRefreshYaml} disabled={pending}>
            Refresh
          </Button>
        }
      />
      <CardBody>
        <CodeBlock code={yamlText || localYaml} title="contract.yaml" />
      </CardBody>
    </Card>
  );
}
