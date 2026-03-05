import React from "react";
import Link from "next/link";

export default function HomePage(): JSX.Element {
  return (
    <section>
      <h1>Rhumb</h1>
      <p>Agent-native tool discovery and scoring.</p>
      <ul style={{ display: "grid", gap: 8, marginTop: 16 }}>
        <li>
          <Link href="/leaderboard/payments">View payments leaderboard</Link>
        </li>
        <li>
          <Link href="/service/stripe">View service scaffold (stripe)</Link>
        </li>
      </ul>
    </section>
  );
}
