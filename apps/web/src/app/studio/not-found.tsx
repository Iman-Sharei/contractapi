import { ButtonLink, EmptyState } from "@/components/ui/primitives";

export default function StudioNotFound() {
  return (
    <EmptyState
      icon="search"
      title="Page not found"
      action={
        <ButtonLink href="/studio" icon="arrowLeft">
          My APIs
        </ButtonLink>
      }
    >
      That Studio page does not exist.
    </EmptyState>
  );
}
