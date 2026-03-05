import React from "react";

import { getLeaderboard } from "../../../lib/api";

export default async function LeaderboardPage({
  params
}: {
  params: Promise<{ category: string }>;
}): Promise<JSX.Element> {
  const { category } = await params;
  const leaderboard = await getLeaderboard(category);

  return (
    <section>
      <h1>{leaderboard.category} leaderboard</h1>
      <p>Round 7 Slice A scaffold.</p>
      <p>Entries loaded: {leaderboard.items.length}</p>
    </section>
  );
}
