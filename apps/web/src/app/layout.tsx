import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "contractapi — Spec-first Postgres APIs",
  description:
    "Design secure, documented FastAPI endpoints over PostgreSQL without mirroring your entire schema.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        {/* Loaded at runtime so Docker/CI builds do not depend on fonts.gstatic.com */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Syne:wght@600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
