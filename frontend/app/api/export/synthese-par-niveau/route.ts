import { createSupabaseServerClient } from "@/lib/supabase/server";
import {
  getAvailableAcademicYears,
  getDatasetIdsForYear,
  resolveSelectedAnnee,
  getNiveauSynthese,
} from "@/lib/supabase/queries";
import { buildCsv } from "@/lib/export/csv";
import { buildPdf } from "@/lib/export/pdf";
import { anneeForFilename, anneeForHeader } from "@/lib/export/filenames";
import { exportHeaders } from "@/lib/export/response";

export const dynamic = "force-dynamic";

/** Export "synthèse par niveau" (§2.7). Périmètre décidé par RLS via
 * getNiveauSynthese (createSupabaseServerClient, réutilise getStudentsJoined)
 * — un scoped_user ne voit que la part de ses classes dans chaque niveau,
 * jamais l'établissement entier. */
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

  const synthese = await getNiveauSynthese(datasetIds);

  const headerLine = anneeForHeader(selectedAnnee);
  const filenameBase = `synthese_par_niveau_${anneeForFilename(selectedAnnee)}`;

  if (format === "csv") {
    const csv = buildCsv(
      ["Niveau", "Élèves", "À risque", "Taux de risque (%)", "Moyenne générale"],
      synthese.map((s) => [
        s.niveau,
        s.n_eleves,
        s.n_a_risque,
        s.pct_a_risque.toFixed(1),
        s.moyenne_generale !== null ? s.moyenne_generale.toFixed(2) : "",
      ])
    );
    return new Response(csv, { headers: exportHeaders("text/csv; charset=utf-8", `${filenameBase}.csv`) });
  }

  const pdf = buildPdf("Synthèse par niveau", headerLine, [
    {
      head: ["Niveau", "Élèves", "À risque", "Taux de risque (%)", "Moyenne générale"],
      body: synthese.map((s) => [
        s.niveau,
        s.n_eleves,
        s.n_a_risque,
        s.pct_a_risque.toFixed(1),
        s.moyenne_generale !== null ? `${s.moyenne_generale.toFixed(2)}/20` : "—",
      ]),
    },
  ]);
  return new Response(pdf, { headers: exportHeaders("application/pdf", `${filenameBase}.pdf`) });
}
