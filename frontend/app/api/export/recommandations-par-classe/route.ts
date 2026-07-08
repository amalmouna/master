import { createSupabaseServerClient } from "@/lib/supabase/server";
import {
  getAvailableAcademicYears,
  getDatasetIdsForYear,
  resolveSelectedAnnee,
  getRecommendationsForExport,
} from "@/lib/supabase/queries";
import { buildCsv } from "@/lib/export/csv";
import { buildPdf } from "@/lib/export/pdf";
import { anneeForFilename, anneeForHeader } from "@/lib/export/filenames";
import { exportHeaders } from "@/lib/export/response";

export const dynamic = "force-dynamic";

const PRIORITE_LABEL: Record<number, string> = { 1: "Priorité 1", 2: "Priorité 2", 3: "Priorité 3" };

/** Export "plans de remédiation par classe" (§2.7). Périmètre décidé par
 * RLS via getRecommendationsForExport (createSupabaseServerClient) — un
 * scoped_user ne reçoit que les recommandations des élèves de ses classes. */
export async function GET(request: Request) {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return new Response("Non authentifié.", { status: 401 });

  const url = new URL(request.url);
  const format = url.searchParams.get("format") === "pdf" ? "pdf" : "csv";
  const anneeParam = url.searchParams.get("annee") || undefined;

  const anneesScolaires = await getAvailableAcademicYears();
  const selectedAnnee = resolveSelectedAnnee(anneeParam, anneesScolaires);
  const datasetIds = await getDatasetIdsForYear(selectedAnnee);

  const recommendations = await getRecommendationsForExport(datasetIds);

  const headerLine = anneeForHeader(selectedAnnee);
  const filenameBase = `recommandations_par_classe_${anneeForFilename(selectedAnnee)}`;

  if (format === "csv") {
    const csv = buildCsv(
      ["Classe", "Niveau", "Année scolaire", "Élève", "Priorité", "Type", "Justification", "Action", "Matières concernées"],
      recommendations.map((r) => [
        r.classe,
        r.niveau,
        r.academic_year,
        r.nom_complet ?? r.student_pseudo,
        r.priorite,
        r.type,
        r.justification,
        r.action,
        r.matieres_concernees.join(" | "),
      ])
    );
    return new Response(csv, { headers: exportHeaders("text/csv; charset=utf-8", `${filenameBase}.csv`) });
  }

  const byClasse = new Map<string, typeof recommendations>();
  for (const r of recommendations) {
    (byClasse.get(r.classe) ?? byClasse.set(r.classe, []).get(r.classe)!).push(r);
  }

  const pdf = buildPdf(
    "Plans de remédiation par classe",
    headerLine,
    [...byClasse.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([classe, rows]) => ({
        title: classe,
        head: ["Élève", "Priorité", "Type", "Justification", "Action", "Matières"],
        body: rows.map((r) => [
          r.nom_complet ?? r.student_pseudo,
          PRIORITE_LABEL[r.priorite] ?? String(r.priorite),
          r.type,
          r.justification,
          r.action,
          r.matieres_concernees.join(", "),
        ]),
      }))
  );
  return new Response(pdf, { headers: exportHeaders("application/pdf", `${filenameBase}.pdf`) });
}
