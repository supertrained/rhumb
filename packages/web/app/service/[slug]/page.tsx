import React from "react";

import { getServiceScore } from "../../../lib/api";

export default async function ServicePage({
  params
}: {
  params: Promise<{ slug: string }>;
}): Promise<JSX.Element> {
  const { slug } = await params;
  const score = await getServiceScore(slug);

  return (
    <section>
      <h1>Service: {slug}</h1>
      <p>Round 7 Slice A scaffold.</p>
      <p>
        Aggregate recommendation score: {score?.aggregateRecommendationScore ?? "pending"}
      </p>
    </section>
  );
}
