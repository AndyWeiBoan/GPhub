"use client";

import { useEffect, useState } from "react";
import {
  fetchAdminStats,
  deleteItemsByCategory,
  CATEGORY_LABELS,
  type ContentCategory,
  type AdminStats,
} from "@/lib/adminApi";

type ToastState = { msg: string; ok: boolean } | null;

export default function DataPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<ToastState>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  function showToast(msg: string, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  }

  async function load() {
    setLoading(true);
    try {
      const s = await fetchAdminStats();
      setStats(s);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleDelete(cat: ContentCategory) {
    const label = CATEGORY_LABELS[cat];
    const count = stats?.categories[cat] ?? 0;
    if (
      !confirm(
        `⚠️ 確定要刪除所有「${label}」的 ${count} 筆資料嗎？\n此操作無法復原。`
      )
    )
      return;

    setDeleting(cat);
    try {
      const result = await deleteItemsByCategory(cat);
      showToast(`已刪除 ${result.deleted} 筆「${label}」資料`);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Error", false);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="space-y-8 max-w-3xl">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-5 right-5 z-50 rounded-lg px-4 py-3 text-sm shadow-lg ${
            toast.ok ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
          }`}
        >
          {toast.msg}
        </div>
      )}

      <div>
        <h1 className="text-2xl font-bold text-white">資料管理</h1>
        <p className="text-sm text-gray-500 mt-1">依 Category 批次刪除資料，操作不可復原。</p>
      </div>

      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : (
        <div className="rounded-xl border border-white/8 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-gray-500 text-xs uppercase">
                <th className="text-left px-5 py-3">Category</th>
                <th className="text-right px-5 py-3">Items</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(Object.entries(CATEGORY_LABELS) as [ContentCategory, string][]).map(
                ([cat, label]) => {
                  const count = stats?.categories[cat] ?? 0;
                  return (
                    <tr
                      key={cat}
                      className="border-b border-white/5 last:border-0 hover:bg-white/3"
                    >
                      <td className="px-5 py-3">
                        <div className="text-gray-200 font-medium">{label}</div>
                        <div className="text-xs text-gray-600">{cat}</div>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <span className={`text-lg font-bold ${count > 0 ? "text-white" : "text-gray-600"}`}>
                          {count}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <button
                          onClick={() => handleDelete(cat)}
                          disabled={count === 0 || deleting === cat}
                          className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition"
                        >
                          {deleting === cat ? "刪除中…" : "刪除全部"}
                        </button>
                      </td>
                    </tr>
                  );
                }
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 px-5 py-4 text-sm text-yellow-400">
        ⚠️ 刪除後資料無法恢復。如有需要，請先備份資料庫（<code className="text-yellow-300">ai_digest.db</code>）再操作。
      </div>
    </div>
  );
}
