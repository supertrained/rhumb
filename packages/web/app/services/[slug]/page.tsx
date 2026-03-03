import Link from "next/link";

import { DimensionChart } from "../../../components/DimensionChart";
import { ScoreDisplay } from "../../../components/ScoreDisplay";

export default async function ServiceDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<JSX.Element> {
  const { slug } = await params;

  return (
    <section>
      <h1>Service: {slug}</h1>
      <ScoreDisplay score={null} />
      <DimensionChart />
      <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
        <Link href={`/services/${slug}/failures`}>Failures</Link>
        <Link href={`/services/${slug}/history`}>History</Link>
      </div>
    </section>
  );
}
