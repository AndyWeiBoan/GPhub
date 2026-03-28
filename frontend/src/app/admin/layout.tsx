"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const NAV_ITEMS = [
  { href: "/admin", label: "Dashboard", icon: "⬛" },
  { href: "/admin/crawl", label: "爬蟲觸發", icon: "🕷" },
  { href: "/admin/sources", label: "來源管理", icon: "📡" },
  { href: "/admin/data", label: "資料管理", icon: "🗑" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-[calc(100vh-57px)]">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-white/5 bg-[#0d0f16] px-3 py-6">
        <p className="mb-4 px-3 text-[11px] font-semibold uppercase tracking-widest text-gray-500">
          Backoffice
        </p>
        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ href, label, icon }) => {
            const active =
              href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition",
                  active
                    ? "bg-violet-500/20 text-violet-300 font-medium"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                )}
              >
                <span className="text-base">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto px-8 py-8">
        {children}
      </main>
    </div>
  );
}
