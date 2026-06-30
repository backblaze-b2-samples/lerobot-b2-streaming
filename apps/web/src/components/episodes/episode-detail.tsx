"use client";

import Link from "next/link";
import { Radio, Trash2, ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { useEpisode } from "@/lib/queries";
import { CameraPlayer } from "./camera-player";
import { EpisodeRelabelForm } from "./episode-relabel-form";
import { DeleteEpisodeButton } from "./delete-episode-button";

function Meta({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-sm font-medium tabular-nums mt-0.5">{value}</div>
    </div>
  );
}

export function EpisodeDetail({ index }: { index: number }) {
  const { data: ep, isLoading, error, refetch } = useEpisode(index);
  const label = `ep_${String(index).padStart(6, "0")}`;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (error || !ep) {
    return <ErrorState error={error} onRetry={() => refetch()} />;
  }

  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/episodes"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3 w-3" />
            Episodes
          </Link>
          <h1 className="page-title mt-1 font-mono">{label}</h1>
          <div className="mt-2 flex items-center gap-2">
            <Badge variant="secondary" className="font-normal">{ep.task}</Badge>
          </div>
        </div>
        <div className="flex gap-2">
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link href={`/stream?episode=${ep.episode_index}`}>
              <Radio className="h-3.5 w-3.5" />
              Stream
            </Link>
          </Button>
          <DeleteEpisodeButton index={ep.episode_index} redirectTo="/episodes">
            <Button size="sm" variant="outline" className="h-8 text-destructive">
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </Button>
          </DeleteEpisodeButton>
        </div>
      </div>

      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title">Cameras</CardTitle>
        </CardHeader>
        <CardContent className="p-5">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {ep.videos.length === 0 ? (
              <p className="text-sm text-muted-foreground">No camera videos found.</p>
            ) : (
              ep.videos.map((v) => (
                <CameraPlayer key={v.camera} index={ep.episode_index} camera={v.camera} />
              ))
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title">Metadata</CardTitle>
        </CardHeader>
        <CardContent className="p-5">
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
            <Meta label="Frames" value={ep.num_frames} />
            <Meta label="FPS" value={ep.fps} />
            <Meta label="Cameras" value={ep.num_cameras} />
            <Meta label="Resolution" value={`${ep.frame_width}×${ep.frame_height}`} />
            <Meta label="Frame range" value={`${ep.dataset_from_index}–${ep.dataset_to_index}`} />
            <Meta label="Size on B2" value={ep.size_human} />
            <Meta label="Objects" value={ep.videos.length + 3} />
          </div>
          <div className="mt-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              B2 prefix
            </div>
            <code className="text-xs font-mono text-muted-foreground break-all">{ep.prefix}</code>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title">Edit · relabel task</CardTitle>
        </CardHeader>
        <CardContent className="p-5">
          <p className="text-sm text-muted-foreground mb-4">
            Frames are immutable, but the task annotation is index metadata. Saving
            rewrites this episode&apos;s v3 metadata in B2.
          </p>
          <EpisodeRelabelForm index={ep.episode_index} currentTask={ep.task} />
        </CardContent>
      </Card>
    </div>
  );
}
