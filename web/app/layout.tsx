import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { EngineVersion } from "@/components/EngineBar";
import Nav from "@/components/Nav";
import ServiceWorker from "@/components/ServiceWorker";
import ThemeSwitch from "@/components/ThemeSwitch";
import "./globals.css";

export const metadata: Metadata = {
  title: "ri-layercake · reinsurance towers to editable PowerPoint",
  description: "Paste a reinsurance programme, shape the tower, drop a loss through it and export a native, editable PowerPoint slide. Runs entirely in your browser.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0E5A8A" };

const THEME_SCRIPT =
  "try{var t=localStorage.getItem('ri-layercake/theme');if(t)document.documentElement.dataset.theme=t}catch(e){}";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" data-theme="light" suppressHydrationWarning>
      <head>
        {/* Apply the saved theme before first paint, so there is no flash. Hashed into the CSP at build time. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        <header className="site-header">
          <Link href="/" prefetch={false} className="brand" aria-label="ri-layercake home">
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
              <rect x="3" y="15" width="16" height="5" rx="1" fill="#0E5A8A" />
              <rect x="3" y="9" width="16" height="5" rx="1" fill="#3FA7B5" />
              <rect x="3" y="3" width="16" height="5" rx="1" fill="#7BC4C4" />
            </svg>
            ri-layercake
          </Link>
          <Nav />
          <ThemeSwitch />
        </header>
        <main id="main">{children}</main>
        <footer className="site-footer">
          <p>
            <strong>Private by construction.</strong> Your programme never leaves this browser: parsing, maths and export
            all run on your machine, and the page makes no network requests while you edit or export. Autosave stays in
            this browser and Clear data removes it. Outputs are illustrative, based on the inputs provided, and not
            pricing or actuarial advice.
          </p>
          <p className="footer-meta">
            <EngineVersion /> · <Link href="/contact/" prefetch={false}>Contact</Link> · MIT licence
          </p>
        </footer>
        <ServiceWorker />
      </body>
    </html>
  );
}
