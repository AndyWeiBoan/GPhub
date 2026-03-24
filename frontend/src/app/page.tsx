import { fetchTrending, fetchTopics } from "@/lib/api";
import type { TrendingItem, Topic, TopicLeadItem } from "@/lib/api";
import CategoryPill from "@/components/CategoryPill";
import Thumb from "@/components/Thumb";
import PhotoCredit from "@/components/PhotoCredit";

// ── helpers ───────────────────────────────────────────────────────────────────

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const h = Math.floor((Date.now() - new Date(dateStr).getTime()) / 3_600_000);
  if (h < 1) return "just now";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function cleanContent(raw: string): string {
  return raw
    .replace(/<[^>]+>/g, "")                              // strip HTML tags
    .replace(/arXiv:\S+\s*/gi, "")                        // remove arXiv IDs
    .replace(/Announce Type:\s*\w+\s*/gi, "")             // remove "Announce Type: new"
    .replace(/^Abstract:\s*/i, "")                        // remove "Abstract:" prefix
    .replace(/&#\d+;|&amp;|&lt;|&gt;|&quot;|&apos;/g, (m) =>  // decode HTML entities
      ({ "&#8217;": "'", "&#8230;": "…", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'" }[m] ?? "")
    )
    .replace(/\s+/g, " ")
    .trim();
}

function excerpt(item: TrendingItem, maxLen = 160): string {
  const src = item.summary || item.raw_content || "";
  const clean = cleanContent(src);
  return clean.length > maxLen ? clean.slice(0, maxLen - 1) + "…" : clean;
}

const CAT_EMOJI: Record<string, string> = {
  research_paper: "🔬", news_article: "📡", blog_post: "✍️",
  tool_release: "🛠", product_launch: "🚀", github_project: "⬡",
};

// Does this item have a real editorial image (not a favicon / icon)?
function hasRealImage(item: TrendingItem): boolean {
  const t = item.thumbnail_url;
  if (!t) return false;
  if (t.includes("favicon") || t.includes(".ico")) return false;
  return true;
}

// Gradient fallbacks per category — used when no real image is available
const CAT_GRADIENT: Record<string, string> = {
  research_paper: "from-violet-950 via-indigo-950 to-[#0f1117]",
  news_article:   "from-blue-950 via-sky-950 to-[#0f1117]",
  blog_post:      "from-sky-950 via-cyan-950 to-[#0f1117]",
  tool_release:   "from-orange-950 via-amber-950 to-[#0f1117]",
  product_launch: "from-pink-950 via-rose-950 to-[#0f1117]",
  github_project: "from-emerald-950 via-teal-950 to-[#0f1117]",
};

// ── Reusable image block (for center hero) ───────────────────────────────────

function HeroImage({ item }: { item: TrendingItem }) {
  const realImg  = hasRealImage(item);
  const gradient = CAT_GRADIENT[item.category ?? ""] ?? "from-gray-900 to-[#0f1117]";
  if (realImg) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={item.thumbnail_url!} alt="" className="h-56 w-full object-cover" />;
  }
  return (
    <span className={`flex h-56 w-full items-center justify-center bg-gradient-to-br ${gradient}`}>
      <span className="text-6xl opacity-40 select-none">{CAT_EMOJI[item.category ?? ""] ?? "✦"}</span>
    </span>
  );
}

// ── Hero (image on top, full text below — no overlay) ────────────────────────

function HeroCard({ item }: { item: TrendingItem }) {
  const desc     = excerpt(item, 200);
  const time     = timeAgo(item.published_at ?? item.fetched_at);
  const realImg  = hasRealImage(item);
  const gradient = CAT_GRADIENT[item.category ?? ""] ?? "from-gray-900 to-[#0f1117]";

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block overflow-hidden rounded-2xl bg-[#161b27] border border-white/[0.06] transition hover:border-white/15"
    >
      {/* ── Image zone ── */}
      <span className="relative block overflow-hidden">
        {realImg ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumbnail_url!}
            alt=""
            className="h-64 w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <span className={`flex h-64 w-full items-center justify-center bg-gradient-to-br ${gradient}`}>
            <span className="text-8xl opacity-40 select-none">
              {CAT_EMOJI[item.category ?? ""] ?? "✦"}
            </span>
          </span>
        )}
        <span className="absolute bottom-0 left-0 right-0 block h-8 bg-gradient-to-t from-[#161b27] to-transparent" />
        <PhotoCredit attribution={item.thumbnail_attribution} />
      </span>

      {/* ── Text zone ── */}
      <span className="block px-5 pb-5 pt-4">
        <span className="mb-2.5 flex flex-wrap items-center gap-2">
          <CategoryPill category={item.category} />
          {item.source_name && (
            <span className="text-xs font-medium text-gray-400">{item.source_name}</span>
          )}
          {item.cross_source_count > 1 && (
            <span className="rounded-full bg-orange-500/20 px-2 py-0.5 text-[11px] font-semibold text-orange-400">
              🔥 {item.cross_source_count} sources
            </span>
          )}
          <span className="ml-auto text-[11px] text-gray-600">{time}</span>
        </span>

        <h2 className="text-[1.1rem] font-bold leading-snug text-gray-50 transition-colors group-hover:text-white">
          {item.title}
        </h2>

        {desc && (
          <p className="mt-2 text-sm leading-relaxed text-gray-400 line-clamp-3">
            {desc}
          </p>
        )}
      </span>
    </a>
  );
}

