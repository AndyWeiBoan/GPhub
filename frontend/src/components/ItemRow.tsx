"use client";
import { useRef, useEffect, useState } from "react";
import type { Item } from "@/lib/api";
import ScoreRing from "./ScoreRing";
import CategoryPill from "./CategoryPill";
import SourcePill from "./SourcePill";

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 1) return "just now";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function shortDesc(item: Item): string {
  if (item.summary) {
    return item.summary.length > 120 ? item.summary.slice(0, 117) + "…" : item.summary;
  }
  if (item.raw_content) {
    const clean = item.raw_content.replace(/<[^>]+>/g, "").trim();
    return clean.length > 120 ? clean.slice(0, 117) + "…" : clean;
  }
  return "";
}

function isRichImage(url: string): boolean {
  return url.includes("avatars.githubusercontent.com") || url.includes("og:image");
}

const CATEGORY_EMOJI: Record<string, string> = {
  research_paper: "📄",
  news_article: "📰",
  blog_post: "✍️",
  tool_release: "🛠",
  product_launch: "🚀",
  github_project: "⬡",
};

const CATEGORY_BG: Record<string, string> = {
  research_paper: "bg-violet-900/40",
  news_article: "bg-blue-900/40",
  blog_post: "bg-sky-900/40",
  tool_release: "bg-orange-900/40",
  product_launch: "bg-pink-900/40",
  github_project: "bg-emerald-900/40",
};

function Thumbnail({ item }: { item: Item }) {
  const [failed, setFailed] = useState(false);
  const cat = item.category ?? "";
  const emoji = CATEGORY_EMOJI[cat] ?? "✦";
  const bg = CATEGORY_BG[cat] ?? "bg-gray-800";

  if (!item.thumbnail_url || failed) {
    return (
      <div className={`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl text-xl ${bg}`}>
        {emoji}
      </div>
    );
  }

  const rich = isRichImage(item.thumbnail_url);

  return (
    <div className={`h-12 w-12 flex-shrink-0 overflow-hidden rounded-xl ${rich ? "" : bg + " flex items-center justify-center p-1.5"}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={item.thumbnail_url}
        alt=""
        onError={() => setFailed(true)}
        className={rich ? "h-full w-full object-cover" : "h-full w-full object-contain"}
      />
    </div>
  );
}

interface Props {
  item: Item;
  rank: number;
  onPreview?: (item: Item) => void;
  onScrollOut?: () => void;
  isPreviewing?: boolean;
}

export default function ItemRow({ item, rank, onPreview, onScrollOut, isPreviewing }: Props) {
  const desc = shortDesc(item);
  const time = timeAgo(item.published_at ?? item.fetched_at);
  const rowRef = useRef<HTMLDivElement>(null);

  // Auto-close when scrolled out of view
  useEffect(() => {
    if (!isPreviewing || !onScrollOut || !rowRef.current) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) onScrollOut();
      },
      { threshold: 0 }
    );
    observer.observe(rowRef.current);
    return () => observer.disconnect();
  }, [isPreviewing, onScrollOut]);

  return (
    <div
      ref={rowRef}
      className={`group flex items-center gap-3 rounded-xl p-3 transition-all hover:bg-white/[0.04] ${isPreviewing ? "bg-white/[0.06]" : ""}`}
    >
      {/* Rank */}
      <span className="w-5 flex-shrink-0 text-right text-xs font-bold text-gray-600">
        {rank}
      </span>

      {/* Thumbnail */}
      <Thumbnail item={item} />

      {/* Content — clickable link area */}
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="min-w-0 flex-1"
      >
        <div className="flex flex-wrap items-center gap-1.5 mb-0.5">
          <CategoryPill category={item.category} />
          <SourcePill name={item.source_name} />
          {time && <span className="text-[11px] text-gray-600">{time}</span>}
          {item.github_stars != null && (
            <span className="text-[11px] text-yellow-500/80">★ {item.github_stars.toLocaleString()}</span>
          )}
        </div>
        <p className="text-sm font-semibold leading-snug text-gray-100 group-hover:text-white line-clamp-1">
          {item.title}
        </p>
        {item.ai_comment ? (
          <p className="mt-0.5 line-clamp-1 text-xs leading-relaxed text-amber-400/70 italic">
            {item.ai_comment}
          </p>
        ) : desc ? (
          <p className="mt-0.5 line-clamp-1 text-xs leading-relaxed text-gray-500">
            {desc}
          </p>
        ) : null}
      </a>

      {/* Score */}
      <ScoreRing score={item.total_score} size={36} />

      {/* Preview button */}
      {onPreview && (
        <button
          onClick={() => onPreview(item)}
          aria-label={isPreviewing ? "Close preview" : "Preview"}
          title={isPreviewing ? "Close preview" : "Preview"}
          className={`flex-shrink-0 flex h-7 w-7 items-center justify-center rounded-lg border transition ${
            isPreviewing
              ? "border-violet-500 bg-violet-500/20 text-violet-300 hover:bg-violet-500/30"
              : "border-white/10 bg-transparent text-gray-500 opacity-0 group-hover:opacity-100 hover:border-white/20 hover:text-white"
          }`}
        >
          {isPreviewing ? (
            <svg viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5">
              <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.75.75 0 1 1 1.06 1.06L9.06 8l3.22 3.22a.75.75 0 1 1-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 0 1-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06z" />
            </svg>
          ) : (
            <svg viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5">
              <path d="M8 3C4.5 3 1.5 5.5 0 8c1.5 2.5 4.5 5 8 5s6.5-2.5 8-5c-1.5-2.5-4.5-5-8-5zm0 8a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0-4.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z" />
            </svg>
          )}
        </button>
      )}
    </div>
  );
}
