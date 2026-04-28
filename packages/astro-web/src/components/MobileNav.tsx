import { useState } from "react";

const NAV_LINKS = [
  { href: "/#find-trust-execute", label: "Product" },
  { href: "/search", label: "Index" },
  { href: "/resolve", label: "Resolve" },
  { href: "/trust", label: "Trust" },
  { href: "/docs", label: "Docs" },
  { href: "/pricing", label: "Pricing" },
  { href: "/#quickstart", label: "Run MCP" },
  { href: "/search", label: "Start free" },
];

export default function MobileNav({ currentPath }: { currentPath: string }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
      <button
        className="rounded-full border border-white/10 p-2 text-rhumb-muted transition-colors hover:border-rhumb-gold/40 hover:text-rhumb-cream lg:hidden"
        onClick={() => setMenuOpen((o) => !o)}
        aria-label="Toggle navigation menu"
        aria-expanded={menuOpen}
        type="button"
      >
        {menuOpen ? (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M2 2L16 16M16 2L2 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M2 5H16M2 9H16M2 13H16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        )}
      </button>

      {menuOpen && (
        <div className="absolute left-0 right-0 top-16 z-50 flex flex-col gap-1 border-b border-white/10 bg-rhumb-deep px-5 py-5 shadow-2xl lg:hidden">
          {NAV_LINKS.map(({ href, label }) => {
            const active = href !== "/#find-trust-execute" && (currentPath === href || currentPath.startsWith(href + "/"));
            return (
              <a
                key={`${href}-${label}`}
                href={href}
                onClick={() => setMenuOpen(false)}
                className={`rounded-xl px-3 py-3 text-sm font-medium transition-colors ${
                  active ? "bg-white/8 text-rhumb-cream" : "text-rhumb-muted hover:bg-white/7 hover:text-rhumb-cream"
                }`}
              >
                {label}
              </a>
            );
          })}
        </div>
      )}
    </>
  );
}
