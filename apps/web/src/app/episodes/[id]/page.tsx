import { notFound } from "next/navigation";

import { EpisodeDetail } from "@/components/episodes/episode-detail";

export default async function EpisodeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const index = Number(id);
  if (!Number.isInteger(index) || index < 0) {
    notFound();
  }
  return <EpisodeDetail index={index} />;
}
