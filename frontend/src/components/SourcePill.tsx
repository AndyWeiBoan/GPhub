// Colorful pill for source names — color + shape derived from the source string

// 12 color options (bg + text + border) — fully static classes for Tailwind purge safety
const COLORS = [
  "bg-violet-500/15 text-violet-300 border-violet-500/25",
  "bg-blue-500/15 text-blue-300 border-blue-500/25",
  "bg-cyan-500/15 text-cyan-300 border-cyan-500/25",
  "bg-teal-500/15 text-teal-300 border-teal-500/25",
  "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  "bg-lime-500/15 text-lime-300 border-lime-500/25",
  "bg-amber-500/15 text-amber-300 border-amber-500/25",
  "bg-orange-500/15 text-orange-300 border-orange-500/25",
  "bg-rose-500/15 text-rose-300 border-rose-500/25",
  "bg-pink-500/15 text-pink-300 border-pink-500/25",
  "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/25",
  "bg-indigo-500/15 text-indigo-300 border-indigo-500/25",
];

// 3 safe shape variants (no dynamic class composition)
const SHAPES = [
  "rounded-full",   // pill
  "rounded-md",     // soft rectangle
  "rounded-xl",     // squircle
];

// djb2 hash — much better distribution than polynomial rolling hash
function hashStr(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) & 0xffffffff;
  }
  return Math.abs(h);
}

export default function SourcePill({ name }: { name: string | null }) {
  if (!name) return null;
  const h = hashStr(name);
  const color = COLORS[h % COLORS.length];
  const shape = SHAPES[h % SHAPES.length];
  return (
    <span className={`inline-flex items-center border px-2 py-0.5 text-[10px] font-medium ${color} ${shape}`}>
      {name}
    </span>
  );
}
