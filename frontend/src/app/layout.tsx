import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GPhub — Curated AI Intelligence Daily",
  description: "Top AI news, research papers, tools and GitHub projects — scored and summarised twice a day.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <nav className="sticky top-0 z-50 border-b border-white/5 bg-[#0f1117]/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
            <div className="flex items-center gap-2">
              <a href="/" className="flex items-center gap-2 transition hover:opacity-80">
                <span className="text-2xl font-black tracking-tight text-white">GPhub</span>
                <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-xs font-medium text-violet-400">
                  Daily
                </span>
              </a>
            </div>
            <div className="flex items-center gap-6 text-sm text-gray-400">
              <a href="/" className="transition hover:text-white">Feed</a>
              <a href="/browse" className="transition hover:text-white">Browse</a>
              <a href="/admin" className="transition hover:text-white text-gray-600 hover:text-gray-300">Admin</a>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
