"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, BarChart3, AlertTriangle, Boxes } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Vue d'ensemble", icon: LayoutDashboard },
  { href: "/matieres", label: "Moyennes par matière", icon: BarChart3 },
  { href: "/risque", label: "Élèves à risque", icon: AlertTriangle },
  { href: "/profils", label: "Profils", icon: Boxes },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 shrink-0 border-r border-border bg-surface flex flex-col">
      <div className="h-14 flex items-center px-4 border-b border-border">
        <span className="text-sm font-semibold tracking-tight">
          Analyse pédagogique
        </span>
      </div>
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors ${
                active
                  ? "bg-accent/10 text-accent font-medium"
                  : "text-muted-foreground hover:bg-background hover:text-foreground"
              }`}
            >
              <Icon size={16} strokeWidth={2} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
