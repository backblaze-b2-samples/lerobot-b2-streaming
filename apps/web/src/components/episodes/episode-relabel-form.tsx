"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRelabelEpisode } from "@/lib/queries";
import { ApiError } from "@/lib/api-client";

const PRESET_TASKS = [
  "Pick up the cube",
  "Stack blocks",
  "Open the drawer",
  "Push the button",
];

interface Props {
  index: number;
  currentTask: string;
}

/** Edit verb — relabel the episode's task annotation. Pre-filled with the
 * real task; the selector rule applies to edit too. No default hint (editing
 * a real resource). */
export function EpisodeRelabelForm({ index, currentTask }: Props) {
  const [task, setTask] = useState(currentTask);
  const relabel = useRelabelEpisode();
  const dirty = task !== currentTask;

  const onSave = async () => {
    try {
      await relabel.mutateAsync({ index, task });
      toast.success("Task relabeled", {
        description: `ep_${String(index).padStart(6, "0")} is now "${task}". Metadata updated in B2.`,
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to relabel episode";
      toast.error("Relabel failed", { description: msg });
    }
  };

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">Task label</label>
        <Select value={task} onValueChange={setTask}>
          <SelectTrigger className="w-72">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRESET_TASKS.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button onClick={onSave} disabled={!dirty || relabel.isPending}>
        {relabel.isPending ? "Saving…" : "Save label"}
      </Button>
    </div>
  );
}
