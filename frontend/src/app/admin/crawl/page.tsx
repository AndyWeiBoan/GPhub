"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  triggerCrawlAll,
  triggerCrawlOne,
  triggerCrawlCategory,
  triggerRescore,
  fetchJob,
  CRAWLER_NAMES,
  CATEGORY_LABELS,
  type CrawlerName,
  type ContentCategory,
  type Job,
  type JobStep,
} from "@/lib/adminApi";

// ── Job Progress Panel ────────────────────────────────────────────────────────

const PHASE_COLOR: Record<string, string> = {
  pending: "text-gray-500",
  running: "text-blue-400",
  done:    "text-emerald-400",
  error:   "text-red-400",
};

const PHASE_BG: Record<string, string> = {
  pending: "border-white/8 bg-white/3",
  running: "border-blue-500/30 bg-blue-500/5",
  done:    "border-emerald-500/30 bg-emerald-500/5",
  error:   "border-red-500/30 bg-red-500/5",
};

const STEP_ICON: Record<string, string> = {
  pending: "○",
  running: "◎",
  done:    "✓",
  error:   "✗",
};

function StepRow({ step }: { step: JobStep }) {
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <span
        className={clsx(
          "mt-0.5 shrink-0 text-sm font-mono",
          PHASE_COLOR[step.status],
          step.status === "running" && "animate-pulse"
        )}
      >
        {STEP_ICON[step.status]}
      </span>
      <div className="min-w-0 flex-1">
        <span className={clsx("text-sm", step.status === "done" ? "text-gray-300" : "text-gray-400")}>
          {step.name}
        </span>
        {step.detail && (
          <span className="ml-2 text-xs text-gray-600">{step.detail}</span>
        )}
      </div>
    </div>
  );
}

function elapsed(startIso: string | null, endIso: string | null): string {
  if (!startIso) return "";
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const secs = Math.round((end - start) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function JobPanel({ job, onDismiss }: { job: Job; onDismiss: () => void }) {
  return (
    <div className={clsx("rounded-xl border p-4 transition-all", PHASE_BG[job.phase])}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className={clsx("text-xs font-semibold uppercase tracking-wider", PHASE_COLOR[job.phase])}>
              {job.phase === "running" ? "🔄 執行中" : job.phase === "done" ? "✅ 完成" : job.phase === "error" ? "❌ 失敗" : "⏳ 等待"}
            </span>
            <span className="text-xs text-gray-600">
              #{job.job_id}
            </span>
          </div>
          <p className="text-sm font-medium text-white mt-0.5">{job.label}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {job.started_at && (
            <span className="text-xs text-gray-600 tabular-nums">
              {elapsed(job.started_at, job.finished_at)}
            </span>
          )}
          {(job.phase === "done" || job.phase === "error") && (
            <button
              onClick={onDismiss}
              className="text-xs text-gray-600 hover:text-gray-300 transition"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Steps */}
      <div className="divide-y divide-white/5 border-t border-white/5">
        {job.steps.map((s, i) => (
          <StepRow key={i} step={s} />
        ))}
      </div>

      {/* Result summary */}
      {job.phase === "done" && job.result && (
        <div className="mt-3 flex gap-4 border-t border-white/5 pt-3">
          {Object.entries(job.result).map(([k, v]) => (
            <div key={k} className="text-xs">
              <span className="text-gray-500">{k}: </span>
              <span className="text-emerald-400 font-semibold">{v}</span>
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {job.phase === "error" && job.error && (
        <p className="mt-3 text-xs text-red-400 border-t border-white/5 pt-3 font-mono break-all">
          {job.error}
        </p>
      )}
    </div>
  );
}

// ── Hook: poll a job until done/error ─────────────────────────────────────────

function useJobPoller() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  const startPolling = useCallback((jobId: string) => {
    if (timers.current.has(jobId)) return;

    const poll = async () => {
      try {
        const job = await fetchJob(jobId);
        setJobs((prev) => {
          const idx = prev.findIndex((j) => j.job_id === jobId);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = job;
            return next;
          }
          return [job, ...prev];
        });
        if (job.phase === "done" || job.phase === "error") {
          clearInterval(timers.current.get(jobId));
          timers.current.delete(jobId);
        }
      } catch {
        // ignore transient errors
      }
    };

    // Immediate fetch + poll every 1.5s
    poll();
    const id = setInterval(poll, 1500);
    timers.current.set(jobId, id);
  }, []);

  const dismiss = useCallback((jobId: string) => {
    setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    clearInterval(timers.current.get(jobId));
    timers.current.delete(jobId);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      timers.current.forEach((id) => clearInterval(id));
    };
  }, []);

  return { jobs, startPolling, dismiss };
}

// ── Action Button ─────────────────────────────────────────────────────────────

function ActionButton({
  label,
  sublabel,
  accent,
  disabled,
  onClick,
}: {
  label: string;
  sublabel?: string;
  accent?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "flex flex-col items-start gap-0.5 rounded-xl border px-5 py-4 text-left transition",
        "disabled:opacity-40 disabled:cursor-not-allowed",
        accent
          ? "border-violet-500/40 bg-violet-500/10 hover:bg-violet-500/20 text-violet-300"
          : "border-white/8 bg-white/3 hover:bg-white/8 text-gray-200"
      )}
    >
      <span className="text-sm font-medium">{label}</span>
      {sublabel && <span className="text-xs text-gray-500">{sublabel}</span>}
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CrawlPage() {
  const { jobs, startPolling, dismiss } = useJobPoller();
  const [error, setError] = useState<string | null>(null);
  const activeJobs = jobs.filter((j) => j.phase === "running" || j.phase === "pending");

  async function run(fn: () => Promise<{ job_id: string; message: string; crawlers?: string[] }>) {
    setError(null);
    try {
      const r = await fn();
      startPolling(r.job_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">爬蟲觸發</h1>
        {activeJobs.length > 0 && (
          <span className="flex items-center gap-1.5 rounded-full bg-blue-500/15 px-3 py-1 text-xs font-medium text-blue-400">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
            {activeJobs.length} 個任務執行中
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Live job panels */}
      {jobs.length > 0 && (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobPanel key={job.job_id} job={job} onDismiss={() => dismiss(job.job_id)} />
          ))}
        </div>
      )}

      {/* All crawlers */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">全部</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ActionButton
            accent
            label="🕷 Run All Crawlers"
            sublabel="RSS + GitHub + Anthropic → 完整流程"
            onClick={() => run(triggerCrawlAll)}
          />
          <ActionButton
            label="🔄 Rescore All Items"
            sublabel="重新計算所有 items 的分數"
            onClick={() => run(triggerRescore)}
          />
        </div>
      </section>

      {/* Per crawler */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">依 Crawler</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {CRAWLER_NAMES.map((name) => (
            <ActionButton
              key={name}
              label={`Run ${name.toUpperCase()}`}
              sublabel={
                name === "rss" ? "所有 RSS feeds"
                : name === "github" ? "GitHub Trending"
                : "Anthropic Blog"
              }
              onClick={() => run(() => triggerCrawlOne(name as CrawlerName))}
            />
          ))}
        </div>
      </section>

      {/* Per category */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">依 Category</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(Object.entries(CATEGORY_LABELS) as [ContentCategory, string][]).map(([cat, label]) => (
            <ActionButton
              key={cat}
              label={label}
              sublabel={cat}
              onClick={() => run(() => triggerCrawlCategory(cat))}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
