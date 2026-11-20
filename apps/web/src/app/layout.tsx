import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "contractapi — turn your database into a secure API",
  description:
    "Connect a database, choose what to share and publish a secure, documented REST API — no code.",
};

/** Applies a saved light/dark choice before paint (no flash). Absent = follow the system. */
const THEME_INIT = `try{var t=localStorage.getItem("contractapi-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

const FONTS_URL =
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;550;600;650;700&family=JetBrains+Mono:wght@400;500&display=swap";

/** Web fonts load after the page, so a slow or blocked fonts.googleapis.com (company
 *  firewalls) never delays the Studio; until then the system font is used. */
const FONTS_LATE = `addEventListener("load",function(){var l=document.createElement("link");l.rel="stylesheet";l.href=${JSON.stringify(FONTS_URL)};document.head.appendChild(l)})`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
        {/* Loaded at runtime (not at build) so Docker/CI builds work offline. */}
        <script dangerouslySetInnerHTML={{ __html: FONTS_LATE }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
