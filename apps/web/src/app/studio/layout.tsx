import type { Metadata } from "next";
import { StudioFrame } from "@/components/studio/StudioFrame";

export const metadata: Metadata = {
  title: "Studio · contractapi",
  description: "Design, publish and run secure APIs over your database.",
};

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return <StudioFrame>{children}</StudioFrame>;
}
