"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { AlertTriangle, Camera, Clapperboard, Gauge, Loader2, Sliders } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { useCreateEpisode, useSourceInfo } from "@/lib/queries";
import { ApiError } from "@/lib/api-client";

// Task labels are an annotation the user assigns; rendered as a selector.
const PRESET_TASKS = [
  "Pick up the cube",
  "Stack blocks",
  "Open the drawer",
  "Push the button",
] as const;

// Curated, vetted-public LeRobot v3 datasets (mirrors PRESET_SOURCES in the
// backend's types/episodes.py). "Custom repo…" lets a user point ingest at any
// other public owner/name — the one place this form accepts free text.
const SOURCE_PRESETS = [
  "lerobot/svla_so101_pickplace",
  "lerobot/svla_so100_pickplace",
  "lerobot/aloha_sim_insertion_human",
  "lerobot/pusht",
] as const;
const CUSTOM_SOURCE = "__custom__";
const REPO_ID_RE = /^[A-Za-z0-9][\w.-]*\/[\w.-]+$/;
// Mirrors MAX_EPISODE_FRAMES in the backend's types/episodes.py.
const MAX_FRAMES_CEILING = 600;

const schema = z
  .object({
    task: z.enum(PRESET_TASKS),
    source: z.string(),
    custom_repo_id: z.string().optional(),
    // Optional cap; kept as the raw input string and validated below.
    max_frames: z.string().optional(),
  })
  .superRefine((val, ctx) => {
    if (val.source === CUSTOM_SOURCE && !REPO_ID_RE.test((val.custom_repo_id ?? "").trim())) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["custom_repo_id"],
        message: "Enter a HuggingFace repo id like owner/name",
      });
    }
    const mf = (val.max_frames ?? "").trim();
    if (mf !== "") {
      const n = Number(mf);
      if (!Number.isInteger(n) || n < 1 || n > MAX_FRAMES_CEILING) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["max_frames"],
          message: `Enter a whole number from 1 to ${MAX_FRAMES_CEILING}, or leave blank`,
        });
      }
    }
  });

type FormValues = z.infer<typeof schema>;

const DEFAULTS: FormValues = {
  task: "Pick up the cube",
  source: SOURCE_PRESETS[0],
  custom_repo_id: "",
  max_frames: "",
};

// Debounce a value: setState only ever runs inside the timeout callback (never
// synchronously in the effect body), so typing a custom repo doesn't fire a
// request per keystroke.
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Camera;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="text-sm font-medium tabular-nums ml-auto text-right">{value}</span>
    </div>
  );
}

