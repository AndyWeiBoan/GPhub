const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Category =
  | "research_paper"
  | "news_article"
  | "blog_post"
  | "community"
  | "product_launch"
  | "github_project";

export type GithubSubcat = "llm" | "agent" | "context" | "vision" | "tool";

export interface Item {
  id: string;
  title: string;
  url: string;
  author: string | null;
  published_at: string | null;
  fetched_at: string;
  summary: string | null;
  raw_content: string | null;
  thumbnail_url: string | null;
  thumbnail_attribution: string | null;   // "Photo by X on Pexels|<url>"
  source_name: string | null;
  category: Category | null;
  github_subcat: GithubSubcat | null;
  github_stars: number | null;
  impact_score: number;
  credibility_score: number;
  novelty_score: number;
  total_score: number;
  is_summarized: boolean;
  ai_comment: string | null;
  ai_comment_model: string | null;
}

export interface ItemListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Item[];
}

export interface CategoryRank {
  category: string;
  items: Item[];
}

export interface TrendingItem extends Item {
  trending_score: number;
  cross_source_count: number;
}

export interface CategoryTrend {
  category: string;
  count_7d: number;
  count_24h: number;
  pct_of_total: number;
}

export interface TrendingResponse {
  items: TrendingItem[];
  category_trends: CategoryTrend[];
  window_hours: number;
}

export interface TopicLeadItem {
  id: string;
  title: string;
  url: string;
  summary: string | null;
  raw_content: string | null;
  thumbnail_url: string | null;
  thumbnail_attribution: string | null;
  source_name: string | null;
  category: Category | null;
  published_at: string | null;
  fetched_at: string;
  trending_score: number;
  ai_comment: string | null;
  ai_comment_model: string | null;
}

export interface Topic {
  label: string;
  count: number;
  lead_item: TopicLeadItem;
}

export interface TopicsResponse {
  topics: Topic[];
  window_hours: number;
}

export async function fetchTopics(top_k = 6, window_hours = 168): Promise<TopicsResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/topics?top_k=${top_k}&window_hours=${window_hours}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error("Failed to fetch topics");
  return res.json();
}

export interface Stats {
  total_items: number;
  total_sources: number;
  last_crawl: string | null;
  categories: Record<string, number>;
}

export async function fetchItems(params: {
  page?: number;
  page_size?: number;
  category?: string;
  github_subcat?: string;
  min_score?: number;
  sort_by?: string;
  q?: string;
  source_name?: string;
}): Promise<ItemListResponse> {
  const url = new URL(`${API_BASE}/api/v1/items`);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch items");
  return res.json();
}

export async function fetchSources(category?: string): Promise<string[]> {
  const url = new URL(`${API_BASE}/api/v1/sources`);
  if (category) url.searchParams.set("category", category);
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json();
  return data.sources ?? [];
}

export async function fetchRanking(top_n = 5): Promise<CategoryRank[]> {
  const res = await fetch(`${API_BASE}/api/v1/ranking?top_n=${top_n}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch ranking");
  return res.json();
}

export async function fetchTrending(
  top_n = 10,
  window_hours = 168,
  options: { exclude?: string; include?: string } = {}
): Promise<TrendingResponse> {
  const url = new URL(`${API_BASE}/api/v1/trending`);
  url.searchParams.set("top_n", String(top_n));
  url.searchParams.set("window_hours", String(window_hours));
  if (options.exclude) url.searchParams.set("exclude", options.exclude);
  if (options.include) url.searchParams.set("include", options.include);
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch trending");
  return res.json();
}

export interface GithubRisingItem {
  id: string;
  title: string;
  url: string;
  summary: string | null;
  thumbnail_url: string | null;
  source_name: string | null;
  github_subcat: GithubSubcat | null;
  github_stars: number | null;
  star_delta: number;
  star_delta_pct: number;
  total_score: number;
}

export interface GithubRisingResponse {
  items: GithubRisingItem[];
  window_hours: number;
}

export async function fetchGithubRising(
  top_n = 10,
  window_hours = 48
): Promise<GithubRisingResponse> {
  const url = new URL(`${API_BASE}/api/v1/github-rising`);
  url.searchParams.set("top_n", String(top_n));
  url.searchParams.set("window_hours", String(window_hours));
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch github rising");
  return res.json();
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/api/v1/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export interface DigestItem {
  id: string;
  title: string;
  url: string;
  ai_comment: string | null;
  ai_comment_model: string | null;
}

export interface Digest {
  title: string;
  analysis: string;
  item_ids: string[];
  items: DigestItem[];
}

export interface WeeklyDigestResponse {
  week_label: string;
  digests: Digest[];
}

export async function fetchWeeklyDigest(): Promise<WeeklyDigestResponse> {
  const res = await fetch(`${API_BASE}/api/v1/weekly-digest`, { cache: "no-store" });
  if (!res.ok) return { week_label: "", digests: [] };
  return res.json();
}
