"use client";

import { useState } from "react";
import Link from "next/link";
import { Film, Trash2, Radio } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useEpisodes } from "@/lib/queries";
import { DeleteEpisodeButton } from "./delete-episode-button";

const PRESET_TASKS = [
  "Pick up the cube",
  "Stack blocks",
  "Open the drawer",
  "Push the button",
];

export function EpisodeList() {
  const [task, setTask] = useState<string>("all");
  const filter = task === "all" ? undefined : task;
  const { data: episodes = [], isLoading, error, refetch } = useEpisodes(filter);

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Dataset library
          </div>
          <Select value={task} onValueChange={setTask}>
            <SelectTrigger className="w-56" size="sm">
              <SelectValue placeholder="Filter by task" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All tasks</SelectItem>
              {PRESET_TASKS.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : episodes.length === 0 ? (
          <EmptyState
            icon={Film}
            title="No episodes in this dataset yet"
            description="Record a teleoperation episode from real robot footage to populate the B2 dataset prefix."
            action={
              <Button asChild size="sm">
                <Link href="/episodes/new">Record episode</Link>
              </Button>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Episode
                </TableHead>
                <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Task
                </TableHead>
                <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Frames
                </TableHead>
                <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Cameras
                </TableHead>
                <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  FPS
                </TableHead>
                <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Size on B2
                </TableHead>
                <TableHead className="text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Actions
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {episodes.map((ep) => (
                <TableRow key={ep.episode_index} className="table-row-hover">
                  <TableCell className="font-medium">
                    <Link
                      href={`/episodes/${ep.episode_index}`}
                      className="hover:underline"
                    >
                      ep_{String(ep.episode_index).padStart(6, "0")}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-normal">
                      {ep.task}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                    {ep.num_frames}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {ep.num_cameras}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {ep.fps}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                    {ep.size_human}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button asChild size="icon" variant="ghost" className="h-8 w-8" title="Stream">
                        <Link href={`/stream?episode=${ep.episode_index}`}>
                          <Radio className="h-4 w-4" />
                        </Link>
                      </Button>
                      <DeleteEpisodeButton index={ep.episode_index}>
                        <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive" title="Delete">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </DeleteEpisodeButton>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
