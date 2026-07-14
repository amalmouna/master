import Link from "next/link";
import { FilterBar } from "@/components/filters/FilterBar";
import {
  getAvailableAcademicYears,
  getDatasetIdsForYear,
  resolveSelectedAnnee,
  getStudentsJoined,
  getFilterOptions,
} from "@/lib/supabase/queries";

export default async function ClassesIndexPage({
  searchParams,
}: {
  searchParams: Promise<{ niveau?: string; annee?: string }>;
}) {
  const { niveau, annee } = await searchParams;
  const anneesScolaires = await getAvailableAcademicYears();

  if (anneesScolaires.length === 0) {
    return (
      <div className="p-8">
        <h1 className="text-lg font-semibold">Classes</h1>
        <p className="mt-2 text-sm text-muted-foreground">Aucun import chargé.</p>
      </div>
    );
  }

  const selectedAnnee = resolveSelectedAnnee(annee, anneesScolaires);
  const datasetIds = await getDatasetIdsForYear(selectedAnnee);
  const students = await getStudentsJoined(datasetIds);
  const options = getFilterOptions(students);

  const niveaux = niveau ? [niveau] : options.niveaux;

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-lg font-semibold">Classes</h1>
      <p className="mt-1 text-xs text-muted-foreground">
        Sélectionnez une classe pour voir quelles matières ont déjà des notes importées.
      </p>

      <div className="mt-4">
        <FilterBar
          niveaux={options.niveaux}
          classesByNiveau={options.classesByNiveau}
          profils={[]}
          anneesScolaires={anneesScolaires}
          selectedAnnee={selectedAnnee}
          enabled={{ annee: true, niveau: true, classe: false, profil: false }}
        />
      </div>

      <div className="mt-6 space-y-4">
        {niveaux.map((n) => (
          <section key={n} className="rounded-lg border border-border bg-surface">
            <h2 className="border-b border-border px-4 py-2 text-sm font-semibold">{n}</h2>
            <div className="flex flex-wrap gap-2 p-3">
              {(options.classesByNiveau[n] ?? []).map((c) => (
                <Link
                  key={c}
                  href={`/classes/${encodeURIComponent(c)}?annee=${encodeURIComponent(selectedAnnee)}`}
                  className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-accent hover:underline"
                >
                  {c}
                </Link>
              ))}
              {(options.classesByNiveau[n] ?? []).length === 0 && (
                <p className="text-sm text-muted-foreground">Aucune classe pour ce niveau.</p>
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
