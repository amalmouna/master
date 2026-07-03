import type { LucideIcon } from "lucide-react";

export function StatCard({
  icon: Icon,
  label,
  value,
  sublabel,
  tone = "default",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  sublabel?: string;
  tone?: "default" | "danger";
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon size={15} strokeWidth={2} />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div
        className={`mt-2 text-2xl font-semibold ${
          tone === "danger" ? "text-danger" : "text-foreground"
        }`}
      >
        {value}
      </div>
      {sublabel && <div className="mt-1 text-xs text-muted-foreground">{sublabel}</div>}
    </div>
  );
}
