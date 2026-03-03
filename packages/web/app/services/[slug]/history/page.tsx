export default async function ServiceHistoryPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<JSX.Element> {
  const { slug } = await params;

  return (
    <section>
      <h1>{slug} score history</h1>
      <p>Historical chart scaffold.</p>
    </section>
  );
}
