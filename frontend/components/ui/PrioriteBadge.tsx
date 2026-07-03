const STYLES: Record<number, string> = {
  1: "bg-danger-bg text-danger",
  2: "bg-warning-bg text-warning",
  3: "bg-background text-muted-foreground border border-border",
};

export function PrioriteBadge({ priorite }: { priorite: number }) {
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${STYLES[priorite] ?? STYLES[3]}`}>
      Priorité {priorite}
    </span>
  );
}
