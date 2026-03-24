"use client";
import { useState, useCallback } from "react";
import type { Item } from "@/lib/api";
import ItemRow from "./ItemRow";
import PreviewPanel from "./PreviewPanel";

interface Props {
  items: Item[];
  pageOffset: number;
}

export default function BrowseList({ items, pageOffset }: Props) {
  const [previewItem, setPreviewItem] = useState<Item | null>(null);
  const isPanelOpen = previewItem !== null;

  const handlePreview = useCallback((item: Item) => {
    setPreviewItem((prev) => (prev?.id === item.id ? null : item));
  }, []);

  const handleClose = useCallback(() => setPreviewItem(null), []);

  return (
    <div className="flex h-full gap-3">

      {/* ── Left: scrollable list column ── */}
      <div
        className={`flex flex-col min-w-0 transition-all duration-300 ease-in-out ${
          isPanelOpen ? "flex-[0_0_55%]" : "flex-1"
        }`}
      >
        <div className="flex-1 overflow-y-auto rounded-2xl border border-white/[0.06] bg-white/[0.02] p-2">
          {items.length === 0 ? (
            <p className="py-16 text-center text-gray-500 text-sm">No items found.</p>
          ) : (
            <div className="divide-y divide-white/[0.04]">
              {items.map((item, i) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  rank={pageOffset + i + 1}
                  onPreview={handlePreview}
                  isPreviewing={previewItem?.id === item.id}
                />
              ))}
            </div>
          )}

        </div>
      </div>

      {/* ── Right: preview panel (fills remaining height) ── */}
      <div
        className={`flex-1 min-w-0 transition-all duration-300 ease-in-out ${
          isPanelOpen ? "opacity-100" : "opacity-0 pointer-events-none flex-[0_0_0px]"
        }`}
      >
        {isPanelOpen && (
          <div className="h-full rounded-2xl border border-white/[0.08] bg-[#161820] shadow-2xl shadow-black/60 overflow-hidden preview-panel-enter">
            <PreviewPanel item={previewItem} onClose={handleClose} />
          </div>
        )}
      </div>

    </div>
  );
}
