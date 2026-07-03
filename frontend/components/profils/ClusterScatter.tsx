import type { ClusterPoint } from "@/lib/supabase/queries";

const CLUSTER_COLORS: Record<string, string> = {
  performant: "#256d3b",
  "équilibré": "#3b5bdb",
  "équilibré fragile": "#9a6300",
  "scientifique fragile": "#c0362c",
  "linguistique fragile": "#c0362c",
  "irrégulier": "#8a4fb0",
};
const FALLBACK_COLOR = "#5b6472";

const WIDTH = 320;
const HEIGHT = 220;
const PADDING = 16;

export function ClusterScatter({ points }: { points: ClusterPoint[] }) {
  const withCoords = points.filter((p) => p.pca_1 !== null && p.pca_2 !== null);
  if (withCoords.length === 0) {
    return <p className="text-sm text-muted-foreground">Pas de coordonnées à afficher.</p>;
  }

  const xs = withCoords.map((p) => p.pca_1 as number);
  const ys = withCoords.map((p) => p.pca_2 as number);
  const [xMin, xMax] = [Math.min(...xs), Math.max(...xs)];
  const [yMin, yMax] = [Math.min(...ys), Math.max(...ys)];
  const scaleX = (v: number) =>
    PADDING + ((v - xMin) / (xMax - xMin || 1)) * (WIDTH - 2 * PADDING);
  const scaleY = (v: number) =>
    HEIGHT - PADDING - ((v - yMin) / (yMax - yMin || 1)) * (HEIGHT - 2 * PADDING);

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-auto">
      <rect x={0} y={0} width={WIDTH} height={HEIGHT} fill="var(--surface)" />
      {withCoords.map((p) => (
        <circle
          key={p.student_id}
          cx={scaleX(p.pca_1 as number)}
          cy={scaleY(p.pca_2 as number)}
          r={2.5}
          fill={CLUSTER_COLORS[p.cluster_label] ?? FALLBACK_COLOR}
          opacity={0.75}
        />
      ))}
    </svg>
  );
}

export function ClusterLegend({ labels }: { labels: string[] }) {
  return (
    <div className="flex flex-wrap gap-3">
      {labels.map((label) => (
        <div key={label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: CLUSTER_COLORS[label] ?? FALLBACK_COLOR }}
          />
          {label}
        </div>
      ))}
    </div>
  );
}
