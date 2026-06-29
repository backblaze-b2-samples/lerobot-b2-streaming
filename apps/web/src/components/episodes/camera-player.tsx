"use client";

import { useEffect, useState } from "react";
import { VideoOff } from "lucide-react";

import { getEpisodeVideoUrl } from "@/lib/api-client";

interface Props {
  index: number;
  camera: string;
}

/** Presigned-URL MP4 player for one camera of an episode. The presigned URL
 * is fetched lazily and refreshed if it expires. */
export function CameraPlayer({ index, camera }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    getEpisodeVideoUrl(index, camera)
      .then((r) => {
        if (active) {
          setUrl(r.url);
          setFailed(false);
        }
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [index, camera]);

  return (
    <div className="space-y-1.5">
      <div className="text-xs font-medium text-muted-foreground font-mono">{camera}</div>
      <div className="aspect-square w-full overflow-hidden rounded-lg border border-border bg-muted/40">
        {failed ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <VideoOff className="h-5 w-5" />
            <span className="text-xs">Preview unavailable</span>
          </div>
        ) : url ? (
          <video
            src={url}
            controls
            loop
            muted
            playsInline
            className="h-full w-full object-cover"
            onError={() => setFailed(true)}
          />
        ) : (
          <div className="h-full w-full animate-pulse bg-muted" />
        )}
      </div>
    </div>
  );
}
