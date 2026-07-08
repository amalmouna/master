import { Download } from "lucide-react";

/** Liens de téléchargement directs (pas de fetch client) — le navigateur
 * navigue vers la route d'export, qui répond avec Content-Disposition:
 * attachment. Le format (CSV/PDF) et le périmètre (année/niveau/classe)
 * sont dans l'URL ; la portée réelle des données est décidée par RLS côté
 * serveur, jamais ici. */
export function ExportLinks({
  csvHref,
  pdfHref,
  label = "Exporter",
}: {
  csvHref: string;
  pdfHref: string;
  label?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Download size={12} strokeWidth={2} />
        {label}
      </span>
      <a
        href={csvHref}
        className="rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-background"
      >
        CSV
      </a>
      <a
        href={pdfHref}
        className="rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-background"
      >
        PDF
      </a>
    </div>
  );
}
