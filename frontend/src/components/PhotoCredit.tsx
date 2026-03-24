"use client";

/**
 * Displays "Photo by X on Pexels" attribution as required by Pexels ToS.
 * attribution format: "Photo by NAME on Pexels|PHOTO_PAGE_URL"
 *
 * Uses <span> instead of <a> so it can safely live inside a parent <a> card.
 * Click opens the Pexels page in a new tab via window.open.
 */
export default function PhotoCredit({ attribution }: { attribution: string | null }) {
  if (!attribution) return null;

  const [label, url] = attribution.split("|");
  if (!label) return null;

  function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    window.open(url ?? "https://www.pexels.com", "_blank", "noopener,noreferrer");
  }

  return (
    <span
      role="link"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={(e) => e.key === "Enter" && handleClick(e as unknown as React.MouseEvent)}
      className="absolute bottom-1.5 right-2 cursor-pointer rounded bg-black/50 px-1.5 py-0.5 text-[9px] text-white/60 backdrop-blur-sm transition hover:text-white/90"
    >
      {label}
    </span>
  );
}
