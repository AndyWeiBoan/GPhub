interface Props {
  score: number; // 0–1
  size?: number;
}

export default function ScoreRing({ score, size = 36 }: Props) {
  const pct = Math.round(score * 100);
  const r = (size - 4) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  const color =
    pct >= 75 ? "#34d399" :
    pct >= 50 ? "#fbbf24" :
    "#6b7280";

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1f2937" strokeWidth={3} />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
        />
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center text-[10px] font-bold"
        style={{ color }}
      >
        {pct}
      </span>
    </div>
  );
}
