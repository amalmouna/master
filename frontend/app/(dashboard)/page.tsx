import { Users, AlertTriangle, TrendingUp, Layers, TriangleAlert } from "lucide-react";
import { StatCard } from "@/components/ui/StatCard";
import {
  getLatestDataset,
  getRiskSummary,
  getSubjectSignals,
  extractEtablissementSignals,
} from "@/lib/supabase/queries";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

export default async function OverviewPage() {
  const dataset = await getLatestDataset();

  if (!dataset) {
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

  const [risk, subjectSignals] = await Promise.all([
    getRiskSummary(dataset.id),
    getSubjectSignals(dataset.id),
  ]);
  const etablissementSignals = extractEtablissementSignals(subjectSignals);
  const niveaux = dataset.quality_summary?.niveaux ?? [];
  const classes = dataset.quality_summary?.classes ?? [];

  return (
    <div className="p-8 max-w-6xl">
      <div className="flex items-baseline justify-between">
        <h1 className="text-lg font-semibold">Vue d&apos;ensemble</h1>
        <span className="text-xs text-muted-foreground">
          {dataset.label} — importé le {formatDate(dataset.date_import)}
        </span>
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
          value={`${niveaux.length} niveaux`}
          sublabel={`${classes.length} classes`}
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
