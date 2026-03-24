import { Suspense } from "react";
import { fetchItems, fetchSources } from "@/lib/api";
import BrowseList from "@/components/BrowseList";
import SearchBar from "@/components/SearchBar";
import { GITHUB_SUBCATS, type GithubSubcat } from "@/lib/githubSubcat";

const CATEGORIES = [
  { value: "", label: "All" },
  { value: "research_paper", label: "Research" },
  { value: "news_article", label: "News" },
  { value: "blog_post", label: "Blog" },
  { value: "community", label: "社群" },
  { value: "product_launch", label: "Products" },
  { value: "github_project", label: "GitHub" },
];

const SORTS = [
  { value: "total_score", label: "Top Score" },
  { value: "published_at", label: "Newest" },
  { value: "fetched_at", label: "Recently Fetched" },
];

const PAGE_SIZE = 30;

interface PageProps {
  searchParams: {
    page?: string;
    category?: string;
    sort_by?: string;
    github_sub?: string;
    q?: string;
    source_name?: string;
  };
}

export default async function BrowsePage({ searchParams }: PageProps) {
  const page       = Number(searchParams.page ?? 1);
  const category   = searchParams.category ?? "";
  const sort_by    = searchParams.sort_by ?? "total_score";
  const githubSub  = (searchParams.github_sub ?? "") as GithubSubcat | "";
  const q          = searchParams.q ?? "";
  const sourceName = searchParams.source_name ?? "";

  // Pass github_subcat directly to the API — no client-side keyword matching
  const [sources, data] = await Promise.all([
    fetchSources(category || undefined),
    fetchItems({
      page,
      page_size: PAGE_SIZE,
      category: category || undefined,
      github_subcat: category === "github_project" && githubSub ? githubSub : undefined,
      sort_by,
      q: q || undefined,
      source_name: sourceName || undefined,
    }),
  ]);

  const totalPages = Math.ceil(data.total / PAGE_SIZE);

  function buildHref(overrides: Record<string, string | number>) {
    const base: Record<string, string> = { page: String(page), sort_by };
    if (category)   base.category    = category;
    if (githubSub)  base.github_sub  = githubSub;
    if (q)          base.q           = q;
    if (sourceName) base.source_name = sourceName;
    const merged = {
      ...base,
      ...Object.fromEntries(Object.entries(overrides).map(([k, v]) => [k, String(v)])),
    };
    Object.keys(merged).forEach((k) => { if (!merged[k]) delete merged[k]; });
    return `/browse?${new URLSearchParams(merged).toString()}`;
  }

  return (
    <div className="mx-auto max-w-6xl flex flex-col px-4" style={{ height: "calc(100vh - 49px)" }}>

      {/* ── Fixed header area ── */}
      <div className="flex-shrink-0 pt-6 pb-3 space-y-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Browse All</h1>
          <p className="mt-0.5 text-sm text-gray-500">{data.total.toLocaleString()} items</p>
        </div>

        {/* Category tabs + Sort */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((c) => (
              <a
                key={c.value}
                href={buildHref({ category: c.value, page: 1, github_sub: "", q: "", source_name: "" })}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  category === c.value
                    ? "border-violet-500 bg-violet-500/20 text-violet-300"
                    : "border-white/10 bg-white/[0.03] text-gray-400 hover:border-white/20 hover:text-white"
                }`}
              >
                {c.label}
              </a>
            ))}
          </div>
          <div className="ml-auto flex gap-2">
            {SORTS.map((s) => (
              <a
                key={s.value}
                href={buildHref({ sort_by: s.value, page: 1 })}
                className={`rounded-lg border px-3 py-1 text-xs transition ${
                  sort_by === s.value
                    ? "border-violet-500 bg-violet-500/20 text-violet-300"
                    : "border-white/10 bg-white/[0.03] text-gray-400 hover:text-white"
                }`}
              >
                {s.label}
              </a>
            ))}
          </div>
        </div>

        {/* Search + Source + Pagination */}
        <div className="flex items-center gap-2 mt-2">
          <Suspense>
            <SearchBar
              sources={sources}
              initialQ={q}
              initialSource={sourceName}
              basePath="/browse"
            />
          </Suspense>

          {totalPages > 1 && (
            <div className="flex items-center gap-1 flex-shrink-0">
              <a
                href={page > 1 ? buildHref({ page: page - 1 }) : "#"}
                aria-disabled={page <= 1}
                className={`rounded-lg border px-3 py-1.5 text-sm transition ${
                  page > 1
                    ? "border-white/10 bg-white/[0.03] text-gray-300 hover:border-white/20 hover:text-white"
                    : "border-transparent bg-transparent text-transparent pointer-events-none"
                }`}
              >
                ←
              </a>
              <span className="px-2 text-sm text-gray-500 whitespace-nowrap">{page} / {totalPages}</span>
              {page < totalPages ? (
                <a
                  href={buildHref({ page: page + 1 })}
                  className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-gray-300 transition hover:border-white/20 hover:text-white"
                >
                  →
                </a>
              ) : (
                <span className="rounded-lg border border-transparent px-3 py-1.5 text-sm">→</span>
              )}
            </div>
          )}
        </div>

        {/* GitHub sub-tabs — shown only when GitHub category is selected */}
        {category === "github_project" && (
          <div className="flex gap-2 border-b border-white/[0.06] pb-3">
            {GITHUB_SUBCATS.map((sub) => (
              <a
                key={sub.value}
                href={buildHref({ github_sub: sub.value, page: 1 })}
                title={sub.desc}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  githubSub === sub.value
                    ? "border-emerald-500 bg-emerald-500/20 text-emerald-300"
                    : "border-white/10 bg-white/[0.03] text-gray-400 hover:border-white/20 hover:text-white"
                }`}
              >
                {sub.label}
              </a>
            ))}
          </div>
        )}
      </div>

      {/* ── Scrollable body: list (left) + preview (right) ── */}
      <div className="flex-1 overflow-hidden pb-4">
        <BrowseList
          items={data.items}
          pageOffset={(page - 1) * PAGE_SIZE}
        />
      </div>
    </div>
  );
}
