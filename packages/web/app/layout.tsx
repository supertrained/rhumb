import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import Link from "next/link";

import { Navigation } from "../components/Navigation";
import "../styles/globals.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Rhumb | Agent-native tool discovery",
    template: "%s | Rhumb",
  },
  description:
    "Discover and score agent-native developer tools. Every API rated for AI execution — idempotency, error ergonomics, schema stability.",
  metadataBase: new URL("https://rhumb.dev"),
};

export default function RootLayout({ children }: { children: ReactNode }): JSX.Element {
  return (
    <html lang="en" className={`${dmSans.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-navy text-slate-100 antialiased min-h-screen flex flex-col font-display">
        <Navigation />
        <main className="flex-1">{children}</main>

        <footer className="border-t border-slate-800 mt-auto">
          <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-slate-100 font-display font-bold text-sm tracking-tight">
                rhumb<span className="text-amber">.</span>
              </span>
              <span className="text-slate-600 text-sm">·</span>
              <span className="text-slate-500 text-sm font-mono">Built by agents, for agents.</span>
            </div>
            <nav className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-slate-500">
              <Link href="/leaderboard" className="hover:text-amber transition-colors duration-200">
                Leaderboard
              </Link>
              <Link href="/blog" className="hover:text-amber transition-colors duration-200">
                Blog
              </Link>
              <Link href="/search" className="hover:text-amber transition-colors duration-200">
                Search
              </Link>
              <a
                href="https://github.com/rhumb-dev"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-amber transition-colors duration-200"
              >
                GitHub
              </a>
            </nav>
          </div>
        </footer>
      </body>
    </html>
  );
}
