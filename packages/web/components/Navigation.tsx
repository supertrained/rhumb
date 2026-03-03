import Link from "next/link";

/** Primary app navigation. */
export function Navigation(): JSX.Element {
  return (
    <nav style={{ display: "flex", gap: 16, padding: 16, borderBottom: "1px solid #e2e8f0" }}>
      <Link href="/">Home</Link>
      <Link href="/services">Services</Link>
      <Link href="/leaderboard/payments">Leaderboard</Link>
      <Link href="/search">Search</Link>
    </nav>
  );
}
