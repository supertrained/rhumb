import { useState } from "react";

const NAV_LINKS = [
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/capabilities", label: "Capabilities" },
  { href: "/search", label: "Search" },
  { href: "/docs", label: "Docs" },
  { href: "/glossary", label: "Glossary" },
  { href: "/blog", label: "Blog" },
  { href: "/about", label: "About" },
];

export default function MobileNav({ currentPath }: { currentPath: string }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
      <button
        className="md:hidden p-2 text-slate-400 hover:text-slate-100 transition-colors"
        onClick={() => setMenuOpen((o) => !o)}
        aria-label="Toggle navigation menu"
        aria-expanded={menuOpen}
      >
        {menuOpen ? (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M2 2L16 16M16 2L2 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M2 5H16M2 9H16M2 13H16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        )}
      </button>

      {menuOpen && (
        <div className="md:hidden absolute top-14 left-0 right-0 border-t border-slate-800 bg-surface px-6 py-4 flex flex-col gap-1 z-50">
          {NAV_LINKS.map(({ href, label }) => {
            const active = currentPath === href || currentPath.startsWith(href + "/");
            return (
              <a
                key={href}
                href={href}
                onClick={() => setMenuOpen(false)}
                className={`px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  active ? "text-slate-100 bg-slate-800/60" : "text-slate-400 hover:text-slate-100"
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
