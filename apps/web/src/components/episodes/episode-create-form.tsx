"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useCreateEpisode } from "@/lib/queries";
import { ApiError } from "@/lib/api-client";

// Finite option sets are rendered as selectors (never free text). Safe
// defaults are surfaced as guidance only (FormDescription), not an autofill
// button — per the create-form UX conventions.
const PRESET_TASKS = [
  "Pick up the cube",
  "Stack blocks",
  "Open the drawer",
  "Push the button",
] as const;

const schema = z.object({
  task: z.enum(PRESET_TASKS),
  num_cameras: z.coerce.number().int().refine((v) => [1, 2, 3].includes(v)),
  num_frames: z.coerce.number().int().refine((v) => [30, 60, 120].includes(v)),
  fps: z.coerce.number().int().refine((v) => [10, 30].includes(v)),
  resolution: z.coerce.number().int().refine((v) => [128, 256].includes(v)),
});

type FormValues = z.infer<typeof schema>;

const DEFAULTS: FormValues = {
  task: "Pick up the cube",
  num_cameras: 2,
  num_frames: 60,
  fps: 30,
  resolution: 256,
};

function NumberSelect({
  value,
  onChange,
  options,
  format,
  width = "w-40",
}: {
  value: number;
  onChange: (v: number) => void;
  options: number[];
  format?: (n: number) => string;
  width?: string;
}) {
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))}>
      <FormControl>
        <SelectTrigger className={width}>
          <SelectValue />
        </SelectTrigger>
      </FormControl>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o} value={String(o)}>
            {format ? format(o) : o}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function EpisodeCreateForm() {
  const router = useRouter();
  const create = useCreateEpisode();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULTS,
  });

  const onSubmit = async (values: FormValues) => {
    try {
      const result = await create.mutateAsync(values);
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
            <CardTitle className="card-title">Recording parameters</CardTitle>
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
                      <SelectTrigger className="w-72">
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
                    The natural-language task label stored in the v3 metadata.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="num_cameras"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Cameras</FormLabel>
                  <NumberSelect
                    value={field.value}
                    onChange={field.onChange}
                    options={[1, 2, 3]}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="num_frames"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Frames</FormLabel>
                  <NumberSelect
                    value={field.value}
                    onChange={field.onChange}
                    options={[30, 60, 120]}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="fps"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>FPS</FormLabel>
                  <NumberSelect
                    value={field.value}
                    onChange={field.onChange}
                    options={[10, 30]}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="resolution"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Resolution</FormLabel>
                  <NumberSelect
                    value={field.value}
                    onChange={field.onChange}
                    options={[128, 256]}
                    format={(n) => `${n}×${n}`}
                  />
                  <FormDescription>
                    Defaults (2 cameras · 60 frames · 30 fps · 256×256) record a
                    small episode in a few seconds — good for a first run.
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
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Recording & uploading…" : "Record episode"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
