"use client";

import { useEffect, useState } from "react";
import {
  fetchSources,
  createSource,
  updateSource,
  deleteSource,
  CATEGORY_LABELS,
  TIER_LABELS,
  type Source,
  type SourceCreate,
  type SourceTier,
  type ContentCategory,
} from "@/lib/adminApi";

type ToastState = { msg: string; ok: boolean } | null;

function Toast({ state }: { state: ToastState }) {
  if (!state) return null;
  return (
    <div
      className={`fixed top-5 right-5 z-50 rounded-lg px-4 py-3 text-sm shadow-lg ${
        state.ok ? "bg-emerald-600 text-white" : "bg-red-600 text-white"
      }`}
    >
      {state.msg}
    </div>
  );
}

const EMPTY_FORM: SourceCreate = {
  name: "",
  url: "",
  tier: "tier2",
  category: "news_article",
  is_active: true,
};

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<ToastState>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Source | null>(null);
  const [form, setForm] = useState<SourceCreate>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [filterActive, setFilterActive] = useState<"all" | "active" | "inactive">("all");

  function showToast(msg: string, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  }

  async function load() {
    setLoading(true);
    try {
      const data = await fetchSources();
      setSources(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  }

  function openEdit(s: Source) {
    setEditing(s);
    setForm({ name: s.name, url: s.url, tier: s.tier, category: s.category, is_active: s.is_active });
    setShowForm(true);
  }

  async function handleSave() {
    setSaving(true);
    try {
      if (editing) {
        await updateSource(editing.id, form);
        showToast("來源已更新");
      } else {
        await createSource(form);
        showToast("來源已新增");
      }
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Error", false);
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(s: Source) {
    try {
      await updateSource(s.id, { is_active: !s.is_active });
      showToast(s.is_active ? "已停用" : "已啟用");
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Error", false);
    }
  }

  async function handleDelete(s: Source) {
    if (!confirm(`確定刪除來源「${s.name}」？此操作不可復原。`)) return;
    try {
      await deleteSource(s.id);
      showToast("來源已刪除");
      await load();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Error", false);
    }
  }

  const filtered = sources.filter((s) => {
    if (filterActive === "active") return s.is_active;
    if (filterActive === "inactive") return !s.is_active;
    return true;
  });

  return (
    <div className="space-y-6 max-w-5xl">
      <Toast state={toast} />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">來源管理</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {sources.filter((s) => s.is_active).length} / {sources.length} 啟用中
          </p>
        </div>
        <button
          onClick={openCreate}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 transition"
        >
          + 新增來源
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {(["all", "active", "inactive"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilterActive(f)}
            className={`rounded-lg px-3 py-1.5 text-sm transition ${
              filterActive === f
                ? "bg-white/10 text-white"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {f === "all" ? "全部" : f === "active" ? "啟用" : "停用"}
          </button>
        ))}
      </div>

      {/* Table */}
      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : (
        <div className="rounded-xl border border-white/8 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-gray-500 text-xs uppercase">
                <th className="text-left px-4 py-2.5">名稱</th>
                <th className="text-left px-4 py-2.5">Category</th>
                <th className="text-left px-4 py-2.5">Tier</th>
                <th className="text-right px-4 py-2.5">Items</th>
                <th className="text-left px-4 py-2.5">狀態</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.id} className="border-b border-white/5 last:border-0 hover:bg-white/3">
                  <td className="px-4 py-2.5">
                    <div className="text-gray-200 font-medium">{s.name}</div>
                    <div className="text-xs text-gray-500 truncate max-w-xs">{s.url}</div>
                  </td>
                  <td className="px-4 py-2.5 text-gray-400">
                    {CATEGORY_LABELS[s.category] ?? s.category}
                  </td>
                  <td className="px-4 py-2.5 text-gray-400">
                    <span className={`text-xs rounded-full px-2 py-0.5 ${
                      s.tier === "tier1"
                        ? "bg-violet-500/20 text-violet-400"
                        : s.tier === "tier2"
                        ? "bg-blue-500/20 text-blue-400"
                        : "bg-white/10 text-gray-400"
                    }`}>
                      {s.tier}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-gray-400">{s.item_count}</td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => handleToggle(s)}
                      className={`text-xs rounded-full px-2 py-0.5 transition ${
                        s.is_active
                          ? "bg-emerald-500/20 text-emerald-400 hover:bg-red-500/20 hover:text-red-400"
                          : "bg-white/10 text-gray-500 hover:bg-emerald-500/20 hover:text-emerald-400"
                      }`}
                    >
                      {s.is_active ? "啟用" : "停用"}
                    </button>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-2 justify-end">
                      <button
                        onClick={() => openEdit(s)}
                        className="text-xs text-gray-500 hover:text-gray-200 transition"
                      >
                        編輯
                      </button>
                      <button
                        onClick={() => handleDelete(s)}
                        className="text-xs text-gray-500 hover:text-red-400 transition"
                      >
                        刪除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                    無資料
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#12141c] p-6 shadow-2xl">
            <h2 className="mb-5 text-lg font-semibold text-white">
              {editing ? "編輯來源" : "新增來源"}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">名稱</label>
                <input
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Hacker News AI"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">URL (RSS / API)</label>
                <input
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500"
                  value={form.url}
                  onChange={(e) => setForm({ ...form, url: e.target.value })}
                  placeholder="https://..."
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Category</label>
                  <select
                    className="w-full rounded-lg border border-white/10 bg-[#12141c] px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500"
                    value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value as ContentCategory })}
                  >
                    {(Object.entries(CATEGORY_LABELS) as [ContentCategory, string][]).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Tier</label>
                  <select
                    className="w-full rounded-lg border border-white/10 bg-[#12141c] px-3 py-2 text-sm text-white focus:outline-none focus:border-violet-500"
                    value={form.tier}
                    onChange={(e) => setForm({ ...form, tier: e.target.value as SourceTier })}
                  >
                    {(Object.entries(TIER_LABELS) as [SourceTier, string][]).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  className="accent-violet-500"
                />
                <label htmlFor="is_active" className="text-sm text-gray-300">啟用此來源</label>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setShowForm(false)}
                className="rounded-lg px-4 py-2 text-sm text-gray-400 hover:text-white transition"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name || !form.url}
                className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 transition"
              >
                {saving ? "儲存中…" : "儲存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
