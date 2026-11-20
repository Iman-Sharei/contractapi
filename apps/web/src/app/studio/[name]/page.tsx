"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";
import { ApiWorkspace } from "@/components/studio/workspace/ApiWorkspace";

function ApiPage() {
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name);
  // key: a different API gets fresh editor state.
  return <ApiWorkspace key={name} name={name} />;
}

export default function ApiDetailPage() {
  return (
    <Suspense>
      <ApiPage />
    </Suspense>
  );
}
