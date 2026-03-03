export default async function LeaderboardPage({
  params,
}: {
  params: Promise<{ category: string }>;
}): Promise<JSX.Element> {
  const { category } = await params;

  return (
    <section>
      <h1>{category} leaderboard</h1>
      <p>Category rankings scaffold.</p>
    </section>
  );
}