export function EpisodeCreateForm() {
  const router = useRouter();
  const create = useCreateEpisode();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULTS,
  });
  const sourceValue = useWatch({ control: form.control, name: "source" });
  const customRepo = useWatch({ control: form.control, name: "custom_repo_id" });

  // Resolve which repo to preview. For a custom repo we debounce + only probe
  // once it's a well-formed owner/name, so we don't fire a request per keystroke.
  const effectiveRepo =
    sourceValue === CUSTOM_SOURCE ? (customRepo ?? "").trim() : sourceValue;
  const debouncedRepo = useDebounced(
    effectiveRepo,
    sourceValue === CUSTOM_SOURCE ? 500 : 0,
  );
  const repoValid =
    debouncedRepo !== "" &&
    (sourceValue !== CUSTOM_SOURCE || REPO_ID_RE.test(debouncedRepo));
  const previewRepo = repoValid ? debouncedRepo : "";

  const info = useSourceInfo(previewRepo, !!previewRepo);
  // Can only record once we've confirmed the source loads (and shown its shape).
  const canSubmit = !!previewRepo && info.isSuccess && !create.isPending;

  const onSubmit = async (values: FormValues) => {
    const source_repo_id =
      values.source === CUSTOM_SOURCE ? (values.custom_repo_id ?? "").trim() : values.source;
    const mf = (values.max_frames ?? "").trim();
    try {
      const result = await create.mutateAsync({
        source_repo_id,
        task: values.task,
        max_frames: mf === "" ? undefined : Number(mf),
      });
      toast.success(`Episode ep_${String(result.episode.episode_index).padStart(6, "0")} recorded`, {
        description: `${result.bytes_uploaded_human} uploaded to B2 · ${result.object_count} objects · device ${result.device}`,
      });
      router.push(`/episodes/${result.episode.episode_index}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to record episode";
      toast.error("Recording failed", { description: msg });
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Source dataset</CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-6">
            <FormField
              control={form.control}
              name="source"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Source dataset</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full sm:w-96">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {SOURCE_PRESETS.map((s) => (
                        <SelectItem key={s} value={s}>
                          {s}
                        </SelectItem>
                      ))}
                      <SelectItem value={CUSTOM_SOURCE}>Custom repo…</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    The recording reproduces this dataset&apos;s real cameras, fps,
                    resolution, and length — nothing is imposed. Pick &ldquo;Custom
                    repo…&rdquo; to ingest your own public LeRobot v3 dataset.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {sourceValue === CUSTOM_SOURCE && (
              <FormField
                control={form.control}
                name="custom_repo_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Custom HuggingFace repo</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="owner/name"
                        className="w-full sm:w-96"
                        value={field.value ?? ""}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormDescription>
                      Must be a public LeRobot v3 dataset (e.g. your own
                      teleoperation data).
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/* What will be recorded — derived from the source, fail-loud here. */}
            <div className="rounded-lg border border-border bg-muted/30 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                What will be recorded
              </div>
              {!previewRepo ? (
                <p className="text-sm text-muted-foreground">
                  Enter a public LeRobot v3 repo to preview its real shape.
                </p>
              ) : info.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading {previewRepo}…
                </div>
              ) : info.isError ? (
                <div className="flex items-start gap-2 text-sm text-destructive">
                  <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>
                    {info.error instanceof ApiError
                      ? info.error.message
                      : "Couldn't load this dataset."}
                  </span>
                </div>
              ) : info.data ? (
                <div className="grid gap-2.5 sm:grid-cols-2">
                  <PreviewRow
                    icon={Camera}
                    label="Cameras"
                    value={`${info.data.num_cameras} · ${info.data.cameras
                      .map((c) => `${c.width}×${c.height}`)
                      .join(", ")}`}
                  />
                  <PreviewRow icon={Gauge} label="FPS" value={String(info.data.fps)} />
                  <PreviewRow
                    icon={Clapperboard}
                    label="Frames"
                    value={`${info.data.episode_frames} available`}
                  />
                  <PreviewRow
                    icon={Sliders}
                    label="State · action"
                    value={`${info.data.state_dim}-DoF · ${info.data.action_dim}-DoF`}
                  />
                  <PreviewRow icon={Sliders} label="Robot" value={info.data.robot_type} />
                  {info.data.task && (
                    <PreviewRow icon={Clapperboard} label="Source task" value={info.data.task} />
                  )}
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Recording</CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-6">
            <FormField
              control={form.control}
              name="task"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Task</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full sm:w-72">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {PRESET_TASKS.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    The natural-language task label stored in the v3 metadata for
                    this recording.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="max_frames"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Frames to record (optional)</FormLabel>
                  <FormControl>
                    <Input
                      inputMode="numeric"
                      placeholder={
                        info.data
                          ? `Full episode (${info.data.episode_frames})`
                          : "Full episode"
                      }
                      className="w-full sm:w-72"
                      value={field.value ?? ""}
                      onChange={field.onChange}
                    />
                  </FormControl>
                  <FormDescription>
                    Leave blank to record the full first source episode (capped at{" "}
                    {MAX_FRAMES_CEILING}). Lower it for a quick demo clip.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => form.reset(DEFAULTS)}
            disabled={create.isPending}
          >
            Reset
          </Button>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Recording & uploading…" : "Record episode"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
