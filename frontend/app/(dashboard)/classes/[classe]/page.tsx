import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  getAvailableAcademicYears,
  getDatasetIdsForYear,
  resolveSelectedAnnee,
  getClassCoverage,
} from "@/lib/supabase/queries";

export default async function ClasseDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ classe: string }>;
  searchParams: Promise<{ annee?: string }>;
}) {
  const { classe: classeParam } = await params;
  const classe = decodeURIComponent(classeParam);
  const { annee } = await searchParams;
  const anneesScolaires = await getAvailableAcademicYears();

  if (anneesScolaires.length === 0) {
    return (
      <div className="p-8">
        <p className="text-sm text-muted-foreground">Aucun import chargé.</p>
      </div>
    );
  }

  const selectedAnnee = resolveSelectedAnnee(annee, anneesScolaires);
  const datasetIds = await getDatasetIdsForYear(selectedAnnee);
  const { eleves, matieres } = await getClassCoverage(datasetIds, classe);

  return (
    <div className="p-8 max-w-5xl">
      <Link href="/classes" className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
        <ArrowLeft size={14} /> Retour
      </Link>

      <div className="mt-3 flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">{classe}</h1>
        <span className="text-xs text-muted-foreground">
          Année {selectedAnnee} · {eleves.length} élève(s)
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Une cellule vide (—) signifie qu&apos;aucun fichier n&apos;a encore été importé pour cette
        matière et cet élève — un fichier Massar à la fois suffit (§10, import additif).
      </p>

      {eleves.length === 0 ? (
        <p className="mt-6 text-sm text-muted-foreground">
          Aucun élève trouvé pour cette classe et cette année.
        </p>
      ) : (
        <section className="mt-6 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-2 font-medium sticky left-0 bg-surface">Élève</th>
                {matieres.map((m) => (
                  <th key={m.code} className="px-4 py-2 font-medium whitespace-nowrap">
                    {m.nom_fr}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {eleves.map((e) => (
                <tr key={e.student_id} className="border-t border-border">
                  <td className="px-4 py-2 font-medium sticky left-0 bg-surface">
                    {e.nom_complet ?? e.student_pseudo.slice(0, 8)}
                  </td>
                  {matieres.map((m) => {
                    const v = e.parMatiere[m.code];
                    return (
                      <td key={m.code} className="px-4 py-2 tabular-nums text-center">
                        {v !== null && v !== undefined ? (
                          v.toFixed(2)
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
