const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type SourceTier = "tier1" | "tier2" | "tier3";
export type ContentCategory =
  | "research_paper"
  | "news_article"
  | "blog_post"
  | "community"
  | "product_launch"
  | "github_project";

export const CATEGORY_LABELS: Record<ContentCategory, string> = {
  research_paper: "Research Paper",
  news_article: "News Article",
  blog_post: "Blog Post",
  community: "Community",
  product_launch: "Product Launch",
  github_project: "GitHub Project",
};

export const TIER_LABELS: Record<SourceTier, string> = {
  tier1: "Tier 1 (High)",
  tier2: "Tier 2 (Medium)",
  tier3: "Tier 3 (Low)",
};

export const CRAWLER_NAMES = ["rss", "github", "anthropic"] as const;
export type CrawlerName = (typeof CRAWLER_NAMES)[number];

export interface Source {
  id: string;
  name: string;
  url: string;
  tier: SourceTier;
  category: ContentCategory;
  is_active: boolean;
  created_at: string | null;
  item_count: number;
}

export interface SourceCreate {
  name: string;
  url: string;
  tier: SourceTier;
  category: ContentCategory;
  is_active?: boolean;
}

export interface SourceUpdate {
  name?: string;
  url?: string;
  tier?: SourceTier;
  category?: ContentCategory;
  is_active?: boolean;
}

export interface CrawlRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  items_fetched: number;
  items_new: number;
  status: string;
  errors: { crawler: string; error: string }[];
}

export interface AdminStats {
  total_items: number;
  total_sources: number;
  active_sources: number;
  last_crawl: string | null;
  categories: Record<string, number>;
  items_by_source: Record<string, number>;
}

// ── helpers ───────────────────────────────────────────────────────────────────

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api/v1/admin${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── job status ────────────────────────────────────────────────────────────────

export type JobPhase = "pending" | "running" | "done" | "error";

export interface JobStep {
  name: string;
  status: "pending" | "running" | "done" | "error";
  detail: string;
}

export interface Job {
  job_id: string;
  label: string;
  phase: JobPhase;
  steps: JobStep[];
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  result: Record<string, number> | null;
}

export const fetchJob = (jobId: string) => req<Job>(`/jobs/${jobId}`);
export const fetchJobs = (limit = 10) => req<Job[]>(`/jobs?limit=${limit}`);

// ── stats ─────────────────────────────────────────────────────────────────────

export const fetchAdminStats = () => req<AdminStats>("/stats");
export const fetchCrawlRuns = (limit = 20) =>
  req<CrawlRun[]>(`/crawl-runs?limit=${limit}`);

// ── crawl triggers ────────────────────────────────────────────────────────────

export const triggerCrawlAll = () =>
  req<{ job_id: string; message: string }>("/trigger-crawl", { method: "POST" });

export const triggerCrawlOne = (crawler: CrawlerName) =>
  req<{ job_id: string; message: string }>(`/trigger-crawl/${crawler}`, { method: "POST" });

export const triggerCrawlCategory = (category: ContentCategory) =>
  req<{ job_id: string; message: string; crawlers: string[] }>(
    `/trigger-crawl-category/${category}`,
    { method: "POST" }
  );

export const triggerRescore = () =>
  req<{ job_id: string; message: string }>("/trigger-rescore", { method: "POST" });

// ── sources ───────────────────────────────────────────────────────────────────

export const fetchSources = (params?: {
  category?: ContentCategory;
  is_active?: boolean;
}) => {
  const q = new URLSearchParams();
  if (params?.category) q.set("category", params.category);
  if (params?.is_active !== undefined) q.set("is_active", String(params.is_active));
  const qs = q.toString();
  return req<Source[]>(`/sources${qs ? `?${qs}` : ""}`);
};

export const createSource = (body: SourceCreate) =>
  req<Source>("/sources", { method: "POST", body: JSON.stringify(body) });

export const updateSource = (id: string, body: SourceUpdate) =>
  req<Source>(`/sources/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const deleteSource = (id: string) =>
  req<void>(`/sources/${id}`, { method: "DELETE" });

// ── data management ───────────────────────────────────────────────────────────

export const deleteItemsByCategory = (category: ContentCategory) =>
  req<{ deleted: number; category: string }>(
    `/items?category=${category}`,
    { method: "DELETE" }
  );
