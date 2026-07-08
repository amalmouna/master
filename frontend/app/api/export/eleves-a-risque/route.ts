import { createSupabaseServerClient } from "@/lib/supabase/server";
import {
  getAvailableAcademicYears,
  getDatasetIdsForYear,
  resolveSelectedAnnee,
  getStudentsJoined,
  getPredictionsByStudent,
  applyStudentFilters,
} from "@/lib/supabase/queries";
import { buildCsv } from "@/lib/export/csv";
import { buildPdf } from "@/lib/export/pdf";
import { anneeForFilename, anneeForHeader } from "@/lib/export/filenames";
import { exportHeaders } from "@/lib/export/response";

// Jamais mis en cache (données nominatives) ; toujours évalué à la requête,
// donc toujours re-vérifié contre la session/RLS de l'appelant courant.
export const dynamic = "force-dynamic";

/** Export "élèves à risque" (§2.7), pour le filtre courant de la page
 * /risque (année, niveau, classe). Le périmètre est décidé par RLS, pas ici
 * : getStudentsJoined passe par createSupabaseServerClient (cookies de
 * session), donc un scoped_user ne reçoit jamais que ses classes — aucun
 * filtrage de sécurité supplémentaire à faire côté application. */
export async function GET(request: Request) {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return new Response("Non authentifié.", { status: 401 });

  const url = new URL(request.url);
  const format = url.searchParams.get("format") === "pdf" ? "pdf" : "csv";
  const niveau = url.searchParams.get("niveau") || undefined;
  const classe = url.searchParams.get("classe") || undefined;
  const anneeParam = url.searchParams.get("annee") || undefined;

  const anneesScolaires = await getAvailableAcademicYears();
  const selectedAnnee = resolveSelectedAnnee(anneeParam, anneesScolaires);
  const datasetIds = await getDatasetIdsForYear(selectedAnnee);

  const [students, predictions] = await Promise.all([
    getStudentsJoined(datasetIds),
    getPredictionsByStudent(datasetIds),
  ]);

  const atRisk = students
    .filter((s) => s.a_risque)
    .map((s) => ({ ...s, probabilite_risque: predictions.get(s.id)?.probabilite_risque ?? null }));
  const filtered = applyStudentFilters(atRisk, { niveau, classe }).sort(
    (a, b) => (b.probabilite_risque ?? 0) - (a.probabilite_risque ?? 0)
  );

  const headerLine = anneeForHeader(selectedAnnee);
  const filenameBase = `eleves_a_risque_${anneeForFilename(selectedAnnee)}`;

  if (format === "csv") {
    const csv = buildCsv(
      ["Élève", "Année scolaire", "Niveau", "Classe", "Profil", "Moyenne générale", "Probabilité de risque (%)"],
      filtered.map((s) => [
        s.nom_complet ?? s.student_pseudo,
        s.academic_year,
        s.niveau,
        s.classe,
        s.cluster_label ?? "",
        s.moyenne_generale !== null ? s.moyenne_generale.toFixed(2) : "",
        s.probabilite_risque !== null ? (s.probabilite_risque * 100).toFixed(0) : "",
      ])
    );
    return new Response(csv, { headers: exportHeaders("text/csv; charset=utf-8", `${filenameBase}.csv`) });
  }

  const pdf = buildPdf("Élèves à risque", headerLine, [
    {
      head: ["Élève", "Année", "Niveau", "Classe", "Profil", "Moyenne", "Risque (%)"],
      body: filtered.map((s) => [
        s.nom_complet ?? s.student_pseudo,
        s.academic_year,
        s.niveau,
        s.classe,
        s.cluster_label ?? "—",
        s.moyenne_generale !== null ? s.moyenne_generale.toFixed(2) : "—",
        s.probabilite_risque !== null ? (s.probabilite_risque * 100).toFixed(0) : "—",
      ]),
    },
  ]);
  return new Response(pdf, { headers: exportHeaders("application/pdf", `${filenameBase}.pdf`) });
}