// ── Medium card (image top, text below) ──────────────────────────────────────

function MediumCard({ item }: { item: TrendingItem }) {
  const desc     = excerpt(item, 80);
  const realImg  = hasRealImage(item);
  const gradient = CAT_GRADIENT[item.category ?? ""] ?? "from-gray-900 to-[#0f1117]";
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col overflow-hidden rounded-xl border border-white/[0.05] bg-[#161b27] transition hover:border-white/10"
    >
      <span className="relative block">
        {realImg ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumbnail_url!}
            alt=""
            className="h-24 w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <span className={`flex h-24 w-full items-center justify-center bg-gradient-to-br ${gradient}`}>
            <span className="text-5xl opacity-40 select-none">
              {CAT_EMOJI[item.category ?? ""] ?? "✦"}
            </span>
          </span>
        )}
        <PhotoCredit attribution={item.thumbnail_attribution} />
      </span>
      <span className="flex flex-1 flex-col gap-1.5 p-3">
        <span className="flex items-center gap-1.5">
          <CategoryPill category={item.category} />
          <span className="text-[10px] text-gray-600">{timeAgo(item.published_at ?? item.fetched_at)}</span>
        </span>
        <h3 className="line-clamp-2 text-sm font-bold leading-snug text-gray-100 group-hover:text-white">
          {item.title}
        </h3>
        {desc && (
          <p className="line-clamp-2 text-[11px] leading-relaxed text-gray-500">{desc}</p>
        )}
        {item.source_name && (
          <p className="mt-auto text-[10px] text-gray-600">{item.source_name}</p>
        )}
      </span>
    </a>
  );
}

// ── Sidebar row (text only) ───────────────────────────────────────────────────

function SidebarRow({ item, rank }: { item: TrendingItem; rank: number }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex items-start gap-3 border-b border-white/[0.05] pb-3 last:border-0 last:pb-0"
    >
      <span className="mt-0.5 w-5 flex-shrink-0 text-right text-sm font-black text-gray-700">{rank}</span>
      <span className="min-w-0">
        <h4 className="text-sm font-semibold leading-snug text-gray-200 group-hover:text-white line-clamp-2 transition-colors">
          {item.title}
        </h4>
        <span className="mt-1 flex items-center gap-1.5">
          {item.source_name && <span className="text-[11px] text-gray-500">{item.source_name}</span>}
          <span className="text-[11px] text-gray-600">{timeAgo(item.published_at ?? item.fetched_at)}</span>
        </span>
      </span>
    </a>
  );
}

// ── Topic helpers ─────────────────────────────────────────────────────────────

