"use client";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  repoUrl: string;
}

type State =
  | { status: "loading" }
  | { status: "ok"; content: string }
  | { status: "error" };

async function fetchReadme(owner: string, repo: string): Promise<string> {
  const branches = ["main", "master"];
  const files = ["README.md", "readme.md", "README.rst", "README"];
  for (const branch of branches) {
    for (const file of files) {
      const url = `https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${file}`;
      const res = await fetch(url);
      if (res.ok) return res.text();
    }
  }
  throw new Error("README not found");
}

// Strip HTML tags, comments, and excess blank lines from raw markdown
function sanitize(md: string): string {
  return md
    .replace(/<!--[\s\S]*?-->/g, "")        // HTML comments
    .replace(/<[^>]+>/g, "")                 // inline HTML tags
    .replace(/\n{3,}/g, "\n\n")             // collapse 3+ blank lines
    .trim();
}

export default function GithubReadme({ repoUrl }: Props) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    setState({ status: "loading" });

    const path = repoUrl.replace(/^https?:\/\/github\.com\//, "").replace(/\/$/, "");
    const parts = path.split("/");
    if (parts.length < 2) { setState({ status: "error" }); return; }
    const [owner, repo] = parts;

    let cancelled = false;
    fetchReadme(owner, repo)
      .then((text) => { if (!cancelled) setState({ status: "ok", content: sanitize(text) }); })
      .catch(() => { if (!cancelled) setState({ status: "error" }); });

    return () => { cancelled = true; };
  }, [repoUrl]);

  if (state.status === "loading") {
    return (
      <div className="flex items-center gap-2 py-4 text-xs text-gray-600">
        <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeDasharray="28" strokeDashoffset="10" />
        </svg>
        Loading README…
      </div>
    );
  }

  if (state.status === "error") {
    return <p className="py-4 text-xs text-gray-600">README not available.</p>;
  }

  return (
    <div className="
      prose prose-sm prose-invert max-w-none
      prose-headings:text-gray-200 prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-1
      prose-h1:text-base prose-h2:text-sm prose-h3:text-sm prose-h4:text-xs
      prose-p:text-gray-400 prose-p:leading-relaxed prose-p:my-1.5
      prose-a:text-violet-400 prose-a:no-underline hover:prose-a:text-violet-300
      prose-code:text-emerald-400 prose-code:bg-white/[0.06] prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono prose-code:before:content-none prose-code:after:content-none
      prose-pre:bg-white/[0.04] prose-pre:border prose-pre:border-white/[0.06] prose-pre:rounded-lg prose-pre:text-xs prose-pre:my-2
      prose-strong:text-gray-300
      prose-li:text-gray-400 prose-li:leading-relaxed prose-li:my-0
      prose-ul:my-1.5 prose-ol:my-1.5
      prose-hr:border-white/[0.08] prose-hr:my-3
      prose-blockquote:border-l-violet-500/50 prose-blockquote:text-gray-500 prose-blockquote:not-italic
      prose-table:text-xs prose-table:border-collapse
      prose-thead:border-b prose-thead:border-white/10
      prose-th:text-gray-400 prose-th:font-semibold prose-th:py-1.5 prose-th:px-2 prose-th:text-left
      prose-td:text-gray-500 prose-td:py-1.5 prose-td:px-2 prose-td:border-b prose-td:border-white/[0.04]
      prose-img:hidden
    ">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {state.content}
      </ReactMarkdown>
    </div>
  );
}
