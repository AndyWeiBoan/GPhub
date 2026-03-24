"use client";
import { useState, useCallback, useEffect, useRef } from "react";
import type { Item } from "@/lib/api";
import ItemRow from "./ItemRow";
import PreviewPanel from "./PreviewPanel";

interface Props {
  items: Item[];
  pageOffset: number;
}

export default function BrowseList({ items, pageOffset }: Props) {
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const previewItem = previewIndex !== null ? items[previewIndex] ?? null : null;
  const isPanelOpen = previewItem !== null;

  const handlePreview = useCallback((item: Item) => {
    const idx = items.findIndex((i) => i.id === item.id);
    setPreviewIndex((prev) => (prev === idx ? null : idx));
  }, [items]);

  const handleClose = useCallback(() => setPreviewIndex(null), []);

  const handlePrev = useCallback(() => {
    setPreviewIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev));
  }, []);

  const handleNext = useCallback(() => {
    setPreviewIndex((prev) => (prev !== null && prev < items.length - 1 ? prev + 1 : prev));
  }, [items.length]);

  // Scroll active row into view when navigating with arrows
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  useEffect(() => {
    if (previewIndex !== null) {
      rowRefs.current[previewIndex]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [previewIndex]);

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
                <div key={item.id} ref={(el) => { rowRefs.current[i] = el; }}>
                  <ItemRow
                    item={item}
                    rank={pageOffset + i + 1}
                    onPreview={handlePreview}
                    isPreviewing={previewIndex === i}
                  />
                </div>
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
            <PreviewPanel
              item={previewItem}
              onClose={handleClose}
              onPrev={handlePrev}
              onNext={handleNext}
              hasPrev={previewIndex !== null && previewIndex > 0}
              hasNext={previewIndex !== null && previewIndex < items.length - 1}
            />
          </div>
        )}
      </div>

    </div>
  );
}
