import type { Category } from "@/lib/api";

const MAP: Record<string, { label: string; color: string }> = {
  research_paper:  { label: "Research",  color: "bg-violet-500/20 text-violet-300" },
  news_article:    { label: "News",      color: "bg-blue-500/20 text-blue-300" },
  blog_post:       { label: "Blog",      color: "bg-sky-500/20 text-sky-300" },
  community:       { label: "社群",      color: "bg-yellow-500/20 text-yellow-300" },
  product_launch:  { label: "Product",   color: "bg-pink-500/20 text-pink-300" },
  github_project:  { label: "GitHub",    color: "bg-emerald-500/20 text-emerald-300" },
};

export default function CategoryPill({ category }: { category: string | null }) {
  if (!category) return null;
  const { label, color } = MAP[category] ?? { label: category, color: "bg-gray-700 text-gray-400" };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${color}`}>
      {label}
    </span>
  );
}
