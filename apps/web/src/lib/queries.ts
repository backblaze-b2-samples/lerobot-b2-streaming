"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  createEpisode,
  deleteEpisode,
  deleteFile,
  getDatasetStats,
  getEpisode,
  getEpisodeOptions,
  getEpisodes,
  getFiles,
  getFileStats,
  getIngestActivity,
  getPreviewUrl,
  getUploadActivity,
  relabelEpisode,
  runStream,
} from "@/lib/api-client";
import type {
  EpisodeCreateRequest,
  FileMetadata,
} from "@lerobot-b2-streaming/shared";

// Single source of truth for query keys. Keep these tightly scoped so that
// invalidating "files" doesn't blow away unrelated caches, and so an IDE
// "find usages" of `qk.files` reveals every consumer.
export const qk = {
  all: ["b2"] as const,
  files: (prefix?: string, limit?: number) =>
    [...qk.all, "files", prefix ?? "", limit ?? 100] as const,
  stats: () => [...qk.all, "stats"] as const,
  uploadActivity: (days: number) =>
    [...qk.all, "stats", "activity", days] as const,
  preview: (key: string) => [...qk.all, "preview", key] as const,
  episodes: (task?: string) => [...qk.all, "episodes", task ?? ""] as const,
  episode: (index: number) => [...qk.all, "episode", index] as const,
  episodeOptions: () => [...qk.all, "episode-options"] as const,
  datasetStats: () => [...qk.all, "dataset-stats"] as const,
  ingestActivity: (days: number) =>
    [...qk.all, "ingest-activity", days] as const,
};

export function useFiles(prefix = "", limit = 100) {
  return useQuery<FileMetadata[], ApiError>({
    queryKey: qk.files(prefix, limit),
    queryFn: () => getFiles(prefix, limit),
  });
}

export function useFileStats() {
  return useQuery({
    queryKey: qk.stats(),
    queryFn: getFileStats,
  });
}

export function useUploadActivity(days = 7) {
  return useQuery({
    queryKey: qk.uploadActivity(days),
    queryFn: () => getUploadActivity(days),
  });
}

// Presigned preview URL — only fetched when `enabled` is true (e.g., when
// the dialog opens for a specific file). Kept short-lived (60s) because
// the URL itself has a presigned expiry and is cheap to regenerate.
export function usePreviewUrl(key: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(key ?? ""),
    queryFn: () => getPreviewUrl(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileKey: string) => deleteFile(fileKey),
    // After delete, blow away every cached file list + stats. Cheap and
    // correct — the dashboard re-fetches lazily as components remount.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}

// --- LeRobot episodes + B2 streaming ---

export function useEpisodes(task?: string) {
  return useQuery({
    queryKey: qk.episodes(task),
    queryFn: () => getEpisodes(task),
  });
}

export function useEpisode(index: number | undefined) {
  return useQuery({
    queryKey: qk.episode(index ?? -1),
    queryFn: () => getEpisode(index as number),
    enabled: index !== undefined && index >= 0,
  });
}

export function useEpisodeOptions() {
  return useQuery({
    queryKey: qk.episodeOptions(),
    queryFn: getEpisodeOptions,
    staleTime: Infinity,
  });
}

export function useDatasetStats() {
  return useQuery({
    queryKey: qk.datasetStats(),
    queryFn: getDatasetStats,
  });
}

export function useIngestActivity(days = 7) {
  return useQuery({
    queryKey: qk.ingestActivity(days),
    queryFn: () => getIngestActivity(days),
  });
}

export function useCreateEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: EpisodeCreateRequest) => createEpisode(req),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.all }),
  });
}

export function useRelabelEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ index, task }: { index: number; task: string }) =>
      relabelEpisode(index, { task }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.all }),
  });
}

export function useDeleteEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (index: number) => deleteEpisode(index),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.all }),
  });
}

export function useRunStream() {
  return useMutation({
    mutationFn: runStream,
  });
}
