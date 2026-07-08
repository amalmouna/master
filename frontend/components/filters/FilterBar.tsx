"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";

export interface FilterBarProps {
  niveaux: string[];
  classesByNiveau: Record<string, string[]>;
  profils: string[];
  /** Filtres pertinents pour la page courante — une page n'active que ceux
   * qui ont un sens (ex. pas de filtre "profil" sur la page Moyennes). */
  enabled: { niveau?: boolean; classe?: boolean; profil?: boolean; annee?: boolean };
  /** Années disponibles (plus récente en premier) — requis si enabled.annee. */
  anneesScolaires?: string[];
  /** Valeur actuellement sélectionnée pour l'année : soit une année précise,
   * soit la sentinelle "toutes" (TOUTES_LES_ANNEES, lib/supabase/queries.ts).
   * Résolue par la page appelante (absence de paramètre URL = année la plus
   * récente), pas dérivée ici — contrairement aux autres filtres, l'année
   * n'a pas de "vide = tout" implicite. */
  selectedAnnee?: string;
}

const TOUTES_LES_ANNEES = "toutes";

/** Barre de filtres partagée (année / niveau / classe / profil), pilotée par
 * l'URL (searchParams) pour rester cohérente entre pages Server Components
 * et navigable/partageable par lien. La classe se réinitialise si le niveau
 * change et ne correspond plus. */
export function FilterBar({
  niveaux,
  classesByNiveau,
  profils,
  enabled,
  anneesScolaires = [],
  selectedAnnee = "",
}: FilterBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const niveau = searchParams.get("niveau") ?? "";
  const classe = searchParams.get("classe") ?? "";
  const profil = searchParams.get("profil") ?? "";
  const classesDisponibles = niveau ? (classesByNiveau[niveau] ?? []) : [];

  function updateParam(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    if (key === "niveau") params.delete("classe");
    router.push(`${pathname}?${params.toString()}`);
  }

  const hasActiveFilters = niveau || classe || profil || searchParams.get("annee");

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2">
      {enabled.annee && (
        <select
          value={selectedAnnee}
          onChange={(e) => updateParam("annee", e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1 text-sm font-medium text-foreground"
        >
          {anneesScolaires.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
          <option value={TOUTES_LES_ANNEES}>Toutes les années</option>
        </select>
      )}
      {enabled.niveau && (
        <select
          value={niveau}
          onChange={(e) => updateParam("niveau", e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
        >
          <option value="">Tous les niveaux</option>
          {niveaux.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      )}
      {enabled.classe && (
        <select
          value={classe}
          onChange={(e) => updateParam("classe", e.target.value)}
          disabled={!niveau}
          className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground disabled:opacity-50"
        >
          <option value="">Toutes les classes</option>
          {classesDisponibles.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      )}
      {enabled.profil && (
        <select
          value={profil}
          onChange={(e) => updateParam("profil", e.target.value)}
          className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
        >
          <option value="">Tous les profils</option>
          {profils.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      )}
      {hasActiveFilters && (
        <button
          onClick={() => router.push(pathname)}
          className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
        >
          Réinitialiser
        </button>
      )}
    </div>
  );
}
