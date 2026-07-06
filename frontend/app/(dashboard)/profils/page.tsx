import { FilterBar } from "@/components/filters/FilterBar";
import { ClusterScatter, ClusterLegend } from "@/components/profils/ClusterScatter";
import {
  getLatestDataset,
  getStudentsJoined,
  getFilterOptions,
  getClusterPoints,
  summarizeClusters,
} from "@/lib/supabase/queries";

export default async function ProfilsPage({
  searchParams,
}: {
  searchParams: Promise<{ niveau?: string; classe?: string }>;
}) {
  const { niveau, classe } = await searchParams;
  const dataset = await getLatestDataset();

  if (!dataset) {
    return (
      <div className="p-8">
        <h1 className="text-lg font-semibold">Profils</h1>
        <p className="mt-2 text-sm text-muted-foreground">Aucun import chargé.</p>
      </div>
    );
  }

  const [students, points] = await Promise.all([
    getStudentsJoined(dataset.id),
    getClusterPoints(dataset.id),
  ]);
  const options = getFilterOptions(students);

  const filteredPoints = points.filter(
    (p) => (!niveau || p.niveau === niveau) && (!classe || p.classe === classe)
  );
  const summary = summarizeClusters(filteredPoints);
  const niveauxAffiches = niveau ? [niveau] : options.niveaux;

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-lg font-semibold">Profils</h1>

      <div className="mt-4">
        <FilterBar
          niveaux={options.niveaux}
          classesByNiveau={options.classesByNiveau}
          profils={options.profils}
          enabled={{ niveau: true, classe: true }}
        />
      </div>

      <p className="mt-4 text-xs text-muted-foreground">
        Le regroupement en profils est réalisé séparément par niveau (les matières
        suivies diffèrent selon le niveau) — les profils ne sont donc comparables
        qu&apos;au sein d&apos;un même niveau.
      </p>

      <div className="mt-4 space-y-6">
        {niveauxAffiches.map((niv) => {
          const niveauPoints = filteredPoints.filter((p) => p.niveau === niv);
          const niveauSummary = summary.filter((s) => s.niveau === niv);
          if (niveauPoints.length === 0) return null;
          const labels = [...new Set(niveauPoints.map((p) => p.cluster_label))];

          return (
            <section key={niv} className="rounded-lg border border-border bg-surface p-4">
              <h2 className="text-sm font-semibold">{niv}</h2>
              <div className="mt-3 grid grid-cols-[1fr_320px] gap-6">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="py-2 font-medium">Profil</th>
                      <th className="py-2 font-medium">Élèves</th>
                      <th className="py-2 font-medium">Moyenne</th>
                      <th className="py-2 font-medium">Dispersion</th>
                      <th className="py-2 font-medium">% à risque</th>
                    </tr>
                  </thead>
                  <tbody>
                    {niveauSummary.map((s) => (
                      <tr key={s.cluster_label} className="border-t border-border">
                        <td className="py-2 font-medium">{s.cluster_label}</td>
                        <td className="py-2 text-muted-foreground">{s.n}</td>
                        <td className="py-2 tabular-nums">
                          {s.moyenne_generale !== null ? `${s.moyenne_generale.toFixed(2)}/20` : "—"}
                        </td>
                        <td className="py-2 tabular-nums text-muted-foreground">
                          {s.dispersion_intermatiere !== null ? s.dispersion_intermatiere.toFixed(2) : "—"}
                        </td>
                        <td className="py-2 tabular-nums">{s.pct_a_risque.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div>
                  <ClusterScatter points={niveauPoints} />
                  <div className="mt-2">
                    <ClusterLegend labels={labels} />
                  </div>
                </div>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
