import type { TrajectoryYear, SubjectTrajectory } from "@/lib/supabase/queries";

const WIDTH = 220;
const HEIGHT = 48;
const PADDING = 4;
const NOTE_MIN = 0;
const NOTE_MAX = 20; // échelle fixe (notes /20) : comparable d'une matière à l'autre, pas auto-ajustée

function Sparkline({ points }: { points: { academic_year: string; moyenne_matiere: number | null }[] }) {
  const withValue = points
    .map((p, i) => ({ ...p, i }))
    .filter((p): p is typeof p & { moyenne_matiere: number } => p.moyenne_matiere !== null);

  if (withValue.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  const scaleX = (i: number) =>
    points.length > 1
      ? PADDING + (i / (points.length - 1)) * (WIDTH - 2 * PADDING)
      : WIDTH / 2;
  const scaleY = (v: number) =>
    HEIGHT - PADDING - ((v - NOTE_MIN) / (NOTE_MAX - NOTE_MIN)) * (HEIGHT - 2 * PADDING);

  const path = withValue
    .map((p, idx) => `${idx === 0 ? "M" : "L"} ${scaleX(p.i)} ${scaleY(p.moyenne_matiere)}`)
    .join(" ");

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-12 w-full max-w-[220px]">
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
      {withValue.map((p) => (
        <circle key={p.academic_year} cx={scaleX(p.i)} cy={scaleY(p.moyenne_matiere)} r={2} fill="var(--accent)" />
      ))}
    </svg>
  );
}

export function Trajectory({
  years,
  subjects,
}: {
  years: TrajectoryYear[];
  subjects: SubjectTrajectory[];
}) {
  if (years.length < 2) {
    return (
      <section className="mt-6 rounded-lg border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Progression</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Historique disponible à partir du deuxième import annuel.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-lg border border-border bg-surface">
      <h2 className="border-b border-border px-4 py-3 text-sm font-semibold">
        Progression ({years.length} années)
      </h2>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2 font-medium">Année</th>
            <th className="px-4 py-2 font-medium">Niveau</th>
            <th className="px-4 py-2 font-medium">Classe</th>
            <th className="px-4 py-2 font-medium">Moyenne générale</th>
            <th className="px-4 py-2 font-medium">Statut</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => (
            <tr key={y.academic_year} className="border-t border-border">
              <td className="px-4 py-2 font-medium">{y.academic_year}</td>
              <td className="px-4 py-2 text-muted-foreground">{y.niveau}</td>
              <td className="px-4 py-2 text-muted-foreground">{y.classe}</td>
              <td className="px-4 py-2 tabular-nums">
                {y.moyenne_generale !== null ? `${y.moyenne_generale.toFixed(2)}/20` : "—"}
              </td>
              <td className="px-4 py-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                    y.a_risque ? "bg-danger-bg text-danger" : "bg-success-bg text-success"
                  }`}
                >
                  {y.a_risque ? "À risque" : "Non à risque"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {subjects.length > 0 && (
        <div className="border-t border-border p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Moyenne par matière, d&apos;année en année
          </h3>
          <div className="mt-3 grid grid-cols-2 gap-4">
            {subjects.map((s) => (
              <div key={s.subject_code} className="rounded-md border border-border p-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">{s.subject_nom_fr}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {s.points.map((p) => (p.moyenne_matiere !== null ? p.moyenne_matiere.toFixed(1) : "—")).join(" → ")}
                  </span>
                </div>
                <Sparkline points={s.points} />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
