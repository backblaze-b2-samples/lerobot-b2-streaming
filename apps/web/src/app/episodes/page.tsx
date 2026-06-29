import Link from "next/link";
import { Film } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EpisodeList } from "@/components/episodes/episode-list";

export default function EpisodesPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Episodes</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            The LeRobot dataset library on B2 — scoped to the dataset prefix.
            Filter by task, open an episode, or delete one (prefix-scoped).
          </p>
        </div>
        <Button asChild size="sm" className="h-8">
          <Link href="/episodes/new">
            <Film className="h-3.5 w-3.5" />
            Record episode
          </Link>
        </Button>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <EpisodeList />
      </div>
    </div>
  );
}
