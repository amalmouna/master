import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PrioriteBadge } from "@/components/ui/PrioriteBadge";
import { DOMAINE_FR } from "@/lib/constants";
import { getLatestDataset, getStudentDetail } from "@/lib/supabase/queries";

function formatNote(v: number | null): string {
  return v !== null ? v.toFixed(2) : "—";
}

export default async function FicheElevePage({
  params,
}: {
  params: Promise<{ pseudo: string }>;
}) {
  const { pseudo } = await params;
  const dataset = await getLatestDataset();

  if (!dataset) {
    return (
      <div className="p-8">
        <p className="text-sm text-muted-foreground">Aucun import chargé.</p>
      </div>
    );
  }

  const detail = await getStudentDetail(dataset.id, pseudo);

  if (!detail) {
    return (
      <div className="p-8">
        <Link href="/risque" className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
          <ArrowLeft size={14} /> Retour
        </Link>
        <p className="mt-4 text-sm text-muted-foreground">Élève introuvable dans cet import.</p>
      </div>
    );
  }

  const { student, cluster_label, prediction, grades, recommendations } = detail;

  return (
    <div className="p-8 max-w-4xl">
      <Link href="/risque" className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
        <ArrowLeft size={14} /> Retour
      </Link>

      <div className="mt-3 flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">{student.nom_complet ?? `Élève ${student.student_pseudo.slice(0, 8)}`}</h1>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            student.a_risque ? "bg-danger-bg text-danger" : "bg-success-bg text-success"
          }`}
        >
          {student.a_risque ? "À risque" : "Non à risque"}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {student.niveau} — {student.classe}
        {cluster_label && <> · Profil {cluster_label}</>}
        {student.age !== null && <> · {student.age} ans</>}
      </p>

      <div className="mt-6 grid grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="text-xs uppercase text-muted-foreground">Moyenne générale</div>
          <div className="mt-1 text-xl font-semibold">
            {student.moyenne_generale !== null ? `${student.moyenne_generale.toFixed(2)}/20` : "—"}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="text-xs uppercase text-muted-foreground">Dispersion</div>
          <div className="mt-1 text-xl font-semibold">{formatNote(student.dispersion_intermatiere)}</div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="text-xs uppercase text-muted-foreground">Tendance</div>
          <div className="mt-1 text-xl font-semibold">{formatNote(student.tendance_globale)}</div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="text-xs uppercase text-muted-foreground">Matières suivies</div>
          <div className="mt-1 text-xl font-semibold">{student.nb_matieres_suivies ?? "—"}</div>
        </div>
      </div>

      {prediction && (
        <section className="mt-6 rounded-lg border border-border bg-surface p-4 space-y-3">
          <h2 className="text-sm font-semibold">Explication du modèle</h2>
          {prediction.explication_risque_fr && (
            <p className="text-sm">{prediction.explication_risque_fr}</p>
          )}
          {prediction.explication_moyenne_fr && (
            <p className="text-sm text-muted-foreground">{prediction.explication_moyenne_fr}</p>
          )}
          {prediction.moyenne_generale_predite !== null && (
            <div className="rounded-md bg-background px-3 py-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Tendance prévisionnelle</span> — estimation du
              modèle Ridge à partir des premiers contrôles (C1/C2), non un fait observé :{" "}
              <span className="tabular-nums">{prediction.moyenne_generale_predite.toFixed(2)}/20</span>
            </div>
          )}
        </section>
      )}

      <section className="mt-6 rounded-lg border border-border bg-surface">
        <h2 className="border-b border-border px-4 py-3 text-sm font-semibold">Notes par matière</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-2 font-medium">Matière</th>
              <th className="px-4 py-2 font-medium">Domaine</th>
              <th className="px-4 py-2 font-medium">C1</th>
              <th className="px-4 py-2 font-medium">C2</th>
              <th className="px-4 py-2 font-medium">C3</th>
              <th className="px-4 py-2 font-medium">C4</th>
              <th className="px-4 py-2 font-medium">Activités</th>
              <th className="px-4 py-2 font-medium">Moyenne</th>
              <th className="px-4 py-2 font-medium">Tendance</th>
            </tr>
          </thead>
          <tbody>
            {grades.map((g) => (
              <tr key={g.id} className="border-t border-border">
                <td className="px-4 py-2 font-medium">{g.subject_nom_fr}</td>
                <td className="px-4 py-2 text-muted-foreground">{DOMAINE_FR[g.subject_domaine] ?? g.subject_domaine}</td>
                <td className="px-4 py-2 tabular-nums">{g.c1_colonne_existe ? formatNote(g.c1) : "—"}</td>
                <td className="px-4 py-2 tabular-nums">{g.c2_colonne_existe ? formatNote(g.c2) : "—"}</td>
                <td className="px-4 py-2 tabular-nums">{g.c3_colonne_existe ? formatNote(g.c3) : "—"}</td>
                <td className="px-4 py-2 tabular-nums">{g.c4_colonne_existe ? formatNote(g.c4) : "—"}</td>
                <td className="px-4 py-2 tabular-nums">
                  {g.activites_colonne_existe ? formatNote(g.activites) : "—"}
                </td>
                <td className="px-4 py-2 tabular-nums font-medium">{formatNote(g.moyenne_matiere)}</td>
                <td className="px-4 py-2 tabular-nums text-muted-foreground">
                  {g.tendance_matiere !== null ? g.tendance_matiere.toFixed(2) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold">Recommandations</h2>
        {recommendations.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">Aucune recommandation pour cet élève.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {recommendations.map((r) => (
              <div key={r.id} className="rounded-lg border border-border bg-surface p-4">
                <div className="flex items-center gap-2">
                  <PrioriteBadge priorite={r.priorite} />
                  <span className="text-xs text-muted-foreground">{r.type}</span>
                </div>
                <p className="mt-2 text-sm">{r.justification}</p>
                <p className="mt-1 text-sm text-muted-foreground">{r.action}</p>
                {r.matieres_concernees.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {r.matieres_concernees.map((m) => (
                      <span
                        key={m}
                        className="rounded bg-background px-1.5 py-0.5 text-xs text-muted-foreground border border-border"
                      >
                        {m}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
