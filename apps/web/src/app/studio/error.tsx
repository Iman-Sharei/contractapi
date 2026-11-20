"use client";

import { Button, ButtonLink, EmptyState } from "@/components/ui/primitives";

export default function StudioError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div role="alert">
      <EmptyState
        icon="alert"
        title="Something went wrong"
        action={
          <span style={{ display: "inline-flex", gap: 8 }}>
            <Button variant="primary" icon="refresh" onClick={reset}>
              Try again
            </Button>
            <ButtonLink href="/studio">My APIs</ButtonLink>
          </span>
        }
      >
        {error.message || "Unexpected Studio error."}
      </EmptyState>
    </div>
  );
}
