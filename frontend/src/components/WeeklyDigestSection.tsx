import type { WeeklyDigestResponse } from "@/lib/api";

interface Props {
  data: WeeklyDigestResponse;
}

function parseWeekLabel(label: string): string {
  // "2026-W13" → "Week 13, 2026"
  const m = label.match(/^(\d{4})-W(\d{1,2})$/);
  if (!m) return label;
  return `Week ${parseInt(m[2])}, ${m[1]}`;
}

export default function WeeklyDigestSection({ data }: Props) {
  if (!data.digests || data.digests.length === 0) return null;

  const [first, ...rest] = data.digests;
  const weekStr = parseWeekLabel(data.week_label);

  return (
    <section className="mb-10">
      {/* Section header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
            AI 週報
          </p>
          <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-400">
            {weekStr}
          </span>
        </div>
        <p className="text-[10px] text-gray-600">由 Gemini AI 生成</p>
      </div>

      <div className="space-y-3">
        {/* First (featured) digest — larger */}
        <div className="rounded-2xl border border-white/[0.07] bg-[#161b27] p-5">
          <div className="flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-bold text-gray-100 mb-2">
                {first.title}
              </h3>
              <p className="text-sm leading-relaxed text-gray-400">
                {first.analysis}
              </p>
              {first.items.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {first.items.slice(0, 4).map((item) => (
                    <a
                      key={item.id}
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] text-gray-400 transition hover:border-white/15 hover:text-gray-200"
                    >
                      <span className="line-clamp-1 max-w-[180px]">{item.title}</span>
                      {item.ai_comment && (
                        <span className="hidden sm:inline text-amber-400/60 italic ml-1">— {item.ai_comment}</span>
                      )}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Remaining digests — compact row */}
        {rest.length > 0 && (
          <div className={`grid gap-3 ${rest.length === 1 ? "grid-cols-1" : rest.length === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
            {rest.map((digest) => (
              <div
                key={digest.title}
                className="rounded-xl border border-white/[0.06] bg-[#161b27] p-4"
              >
                <h4 className="text-sm font-semibold text-gray-200 mb-1.5 line-clamp-1">
                  {digest.title}
                </h4>
                <p className="text-[11px] leading-relaxed text-gray-500 line-clamp-3">
                  {digest.analysis}
                </p>
                {digest.items.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {digest.items.slice(0, 3).map((item) => (
                      <a
                        key={item.id}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="rounded-md border border-white/[0.06] bg-white/[0.02] px-1.5 py-0.5 text-[10px] text-gray-500 transition hover:text-gray-300"
                      >
                        <span className="line-clamp-1 max-w-[120px]">{item.title}</span>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
