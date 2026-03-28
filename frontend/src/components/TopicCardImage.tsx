"use client";
import { useState } from "react";

interface Props {
  src: string;
  gradient: string;
  className?: string;
}

/**
 * Renders a topic card background image with automatic fallback to
 * a category gradient if the image fails to load or is unavailable.
 * Needed because some OG images (e.g. Dev.to) have white backgrounds
 * that look broken on dark cards.
 */
export default function TopicCardImage({ src, gradient, className = "" }: Props) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return <span className={`absolute inset-0 bg-gradient-to-br ${gradient} ${className}`} />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      onError={() => setFailed(true)}
      className={`absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03] ${className}`}
    />
  );
}
