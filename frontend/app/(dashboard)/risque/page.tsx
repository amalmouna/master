import Link from "next/link";
import { FilterBar } from "@/components/filters/FilterBar";
import {
  getAvailableAcademicYears,
  getDatasetIdsForYear,
  resolveSelectedAnnee,
  getStudentsJoined,
  getFilterOptions,
  applyStudentFilters,
  getPredictionsByStudent,
  type StudentJoined,
} from "@/lib/supabase/queries";

interface AtRiskRow extends StudentJoined {
  probabilite_risque: number | null;
}

export default async function RisquePage({
  searchParams,
}: {
  searchParams: Promise<{ niveau?: string; classe?: string; annee?: string }>;
}) {
  const { niveau, classe, annee } = await searchParams;
  const anneesScolaires = await getAvailableAcademicYears();

  if (anneesScolaires.length === 0) {
    return (
      <div className="p-8">
        <h1 className="text-lg font-semibold">Élèves à risque</h1>
        <p className="mt-2 text-sm text-muted-foreground">Aucun import chargé.</p>
      </div>
    );
  }

  const selectedAnnee = resolveSelectedAnnee(annee, anneesScolaires);
  const datasetIds = await getDatasetIdsForYear(selectedAnnee);

  const [students, predictions] = await Promise.all([
    getStudentsJoined(datasetIds),
    getPredictionsByStudent(datasetIds),
  ]);
  const options = getFilterOptions(students);

  const atRisk: AtRiskRow[] = students
    .filter((s) => s.a_risque)
    .map((s) => ({ ...s, probabilite_risque: predictions.get(s.id)?.probabilite_risque ?? null }));

  const filtered = applyStudentFilters(atRisk, { niveau, classe }).sort(
    (a, b) => (b.probabilite_risque ?? 0) - (a.probabilite_risque ?? 0)
  );

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">Élèves à risque</h1>
        <span className="text-xs text-muted-foreground">
          {filtered.length} élève(s) à risque sur {applyStudentFilters(students, { niveau, classe }).length} dans le périmètre
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">Élèves à risque uniquement.</p>

      <div className="mt-4">
        <FilterBar
          niveaux={options.niveaux}
          classesByNiveau={options.classesByNiveau}
          profils={options.profils}
          anneesScolaires={anneesScolaires}
          selectedAnnee={selectedAnnee}
          enabled={{ annee: true, niveau: true, classe: true, profil: false }}
        />
      </div>

      <section className="mt-6 rounded-lg border border-border bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-2 font-medium">Élève</th>
              <th className="px-4 py-2 font-medium">Année</th>
              <th className="px-4 py-2 font-medium">Niveau</th>
              <th className="px-4 py-2 font-medium">Classe</th>
              <th className="px-4 py-2 font-medium">Profil</th>
              <th className="px-4 py-2 font-medium">Moyenne</th>
              <th className="px-4 py-2 font-medium">Probabilité de risque</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-muted-foreground">
                  Aucun élève à risque dans ce périmètre.
                </td>
              </tr>
            )}
            {filtered.map((s) => (
              <tr key={s.id} className="border-t border-border hover:bg-background">
                <td className="px-4 py-2">
                  <Link
                    href={`/eleves/${s.student_pseudo}?annee=${encodeURIComponent(s.academic_year)}`}
                    className="font-medium text-accent hover:underline"
                  >
                    {s.nom_complet ?? s.student_pseudo.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-2 text-muted-foreground">{s.academic_year}</td>
                <td className="px-4 py-2 text-muted-foreground">{s.niveau}</td>
                <td className="px-4 py-2 text-muted-foreground">{s.classe}</td>
                <td className="px-4 py-2 text-muted-foreground">{s.cluster_label ?? "—"}</td>
                <td className="px-4 py-2 tabular-nums">
                  {s.moyenne_generale !== null ? `${s.moyenne_generale.toFixed(2)}/20` : "—"}
                </td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-16 rounded-full bg-border">
                      <div
                        className="h-1.5 rounded-full bg-danger"
                        style={{ width: `${Math.min((s.probabilite_risque ?? 0) * 100, 100)}%` }}
                      />
                    </div>
                    <span className="tabular-nums">
                      {s.probabilite_risque !== null ? `${(s.probabilite_risque * 100).toFixed(0)}%` : "—"}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
