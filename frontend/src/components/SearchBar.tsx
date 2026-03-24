"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

interface Props {
  sources: string[];
  initialQ: string;
  initialSource: string;
  basePath: string; // e.g. "/browse"
}

export default function SearchBar({ sources, initialQ, initialSource, basePath }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState(initialQ);
  const [source, setSource] = useState(initialSource);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function buildUrl(newQ: string, newSource: string) {
    const p = new URLSearchParams(params.toString());
    p.set("page", "1");
    if (newQ) p.set("q", newQ); else p.delete("q");
    if (newSource) p.set("source_name", newSource); else p.delete("source_name");
    return `${basePath}?${p.toString()}`;
  }

  // Debounce search input (400ms)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      router.push(buildUrl(q, source));
    }, 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  // Source dropdown: navigate immediately
  function handleSource(val: string) {
    setSource(val);
    router.push(buildUrl(q, val));
  }

  return (
    <div className="flex flex-1 items-center gap-2">
      {/* Search input */}
      <div className="relative flex-1">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
          ⌕
        </span>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search titles…"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] py-1.5 pl-8 pr-3 text-sm text-gray-200 placeholder-gray-600 outline-none transition focus:border-violet-500/50 focus:bg-white/[0.05]"
        />
        {q && (
          <button
            onClick={() => setQ("")}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-300"
          >
            ✕
          </button>
        )}
      </div>

      {/* Source dropdown */}
      <select
        value={source}
        onChange={(e) => handleSource(e.target.value)}
        className="rounded-lg border border-white/10 bg-[#161b27] py-1.5 pl-3 pr-7 text-sm text-gray-300 outline-none transition focus:border-violet-500/50 hover:border-white/20 cursor-pointer"
      >
        <option value="">All Sources</option>
        {sources.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
    </div>
  );
}
