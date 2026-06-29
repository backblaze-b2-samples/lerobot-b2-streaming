"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useDeleteEpisode } from "@/lib/queries";
import { ApiError } from "@/lib/api-client";

interface Props {
  index: number;
  children: ReactNode;
  /** When set, navigate here after a successful delete (e.g. from detail page). */
  redirectTo?: string;
}

export function DeleteEpisodeButton({ index, children, redirectTo }: Props) {
  const router = useRouter();
  const del = useDeleteEpisode();
  const label = `ep_${String(index).padStart(6, "0")}`;

  const onConfirm = async () => {
    try {
      const res = await del.mutateAsync(index);
      toast.success(`Deleted ${label}`, {
        description: `${res.objects_removed} objects removed from B2 (prefix-scoped).`,
      });
      if (redirectTo) router.push(redirectTo);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to delete episode";
      toast.error("Delete failed", { description: msg });
    }
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{children}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {label}?</AlertDialogTitle>
          <AlertDialogDescription>
            This removes every shard and metadata object for this episode from
            Backblaze B2. The delete is scoped to{" "}
            <code className="font-mono text-xs">{label}</code>&apos;s prefix only —
            no other episode is touched. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={del.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={del.isPending}
            className="bg-destructive text-white hover:bg-destructive/90"
          >
            {del.isPending ? "Deleting…" : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
