import { EpisodeCreateForm } from "@/components/episodes/episode-create-form";

export default function NewEpisodePage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Record Episode</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Synthesize a teleoperation episode with the real LeRobot v3 API and
          upload the dataset tree to Backblaze B2. Runs locally on CPU (or the
          detected GPU) — no external API key.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2 max-w-2xl">
        <EpisodeCreateForm />
      </div>
    </div>
  );
}
