import type { CategoryRank } from "@/lib/api";
import ItemRow from "./ItemRow";
import CategoryPill from "./CategoryPill";

const SECTION_META: Record<string, { emoji: string; label: string; desc: string }> = {
  research_paper:  { emoji: "🔬", label: "Research Papers",   desc: "Top papers from arXiv and academia" },
  news_article:    { emoji: "📡", label: "AI News",           desc: "Breaking news from top AI publications" },
  blog_post:       { emoji: "✍️",  label: "Blog Posts",       desc: "Insights from AI practitioners" },
  tool_release:    { emoji: "🛠",  label: "Tools",            desc: "New AI tools and releases" },
  product_launch:  { emoji: "🚀", label: "Product Launches", desc: "New products from Product Hunt and beyond" },
  github_project:  { emoji: "⬡",  label: "GitHub Trending",  desc: "Hottest AI repositories today" },
};

export default function CategorySection({ data }: { data: CategoryRank }) {
  const meta = SECTION_META[data.category] ?? { emoji: "•", label: data.category, desc: "" };

  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
      {/* Section header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">{meta.emoji}</span>
          <div>
            <h2 className="text-sm font-bold text-white">{meta.label}</h2>
            <p className="text-xs text-gray-500">{meta.desc}</p>
          </div>
        </div>
        <a
          href={`/browse?category=${data.category}`}
          className="text-xs text-gray-500 transition hover:text-violet-400"
        >
          See all →
        </a>
      </div>

      {/* Divider */}
      <div className="mb-3 h-px bg-white/[0.04]" />

      {/* Items */}
      <div className="space-y-1">
        {data.items.map((item, i) => (
          <ItemRow key={item.id} item={item} rank={i + 1} />
        ))}
      </div>
    </section>
  );
}