function topicDesc(lead: TopicLeadItem, maxLen = 160): string {
  const src = lead.summary || lead.raw_content || "";
  const clean = src
    .replace(/<[^>]+>/g, "")
    .replace(/arXiv:\S+/gi, "")
    .replace(/Announce Type:\s*\w+\.?\s*/gi, "")
    .replace(/^Abstract:\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();
  return clean.length > maxLen ? clean.slice(0, maxLen - 1) + "…" : clean;
}

function topicHasRealImg(lead: TopicLeadItem): boolean {
  return !!(lead.thumbnail_url && !lead.thumbnail_url.includes("favicon") && !lead.thumbnail_url.includes(".ico"));
}

// ── #1 大 Hero（左半，全高，大圖＋疊加文字）────────────────────────────────────

function TopicMainHero({ topic, rank }: { topic: Topic; rank: number }) {
  const lead    = topic.lead_item;
  const realImg = topicHasRealImg(lead);
  const gradient = CAT_GRADIENT[lead.category ?? ""] ?? "from-gray-900 to-[#0f1117]";
  const desc    = topicDesc(lead, 240);

  return (
    <a
      href={lead.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative flex h-full min-h-[420px] overflow-hidden rounded-xl border border-white/[0.06] bg-[#161b27] transition hover:border-white/15"
    >
      {/* Background image or gradient */}
      {realImg ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={lead.thumbnail_url!}
          alt=""
          className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
        />
      ) : (
        <span className={`absolute inset-0 bg-gradient-to-br ${gradient}`}>
          <span className="absolute inset-0 flex items-center justify-center">
            <span className="text-[10rem] opacity-10 select-none">{CAT_EMOJI[lead.category ?? ""] ?? "✦"}</span>
          </span>
        </span>
      )}
      {/* Gradient overlay */}
      <span className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />

      {/* Text */}
      <span className="relative mt-auto w-full p-5">
        <span className="mb-3 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-orange-500/25 px-2.5 py-0.5 text-[11px] font-bold text-orange-400">
            #{rank} {topic.label}
          </span>
          <span className="rounded-full bg-black/50 px-2 py-0.5 text-[10px] text-gray-300 backdrop-blur-sm">
            {topic.count} articles this week
          </span>
        </span>
        <h2 className="text-2xl font-extrabold leading-snug text-white group-hover:text-gray-100 line-clamp-3 mb-2">
          {lead.title}
        </h2>
        {desc && (
          <p className="text-sm leading-relaxed text-gray-300/80 line-clamp-2 mb-3">
            {desc}
          </p>
        )}
        <span className="flex items-center gap-2">
          <CategoryPill category={lead.category} />
          {lead.source_name && (
            <span className="text-[11px] text-gray-400">{lead.source_name}</span>
          )}
        </span>
      </span>
      <PhotoCredit attribution={lead.thumbnail_attribution} />
    </a>
  );
}

// ── 小圖卡（#2 #3 #5 #6）────────────────────────────────────────────────────────

function TopicSmallCard({ topic, rank }: { topic: Topic; rank: number }) {
  const lead    = topic.lead_item;
  const realImg = topicHasRealImg(lead);
  const gradient = CAT_GRADIENT[lead.category ?? ""] ?? "from-gray-900 to-[#0f1117]";

  return (
    <a
      href={lead.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative flex h-full min-h-[140px] overflow-hidden rounded-xl border border-white/[0.06] bg-[#161b27] transition hover:border-white/15"
    >
      {realImg ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={lead.thumbnail_url!}
          alt=""
          className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
        />
      ) : (
        <span className={`absolute inset-0 bg-gradient-to-br ${gradient}`} />
      )}
      <span className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />

      <span className="relative mt-auto w-full p-3">
        <span className="mb-1.5 flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-orange-400">#{rank}</span>
          <span className="text-[10px] font-semibold text-gray-300">{topic.label}</span>
          <span className="ml-auto text-[9px] text-gray-500">{topic.count} articles</span>
        </span>
        <h3 className="text-sm font-bold leading-snug text-white group-hover:text-gray-100 line-clamp-2">
          {lead.title}
        </h3>
        {lead.source_name && (
          <p className="mt-1 text-[10px] text-gray-500">{lead.source_name}</p>
        )}
      </span>
      <PhotoCredit attribution={lead.thumbnail_attribution} />
    </a>
  );
}

// ── 橫寬卡（#4）──────────────────────────────────────────────────────────────────

function TopicWideCard({ topic, rank }: { topic: Topic; rank: number }) {
  const lead    = topic.lead_item;
  const realImg = topicHasRealImg(lead);
  const gradient = CAT_GRADIENT[lead.category ?? ""] ?? "from-gray-900 to-[#0f1117]";
  const desc    = topicDesc(lead, 130);

  return (
    <a
      href={lead.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative flex h-full min-h-[140px] overflow-hidden rounded-xl border border-white/[0.06] bg-[#161b27] transition hover:border-white/15"
    >
      {realImg ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={lead.thumbnail_url!}
          alt=""
          className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
        />
      ) : (
        <span className={`absolute inset-0 bg-gradient-to-br ${gradient}`} />
      )}
      <span className="absolute inset-0 bg-gradient-to-r from-black/90 via-black/50 to-black/20" />

      <span className="relative mt-auto w-full p-3">
        <span className="mb-1.5 flex items-center gap-2">
          <span className="rounded-full bg-orange-500/20 px-2 py-0.5 text-[10px] font-bold text-orange-400">
            #{rank} {topic.label}
          </span>
          <span className="text-[9px] text-gray-500">{topic.count} articles this week</span>
        </span>
        <h3 className="text-sm font-bold leading-snug text-white group-hover:text-gray-100 line-clamp-1">
          {lead.title}
        </h3>
        {desc && (
          <p className="mt-0.5 text-[11px] text-gray-400 line-clamp-1">{desc}</p>
        )}
      </span>
      <PhotoCredit attribution={lead.thumbnail_attribution} />
    </a>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const LATEST_CATEGORIES: { key: string; label: string }[] = [
  { key: "blog_post",      label: "Blog" },
  { key: "github_project", label: "GitHub" },
  { key: "product_launch", label: "Products" },
  { key: "news_article",   label: "News" },
];

export default async function HomePage() {
  const topicsData = await fetchTopics(6, 168);
  const topics = topicsData.topics;

  // Collect IDs already shown in Hot Topics section
  const hotTopicIds = topics.map((t) => t.lead_item.id).join(",");

  // Fetch row-3 MediumCards and per-category (fetch more to survive dedup)
  const [allData, ...categoryResults] = await Promise.all([
    fetchTrending(3, 168),
    ...LATEST_CATEGORIES.map(({ key }) =>
      fetchTrending(20, 168, { include: key, exclude: hotTopicIds || undefined })
    ),
  ]);

  const gridItems = allData.items.slice(0, 3);

  // Build full exclusion list: Hot Topics lead items + row-3 MediumCards
  const excludedIds = new Set([
    ...topics.map((t) => t.lead_item.id),
    ...gridItems.map((i) => i.id),
  ]);

  // Normalize URL: strip query string so Medium cross-tag dupes are caught
  function normalizeUrl(url: string): string {
    try { return new URL(url).origin + new URL(url).pathname; }
    catch { return url; }
  }

  // Deduplicate by normalized URL AND title (covers cross-source/cross-tag dupes)
  function dedupeItems(items: typeof gridItems, limit: number) {
    const seenUrls = new Set<string>();
    const seenTitles = new Set<string>();
    const result = [];
    for (const item of items) {
      if (excludedIds.has(item.id)) continue;
      const urlKey = normalizeUrl(item.url);
      const titleKey = item.title.trim().toLowerCase();
      if (seenUrls.has(urlKey) || seenTitles.has(titleKey)) continue;
      seenUrls.add(urlKey);
      seenTitles.add(titleKey);
      result.push(item);
      if (result.length >= limit) break;
    }
    return result;
  }

  return (
    <main className="mx-auto max-w-6xl px-4 pb-20 pt-6">

      {/* ── Header ── */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-extrabold text-white">This Week in AI</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Top trending topics · past 7 days
          </p>
        </div>
        <a href="/browse" className="text-xs text-gray-500 transition hover:text-white">Browse all →</a>
      </div>

      {topics.length === 0 ? (
        <div className="rounded-2xl border border-white/[0.06] py-24 text-center">
          <p className="text-5xl mb-4">📭</p>
          <p className="text-sm text-gray-500 mb-2">No data yet.</p>
          <code className="text-xs text-violet-400">curl -X POST http://localhost:8000/api/v1/trigger-crawl</code>
        </div>
      ) : (
        <div className="space-y-10">

          {/* ══ TOP: Hot Topics this week ════════════════════════════════════ */}
          <section>
            <p className="mb-4 text-[10px] font-bold uppercase tracking-widest text-gray-500">
              🔥 Hot Topics This Week
            </p>

            {/*
              不規則 grid 排版（12欄）：
              ┌──────────────────────┬──────────┬──────────┐
              │                      │   #2     │   #3     │
              │         #1           ├──────────┴──────────┤
              │       左 6 欄         │         #4          │
              │                      ├──────────┬──────────┤
              ├──────────────────────┤   #5     │   #6     │
              │  #7  │  #8  │  #9   │          │          │
              └──────┴───────┴───────┴──────────┴──────────┘
            */}
            {/*
              實際資料 6 筆，對應排版：
              col 1-6  row 1-2  → #1 主 hero
              col 7-9  row 1    → #2 小卡
              col 10-12 row 1   → #3 小卡
              col 7-12  row 2   → #4 寬卡
              col 1-6   row 3   → 左下：MediumCard grid（由 gridItems 提供）
              col 7-9   row 3   → #5 小卡
              col 10-12 row 3   → #6 小卡
            */}
            <div className="grid grid-cols-12 gap-3" style={{ gridTemplateRows: "1fr 1fr auto" }}>

              {/* #1 — 左 6 欄，橫跨兩行 */}
              <div className="col-span-6 row-span-2" style={{ minHeight: "320px" }}>
                {topics[0] && <TopicMainHero topic={topics[0]} rank={1} />}
              </div>

              {/* #2 — 右上，3 欄 */}
              <div className="col-span-3">
                {topics[1] && <TopicSmallCard topic={topics[1]} rank={2} />}
              </div>

              {/* #3 — 右上，3 欄 */}
              <div className="col-span-3">
                {topics[2] && <TopicSmallCard topic={topics[2]} rank={3} />}
              </div>

              {/* #4 — 右中，橫跨 6 欄 */}
              <div className="col-span-6">
                {topics[3] && <TopicWideCard topic={topics[3]} rank={4} />}
              </div>

              {/* Row 3 左下：3 個 MediumCard（取 gridItems 前 3 筆） */}
              <div className="col-span-6">
                <div className="grid grid-cols-3 gap-3 h-full">
                  {gridItems.slice(0, 3).map((item) => (
                    <MediumCard key={item.id} item={item} />
                  ))}
                </div>
              </div>

              {/* #5 — 右下，3 欄 */}
              <div className="col-span-3">
                {topics[4] && <TopicSmallCard topic={topics[4]} rank={5} />}
              </div>

              {/* #6 — 右下，3 欄 */}
              <div className="col-span-3">
                {topics[5] && <TopicSmallCard topic={topics[5]} rank={6} />}
              </div>

            </div>
          </section>

          {/* ══ BOTTOM: Latest Items — 每排一種分類的 top 4 ════════════════ */}
          <div className="space-y-8">
            {LATEST_CATEGORIES.map(({ key, label }, i) => {
              const items = dedupeItems(categoryResults[i]?.items ?? [], 4);
              if (items.length === 0) return null;
              return (
                <section key={key}>
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                      Latest · {label}
                    </p>
                    <a href={`/browse?category=${key}`} className="text-xs text-gray-500 transition hover:text-white">
                      See all →
                    </a>
                  </div>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    {items.map((item) => <MediumCard key={item.id} item={item} />)}
                  </div>
                </section>
              );
            })}
          </div>

        </div>
      )}
    </main>
  );
}
