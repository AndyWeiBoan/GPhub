"use client";
import { useEffect, useState } from "react";
import type { Item } from "@/lib/api";
import CategoryPill from "./CategoryPill";
import SourcePill from "./SourcePill";
import GithubReadme from "./GithubReadme";

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 1) return "just now";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
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

const SCORE_COLOR: Record<string, string> = {
  Impact: "text-orange-400",
  Credibility: "text-sky-400",
  Novelty: "text-emerald-400",
  Total: "text-violet-400",
};

interface Props {
  item: Item | null;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}

export default function PreviewPanel({ item, onClose, onPrev, onNext, hasPrev, hasNext }: Props) {
  const [imgFailed, setImgFailed] = useState(false);
  const [visible, setVisible] = useState(false);
  const [rawExpanded, setRawExpanded] = useState(false);

  useEffect(() => {
    setImgFailed(false);
    setRawExpanded(false);
  }, [item?.id]);

  useEffect(() => {
    if (item) {
      const t = setTimeout(() => setVisible(true), 10);
      return () => clearTimeout(t);
    } else {
      setVisible(false);
    }
  }, [item]);

  if (!item) return null;

  const cat = item.category ?? "";
  const emoji = CATEGORY_EMOJI[cat] ?? "✦";
  const bg = CATEGORY_BG[cat] ?? "bg-gray-800";
  const time = timeAgo(item.published_at ?? item.fetched_at);
  const date = formatDate(item.published_at);
  const hasImage = item.thumbnail_url && !imgFailed;

  const rawText = item.raw_content
    ? item.raw_content.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim()
    : "";
  const RAW_PREVIEW_LEN = 800;
  const RAW_MAX_LEN = 1500;
  const rawCapped = rawText.slice(0, RAW_MAX_LEN);
  const rawPreview = rawCapped.slice(0, RAW_PREVIEW_LEN);
  const hasMore = rawText.length > RAW_PREVIEW_LEN;

  const hostname = (() => {
    try { return new URL(item.url).hostname.replace(/^www\./, ""); }
    catch { return ""; }
  })();

  return (
    <div
      className={`flex flex-col h-full transition-all duration-300 ease-out ${
        visible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-4"
      }`}
    >
      {/* ── Top bar: close ── */}
      <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-white/[0.06]">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Preview</span>
        <div className="flex items-center gap-1">
          <button
            onClick={onPrev}
            disabled={!hasPrev}
            aria-label="Previous item"
            className={`flex h-7 w-7 items-center justify-center rounded-lg text-sm transition ${
              hasPrev
                ? "text-gray-400 hover:bg-white/[0.08] hover:text-white"
                : "text-gray-700 cursor-not-allowed"
            }`}
          >
            ←
          </button>
          <button
            onClick={onNext}
            disabled={!hasNext}
            aria-label="Next item"
            className={`flex h-7 w-7 items-center justify-center rounded-lg text-sm transition ${
              hasNext
                ? "text-gray-400 hover:bg-white/[0.08] hover:text-white"
                : "text-gray-700 cursor-not-allowed"
            }`}
          >
            →
          </button>
          <button
            onClick={onClose}
            aria-label="Close preview"
            className="flex h-7 w-7 items-center justify-center rounded-lg text-gray-500 transition hover:bg-white/[0.08] hover:text-white"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4">
              <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.75.75 0 1 1 1.06 1.06L9.06 8l3.22 3.22a.75.75 0 1 1-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 0 1-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06z" />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Action + Scores (pinned below header) ── */}
      <div className="px-4 py-3 space-y-3 border-b border-white/[0.06]">
        {/* Open Article button */}
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-500 active:scale-95"
        >
          Open
          <svg viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5">
            <path d="M3.75 2h3.5a.75.75 0 0 1 0 1.5h-3.5a.25.25 0 0 0-.25.25v8.5c0 .138.112.25.25.25h8.5a.25.25 0 0 0 .25-.25v-3.5a.75.75 0 0 1 1.5 0v3.5A1.75 1.75 0 0 1 12.25 14h-8.5A1.75 1.75 0 0 1 2 12.25v-8.5C2 2.784 2.784 2 3.75 2zm6.854.146a.5.5 0 0 1 .353-.146H14a.5.5 0 0 1 .5.5v3.043a.5.5 0 0 1-.854.353L12.5 4.75l-4.22 4.22a.5.5 0 0 1-.707-.707L11.793 4.03l-1.146-1.146a.5.5 0 0 1-.043-.738z" />
          </svg>
        </a>

        {/* Score row */}
        <div className="grid grid-cols-4 gap-1.5 text-center">
          {[
            { label: "Impact", value: item.impact_score },
            { label: "Credibility", value: item.credibility_score },
            { label: "Novelty", value: item.novelty_score },
            { label: "Total", value: item.total_score },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-lg border border-white/[0.06] bg-white/[0.03] py-2">
              <p className="text-[9px] font-medium text-gray-500 uppercase tracking-wide">{label}</p>
              <p className={`text-sm font-bold ${SCORE_COLOR[label]}`}>{value.toFixed(1)}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Scrollable body ── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Thumbnail */}
        {hasImage ? (
          <div className="w-full overflow-hidden rounded-xl aspect-video bg-white/[0.04]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={item.thumbnail_url!}
              alt=""
              onError={() => setImgFailed(true)}
              className="h-full w-full object-cover"
            />
          </div>
        ) : (
          <div className={`w-full rounded-xl aspect-video flex items-center justify-center text-5xl ${bg}`}>
            {emoji}
          </div>
        )}

        {/* Meta pills + time */}
        <div className="flex flex-wrap items-center gap-1.5">
          <CategoryPill category={item.category} />
          <SourcePill name={item.source_name} />
          {item.github_stars != null && (
            <span className="text-[11px] text-yellow-500/80">★ {item.github_stars.toLocaleString()}</span>
          )}
          {time && <span className="ml-auto text-[11px] text-gray-600">{time}</span>}
        </div>

        {/* Title */}
        <h2 className="text-sm font-bold leading-snug text-gray-100">
          {item.title}
        </h2>

        {/* Author + date */}
        {(item.author || date) && (
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-500">
            {item.author && (
              <span className="flex items-center gap-1">
                <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3 text-gray-600">
                  <path d="M10.5 5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM8 8a4 4 0 0 0-4 4 .5.5 0 0 0 .5.5h7a.5.5 0 0 0 .5-.5 4 4 0 0 0-4-4z"/>
                </svg>
                {item.author}
              </span>
            )}
            {date && (
              <span className="flex items-center gap-1">
                <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3 text-gray-600">
                  <path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM2 3.5v1h12v-1A.5.5 0 0 0 13.5 3h-11A.5.5 0 0 0 2 3.5zm0 2.5v7.5A.5.5 0 0 0 2.5 14h11a.5.5 0 0 0 .5-.5V6H2z"/>
                </svg>
                {date}
              </span>
            )}
          </div>
        )}

        {/* AI Comment */}
        {item.ai_comment && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-500/60 mb-1">AI 短評</p>
            <p className="text-sm leading-relaxed text-amber-300/80 italic">{item.ai_comment}</p>
          </div>
        )}

        {/* Summary */}
        {item.summary && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-600">Summary</p>
            <p className="text-sm leading-relaxed text-gray-300">{item.summary}</p>
          </div>
        )}

        {/* Raw content */}
        {rawText && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-600">Content</p>
            <p className="text-sm leading-relaxed text-gray-400 whitespace-pre-line">
              {rawExpanded || !hasMore ? rawCapped : rawPreview + "…"}
            </p>
            {hasMore && (
              <button
                onClick={() => setRawExpanded((v) => !v)}
                className="text-xs text-violet-400 hover:text-violet-300 transition"
              >
                {rawExpanded ? "Show less ↑" : "Show more ↓"}
              </button>
            )}
          </div>
        )}

        {/* README — GitHub only */}
        {item.category === "github_project" && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-600">README</p>
              <div className="flex-1 border-t border-white/[0.06]" />
            </div>
            <GithubReadme repoUrl={item.url} />
          </div>
        )}

        {/* Source URL */}
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-600">Source</p>
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-[11px] text-gray-500 hover:text-gray-300 transition break-all"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3 flex-shrink-0 text-gray-600">
              <path d="M7.775 3.275a.75.75 0 0 0 1.06 1.06l1.25-1.25a2 2 0 1 1 2.83 2.83l-2.5 2.5a2 2 0 0 1-2.83 0 .75.75 0 0 0-1.06 1.06 3.5 3.5 0 0 0 4.95 0l2.5-2.5a3.5 3.5 0 0 0-4.95-4.95l-1.25 1.25zm-4.69 9.64a2 2 0 0 1 0-2.83l2.5-2.5a2 2 0 0 1 2.83 0 .75.75 0 0 0 1.06-1.06 3.5 3.5 0 0 0-4.95 0l-2.5 2.5a3.5 3.5 0 0 0 4.95 4.95l1.25-1.25a.75.75 0 0 0-1.06-1.06l-1.25 1.25a2 2 0 0 1-2.83 0z" />
            </svg>
            {hostname}
          </a>
        </div>

        {/* Photo attribution */}
        {item.thumbnail_attribution && (() => {
          const parts = item.thumbnail_attribution.split("|");
          const text = parts[0];
          const href = parts[1];
          return (
            <p className="text-[10px] text-gray-700">
              {href ? (
                <a href={href} target="_blank" rel="noopener noreferrer" className="hover:text-gray-500 transition">
                  {text}
                </a>
              ) : text}
            </p>
          );
        })()}
      </div>
    </div>
  );
}
