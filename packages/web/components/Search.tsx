"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect } from "react";

/** Styled search input — amber focus ring, dark surface. */
export function Search(): JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      router.push(`/search?q=${encodeURIComponent(trimmed)}`);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative">
        {/* Search icon */}
        <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-500">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M11 6.5C11 9.0 9.0 11 6.5 11C4.0 11 2 9.0 2 6.5C2 4.0 4.0 2 6.5 2C9.0 2 11 4.0 11 6.5ZM10.2 10.9L14 14.7"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </div>

        <input
          aria-label="Search services"
          type="search"
          name="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search services, APIs, categories…"
          className="
            w-full pl-11 pr-4 py-3.5 rounded-xl
            bg-surface border border-slate-700
            text-slate-100 placeholder-slate-500
            font-display text-sm
            outline-none
            focus:border-amber focus:ring-2 focus:ring-amber/20
            transition-all duration-200
          "
        />

        {query && (
          <button
            type="submit"
            className="absolute inset-y-0 right-3 flex items-center px-3 text-xs font-mono text-amber hover:text-amber-dark transition-colors"
          >
            Search ↵
          </button>
        )}
      </div>
    </form>
  );
}
