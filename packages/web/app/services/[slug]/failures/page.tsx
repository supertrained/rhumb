import { FailureModeTags } from "../../../../components/FailureModeTags";

export default async function ServiceFailuresPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<JSX.Element> {
  const { slug } = await params;

  return (
    <section>
      <h1>{slug} failures</h1>
      <FailureModeTags tags={["AF", "SB", "AV"]} />
    </section>
  );
}
