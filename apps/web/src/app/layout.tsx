import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "contractapi — turn your database into a secure API",
  description:
    "Connect a database, choose what to share and publish a secure, documented REST API — no code.",
};

/** Applies a saved light/dark choice before paint (no flash). Absent = follow the system. */
const THEME_INIT = `try{var t=localStorage.getItem("contractapi-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
        {/* Loaded at runtime so Docker/CI builds do not depend on fonts.gstatic.com */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- App Router root layout applies to every page */}
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;550;600;650;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
