import { redirect } from "next/navigation";

export default async function ServiceHistoryRedirectPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<never> {
  const { slug } = await params;
  redirect(`/service/${slug}`);
}
