import { Users, AlertTriangle, TrendingUp, Layers, TriangleAlert } from "lucide-react";
import { StatCard } from "@/components/ui/StatCard";
import { FilterBar } from "@/components/filters/FilterBar";
import {
  getAvailableAcademicYears,
  getDatasetIdsForYear,
  resolveSelectedAnnee,
  getStudentsJoined,
  getFilterOptions,
  getRiskSummary,
  getSubjectSignals,
  extractEtablissementSignals,
  TOUTES_LES_ANNEES,
} from "@/lib/supabase/queries";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ annee?: string }>;
}) {
  const { annee } = await searchParams;
  const anneesScolaires = await getAvailableAcademicYears();

  if (anneesScolaires.length === 0) {
    return (
      <div className="p-8">
        <h1 className="text-lg font-semibold">Vue d&apos;ensemble</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Aucun import chargé. Exécutez le loader (src/persistence/load_to_supabase.py)
          pour alimenter le tableau de bord.
        </p>
      </div>
    );
  }

  const selectedAnnee = resolveSelectedAnnee(annee, anneesScolaires);
  const datasetIds = await getDatasetIdsForYear(selectedAnnee);

  const [students, risk, subjectSignals] = await Promise.all([
    getStudentsJoined(datasetIds),
    getRiskSummary(datasetIds),
    getSubjectSignals(datasetIds),
  ]);
  const etablissementSignals = extractEtablissementSignals(subjectSignals);
  const options = getFilterOptions(students);

  return (
    <div className="p-8 max-w-6xl">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">Vue d&apos;ensemble</h1>
        {selectedAnnee === TOUTES_LES_ANNEES && (
          <span className="text-xs text-muted-foreground">
            Toutes années confondues — un élève déjà importé plusieurs années compte une fois par année.
          </span>
        )}
      </div>

      <div className="mt-4">
        <FilterBar
          niveaux={options.niveaux}
          classesByNiveau={options.classesByNiveau}
          profils={options.profils}
          anneesScolaires={anneesScolaires}
          selectedAnnee={selectedAnnee}
          enabled={{ annee: true }}
        />
      </div>

      <div className="mt-6 grid grid-cols-4 gap-4">
        <StatCard icon={Users} label="Élèves" value={String(risk.n_eleves)} />
        <StatCard
          icon={AlertTriangle}
          label="Taux de risque"
          value={`${risk.pct_a_risque.toFixed(1)}%`}
          sublabel={`${risk.n_a_risque} élève(s)`}
          tone="danger"
        />
        <StatCard
          icon={TrendingUp}
          label="Moyenne générale"
          value={risk.moyenne_generale !== null ? `${risk.moyenne_generale.toFixed(2)}/20` : "—"}
        />
        <StatCard
          icon={Layers}
          label="Périmètre"
          value={`${options.niveaux.length} niveaux`}
          sublabel={`${Object.values(options.classesByNiveau).flat().length} classes`}
        />
      </div>

      {etablissementSignals.length > 0 && (
        <div className="mt-6 rounded-lg border border-warning-bg bg-warning-bg p-4">
          <div className="flex items-center gap-2 text-warning">
            <TriangleAlert size={16} strokeWidth={2} />
            <span className="text-sm font-semibold">Signaux établissement</span>
          </div>
          <ul className="mt-2 space-y-1">
            {etablissementSignals.map((s) => (
              <li key={s.matiere} className="text-sm text-foreground">
                {s.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6 grid grid-cols-2 gap-6">
        <section className="rounded-lg border border-border bg-surface">
          <h2 className="border-b border-border px-4 py-3 text-sm font-semibold">
            Risque par niveau
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2 font-medium">Niveau</th>
                <th className="px-4 py-2 font-medium">Élèves</th>
                <th className="px-4 py-2 font-medium">À risque</th>
                <th className="px-4 py-2 font-medium">Taux</th>
              </tr>
            </thead>
            <tbody>
              {risk.par_niveau.map((row) => (
                <tr key={row.niveau} className="border-t border-border">
                  <td className="px-4 py-2 font-medium">{row.niveau}</td>
                  <td className="px-4 py-2 text-muted-foreground">{row.n}</td>
                  <td className="px-4 py-2 text-muted-foreground">{row.n_a_risque}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 rounded-full bg-border">
                        <div
                          className="h-1.5 rounded-full bg-danger"
                          style={{ width: `${Math.min(row.pct_a_risque, 100)}%` }}
                        />
                      </div>
                      <span className="tabular-nums">{row.pct_a_risque.toFixed(1)}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <h2 className="border-b border-border px-4 py-3 text-sm font-semibold">
            Matières les plus problématiques
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2 font-medium">Matière</th>
                <th className="px-4 py-2 font-medium">Moyenne</th>
                <th className="px-4 py-2 font-medium">% sous 10</th>
              </tr>
            </thead>
            <tbody>
              {subjectSignals.slice(0, 5).map((s) => (
                <tr
                  key={s.code}
                  className={`border-t border-border ${
                    s.pct_sous_10 > 50 ? "bg-danger-bg/40" : ""
                  }`}
                >
                  <td className="px-4 py-2 font-medium">{s.nom_fr}</td>
                  <td className="px-4 py-2 text-muted-foreground">{s.moyenne.toFixed(2)}/20</td>
                  <td className="px-4 py-2 tabular-nums">{s.pct_sous_10.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
