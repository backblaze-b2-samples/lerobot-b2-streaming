import { StreamRunner } from "@/components/stream/stream-runner";

export default async function StreamPage({
  searchParams,
}: {
  searchParams: Promise<{ episode?: string }>;
}) {
  const { episode } = await searchParams;
  const initialEpisode =
    episode !== undefined && Number.isInteger(Number(episode))
      ? Number(episode)
      : undefined;

  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Stream from B2</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Stream an episode or task split chunk-by-chunk from Backblaze B2 over
          the S3 API into a mini training loop — and watch how little of the
          dataset actually moves.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <StreamRunner initialEpisode={initialEpisode} />
      </div>
    </div>
  );
}
