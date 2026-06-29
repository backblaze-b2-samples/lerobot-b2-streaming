export type FileStatus = "uploading" | "complete" | "error";

export interface FileMetadata {
  key: string;
  filename: string;
  folder: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
}

export interface FileMetadataDetail {
  filename: string;
  size_bytes: number;
  size_human: string;
  mime_type: string;
  extension: string;
  md5: string;
  sha256: string;
  uploaded_at: string;
  // Image-specific
  image_width: number | null;
  image_height: number | null;
  exif: Record<string, string> | null;
  // PDF-specific
  pdf_pages: number | null;
  pdf_author: string | null;
  pdf_title: string | null;
  // Audio/Video
  duration_seconds: number | null;
  codec: string | null;
  bitrate: number | null;
}

export interface FileUploadResponse {
  key: string;
  filename: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
  metadata: FileMetadataDetail | null;
}

export interface DailyUploadCount {
  date: string;
  uploads: number;
}

export interface UploadStats {
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
  total_downloads: number;
}

// --- LeRobot episodes + B2 streaming ---

export interface EpisodeCameraVideo {
  camera: string;
  key: string;
  size_bytes: number;
  size_human: string;
}

export interface Episode {
  episode_index: number;
  task: string;
  num_frames: number;
  fps: number;
  num_cameras: number;
  cameras: string[];
  resolution: number;
  dataset_from_index: number;
  dataset_to_index: number;
  size_bytes: number;
  size_human: string;
  prefix: string;
  created_at: string | null;
  videos: EpisodeCameraVideo[];
}

export interface EpisodeCreateRequest {
  task: string;
  num_cameras: number;
  num_frames: number;
  fps: number;
  resolution: number;
  // HuggingFace v3 dataset the real footage is drawn from (a curated preset or a
  // custom owner/name). Omit to use the server default.
  source_repo_id?: string;
}

export interface EpisodeUpdateRequest {
  task: string;
}

export interface EpisodeCreateResult {
  episode: Episode;
  bytes_uploaded: number;
  bytes_uploaded_human: string;
  object_count: number;
  device: string;
}

export interface EpisodeFormOptions {
  tasks: string[];
  num_cameras: number[];
  num_frames: number[];
  fps: number[];
  resolutions: number[];
  sources: string[];
  default_task: string;
  default_num_cameras: number;
  default_num_frames: number;
  default_fps: number;
  default_resolution: number;
  default_source: string;
}

export interface WorkerStreamStats {
  worker_id: number;
  task: string | null;
  episodes_streamed: number;
  frames_decoded: number;
  bytes_fetched: number;
  bytes_fetched_human: string;
  throughput_frames_per_s: number;
  elapsed_s: number;
}

export interface StreamRunStats {
  workers: number;
  episodes_streamed: number;
  frames_decoded: number;
  bytes_fetched: number;
  bytes_fetched_human: string;
  total_dataset_bytes: number;
  total_dataset_bytes_human: string;
  fetch_ratio: number;
  elapsed_s: number;
  throughput_frames_per_s: number;
  train_loss_start: number | null;
  train_loss_end: number | null;
  device: string;
  per_worker: WorkerStreamStats[];
}

export interface StreamRunRequest {
  episode_index?: number | null;
  task?: string | null;
  workers: number;
  max_frames?: number;
}

export interface DatasetStats {
  total_episodes: number;
  total_frames: number;
  total_cameras: number;
  total_tasks: number;
  total_dataset_bytes: number;
  total_dataset_bytes_human: string;
  tasks: string[];
}

export interface DailyEpisodeCount {
  date: string;
  episodes: number;
}
