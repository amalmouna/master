import { FilterBar } from "@/components/filters/FilterBar";
import {
  getLatestDataset,
  getStudentsJoined,
  getFilterOptions,
  applyStudentFilters,
  getSubjectSignals,
} from "@/lib/supabase/queries";
import { DOMAINE_FR } from "@/lib/constants";

export default async function MatieresPage({
  searchParams,
}: {
  searchParams: Promise<{ niveau?: string; classe?: string; profil?: string }>;
}) {
  const { niveau, classe, profil } = await searchParams;
  const dataset = await getLatestDataset();

  if (!dataset) {
    return (
      <div className="p-8">
        <h1 className="text-lg font-semibold">Moyennes par matière</h1>
        <p className="mt-2 text-sm text-muted-foreground">Aucun import chargé.</p>
      </div>
    );
  }

  const students = await getStudentsJoined(dataset.id);
  const options = getFilterOptions(students);
  const filtered = applyStudentFilters(students, { niveau, classe, profil });
  const filteredIds = new Set(filtered.map((s) => s.id));
  const signals = await getSubjectSignals(dataset.id, filteredIds);

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">Moyennes par matière</h1>
        <span className="text-xs text-muted-foreground">{filtered.length} élève(s) dans le périmètre</span>
      </div>

      <div className="mt-4">
        <FilterBar
          niveaux={options.niveaux}
          classesByNiveau={options.classesByNiveau}
          profils={options.profils}
          enabled={{ niveau: true, classe: true, profil: true }}
        />
      </div>

      <section className="mt-6 rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-2 font-medium">Matière</th>
              <th className="px-4 py-2 font-medium">Domaine</th>
              <th className="px-4 py-2 font-medium">Élèves suivis</th>
              <th className="px-4 py-2 font-medium">Moyenne</th>
              <th className="px-4 py-2 font-medium">% sous 10</th>
              <th className="px-4 py-2 font-medium">% sous 8</th>
            </tr>
          </thead>
          <tbody>
            {signals.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  Aucun élève ne correspond à ce filtre.
                </td>
              </tr>
            )}
            {signals.map((s) => (
              <tr
                key={s.code}
                className={`border-t border-border ${s.pct_sous_10 > 50 ? "bg-danger-bg/40" : ""}`}
              >
                <td className="px-4 py-2 font-medium">{s.nom_fr}</td>
                <td className="px-4 py-2 text-muted-foreground">{DOMAINE_FR[s.domaine] ?? s.domaine}</td>
                <td className="px-4 py-2 text-muted-foreground">{s.n_suivi}</td>
                <td className="px-4 py-2 tabular-nums">{s.moyenne.toFixed(2)}/20</td>
                <td className="px-4 py-2 tabular-nums">{s.pct_sous_10.toFixed(1)}%</td>
                <td className="px-4 py-2 tabular-nums text-muted-foreground">
                  {s.pct_sous_8.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
