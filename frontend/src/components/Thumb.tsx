"use client";
import { useState } from "react";
import type { TrendingItem } from "@/lib/api";

const CAT_EMOJI: Record<string, string> = {
  research_paper: "🔬", news_article: "📡", blog_post: "✍️",
  tool_release: "🛠", product_launch: "🚀", github_project: "⬡",
};
const CAT_BG: Record<string, string> = {
  research_paper: "bg-violet-900/50", news_article: "bg-blue-900/50",
  blog_post: "bg-sky-900/50", tool_release: "bg-orange-900/50",
  product_launch: "bg-pink-900/50", github_project: "bg-emerald-900/50",
};

interface Props {
  item: TrendingItem;
  size?: "sm" | "lg";
}

export default function Thumb({ item, size = "sm" }: Props) {
  const [failed, setFailed] = useState(false);
  const cat = item.category ?? "";
  const emoji = CAT_EMOJI[cat] ?? "✦";
  const bg = CAT_BG[cat] ?? "bg-gray-800";
  const cls = size === "lg"
    ? "w-16 h-16 rounded-2xl text-3xl"
    : "w-10 h-10 rounded-xl text-xl";

  if (!item.thumbnail_url || failed) {
    return (
      <div className={`flex flex-shrink-0 items-center justify-center ${cls} ${bg}`}>
        {emoji}
      </div>
    );
  }

  const isAvatar = item.thumbnail_url.includes("avatars.githubusercontent.com");

  return (
    <div className={`flex-shrink-0 overflow-hidden ${cls} ${!isAvatar ? bg + " flex items-center justify-center p-1.5" : ""}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={item.thumbnail_url}
        alt=""
        onError={() => setFailed(true)}
        className={isAvatar ? "h-full w-full object-cover" : "h-full w-full object-contain"}
      />
    </div>
  );
}
