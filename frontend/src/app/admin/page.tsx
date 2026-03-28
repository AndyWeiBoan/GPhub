"use client";

import { useEffect, useState } from "react";
import {
  fetchAdminStats,
  fetchCrawlRuns,
  type AdminStats,
  type CrawlRun,
  CATEGORY_LABELS,
} from "@/lib/adminApi";

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    success: "bg-emerald-500/20 text-emerald-400",
    partial: "bg-yellow-500/20 text-yellow-400",
    running: "bg-blue-500/20 text-blue-400",
    error: "bg-red-500/20 text-red-400",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${map[status] ?? "bg-white/10 text-gray-400"}`}>
      {status}
    </span>
  );
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-TW", { hour12: false });
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchAdminStats(), fetchCrawlRuns(10)])
      .then(([s, r]) => { setStats(s); setRuns(r); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500">Loading…</p>;

  return (
    <div className="space-y-8 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          最後爬蟲：{fmtDate(stats?.last_crawl ?? null)}
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total Items" value={stats?.total_items ?? 0} />
        <StatCard label="Total Sources" value={stats?.total_sources ?? 0} sub={`${stats?.active_sources ?? 0} 啟用中`} />
        {Object.entries(stats?.categories ?? {}).map(([cat, count]) => (
          <StatCard
            key={cat}
            label={CATEGORY_LABELS[cat as keyof typeof CATEGORY_LABELS] ?? cat}
            value={count}
          />
        ))}
      </div>

      {/* Top sources */}
      <div>
        <h2 className="text-base font-semibold text-gray-200 mb-3">Items by Source（Top 10）</h2>
        <div className="rounded-xl border border-white/8 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-gray-500 text-xs uppercase">
                <th className="text-left px-4 py-2">來源</th>
                <th className="text-right px-4 py-2">Items</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats?.items_by_source ?? {})
                .slice(0, 10)
                .map(([source, count]) => (
                  <tr key={source} className="border-b border-white/5 last:border-0 hover:bg-white/3">
                    <td className="px-4 py-2 text-gray-300">{source}</td>
                    <td className="px-4 py-2 text-right text-gray-400">{count}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent crawl runs */}
      <div>
        <h2 className="text-base font-semibold text-gray-200 mb-3">最近爬蟲紀錄</h2>
        <div className="rounded-xl border border-white/8 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-gray-500 text-xs uppercase">
                <th className="text-left px-4 py-2">開始時間</th>
                <th className="text-left px-4 py-2">結束時間</th>
                <th className="text-right px-4 py-2">抓取</th>
                <th className="text-right px-4 py-2">新增</th>
                <th className="text-left px-4 py-2">狀態</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b border-white/5 last:border-0 hover:bg-white/3">
                  <td className="px-4 py-2 text-gray-300">{fmtDate(r.started_at)}</td>
                  <td className="px-4 py-2 text-gray-400">{fmtDate(r.finished_at)}</td>
                  <td className="px-4 py-2 text-right text-gray-400">{r.items_fetched}</td>
                  <td className="px-4 py-2 text-right text-emerald-400">{r.items_new}</td>
                  <td className="px-4 py-2">{statusBadge(r.status)}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                    尚無爬蟲紀錄
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
