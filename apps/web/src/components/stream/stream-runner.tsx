"use client";

import { useState } from "react";
import { Radio, Zap, Database, Layers, Gauge } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ErrorState } from "@/components/ui/error-state";
import { useEpisodes, useRunStream } from "@/lib/queries";
import type { StreamRunStats } from "@lerobot-s3-streaming/shared";

const PRESET_TASKS = [
  "Pick up the cube",
  "Stack blocks",
  "Open the drawer",
  "Push the button",
];

function Stat({ icon: Icon, label, value, accent }: { icon: typeof Zap; label: string; value: string; accent?: boolean }) {
  return (
    <Card className={accent ? "border-primary/40" : ""}>
      <CardHeader className="flex flex-row items-center justify-between pt-4 pb-2 px-4 space-y-0">
        <CardTitle className="text-xs font-semibold text-muted-foreground">{label}</CardTitle>
        <div className="stat-icon-wrap">
          <Icon className="h-4 w-4" />
        </div>
      </CardHeader>
      <CardContent className="pb-5 px-4">
        <div className="stat-value">{value}</div>
      </CardContent>
    </Card>
  );
}

export function StreamRunner({ initialEpisode }: { initialEpisode?: number }) {
  const { data: episodes = [] } = useEpisodes();
  const run = useRunStream();
  const [mode, setMode] = useState<"episode" | "task">(
    initialEpisode !== undefined ? "episode" : "task",
  );
  const [episode, setEpisode] = useState<string>(
    initialEpisode !== undefined ? String(initialEpisode) : "",
  );
  const [task, setTask] = useState<string>("all");
  const [workers, setWorkers] = useState<string>("1");
  const [stats, setStats] = useState<StreamRunStats | null>(null);

  const onRun = async () => {
    setStats(null);
    const req = {
      workers: Number(workers),
      episode_index: mode === "episode" && episode ? Number(episode) : null,
      task: mode === "task" && task !== "all" ? task : null,
    };
    const result = await run.mutateAsync(req);
    setStats(result);
  };

  const ratioPct = stats ? Math.round(stats.fetch_ratio * 100) : 0;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title">Streaming run</CardTitle>
        </CardHeader>
        <CardContent className="p-5 space-y-5">
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Source</label>
              <Select value={mode} onValueChange={(v) => setMode(v as "episode" | "task")}>
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="episode">Single episode</SelectItem>
                  <SelectItem value="task">Task split</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {mode === "episode" ? (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Episode</label>
                <Select value={episode} onValueChange={setEpisode}>
                  <SelectTrigger className="w-56">
                    <SelectValue placeholder="Pick an episode" />
                  </SelectTrigger>
                  <SelectContent>
                    {episodes.map((e) => (
                      <SelectItem key={e.episode_index} value={String(e.episode_index)}>
                        ep_{String(e.episode_index).padStart(6, "0")} · {e.task}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Task split</label>
                <Select value={task} onValueChange={setTask}>
                  <SelectTrigger className="w-56">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All episodes</SelectItem>
                    {PRESET_TASKS.map((t) => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Workers</label>
              <Select value={workers} onValueChange={setWorkers}>
                <SelectTrigger className="w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[1, 2, 4, 8].map((w) => (
                    <SelectItem key={w} value={String(w)}>{w}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={onRun}
              disabled={run.isPending || (mode === "episode" && !episode)}
            >
              <Radio className="h-3.5 w-3.5" />
              {run.isPending ? "Streaming from B2…" : "Stream from B2"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Each run reads the small v3 metadata, then issues S3 ranged GETs to
            pull only the Parquet row-groups and video byte-ranges the selection
            needs — never the whole dataset — and feeds a mini training step.
          </p>
        </CardContent>
      </Card>

      {run.error && <ErrorState error={run.error} onRetry={onRun} />}

      {stats && (
        <div className="space-y-6 animate-fade-in-up">
          <Card className="border-primary/40">
            <CardContent className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Bytes fetched from B2 vs total dataset
                  </div>
                  <div className="mt-1 text-2xl font-semibold tabular-nums">
                    {stats.bytes_fetched_human}
                    <span className="text-muted-foreground text-base font-normal">
                      {" "}/ {stats.total_dataset_bytes_human}
                    </span>
                  </div>
                </div>
                <Badge variant="secondary" className="text-sm">
                  {ratioPct}% fetched
                </Badge>
              </div>
              <Progress value={ratioPct} className="mt-3" />
              <p className="mt-2 text-xs text-muted-foreground">
                Only {ratioPct}% of the dataset was transferred — the ranged-GET
                bridge avoids a full per-researcher download.
              </p>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon={Layers} label="Episodes streamed" value={String(stats.episodes_streamed)} />
            <Stat icon={Database} label="Frames decoded" value={String(stats.frames_decoded)} />
            <Stat icon={Gauge} label="Throughput" value={`${stats.throughput_frames_per_s} fps`} />
            <Stat icon={Zap} label="Device" value={stats.device} />
          </div>

          {stats.train_loss_start !== null && (
            <p className="text-sm text-muted-foreground">
              Mini training loop loss: {stats.train_loss_start} → {stats.train_loss_end}
              {" "}(tiny MLP, {stats.elapsed_s}s elapsed)
            </p>
          )}

          {stats.per_worker.length > 1 && (
            <Card>
              <CardHeader className="border-b border-border py-4 px-5">
                <CardTitle className="card-title">Per-worker throughput</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Worker</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Episodes</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Frames</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Fetched</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">fps</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {stats.per_worker.map((w) => (
                      <TableRow key={w.worker_id}>
                        <TableCell className="font-mono text-xs">#{w.worker_id}</TableCell>
                        <TableCell className="tabular-nums">{w.episodes_streamed}</TableCell>
                        <TableCell className="tabular-nums">{w.frames_decoded}</TableCell>
                        <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">{w.bytes_fetched_human}</TableCell>
                        <TableCell className="tabular-nums">{w.throughput_frames_per_s.toFixed(1)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
