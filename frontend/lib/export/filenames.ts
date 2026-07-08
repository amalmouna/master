import { TOUTES_LES_ANNEES } from "@/lib/supabase/queries";

/** L'année scolaire doit toujours apparaître dans le nom de fichier ET
 * l'en-tête d'un export (§2.7 étendu) — un fichier téléchargé ne doit jamais
 * laisser planer un doute sur la cohorte qu'il décrit. "2025/2026" n'est pas
 * un nom de fichier valide (le "/" serait lu comme un séparateur de chemin) :
 * remplacé par un tiret. */
export function anneeForFilename(annee: string): string {
  return annee === TOUTES_LES_ANNEES ? "toutes-annees" : annee.replace("/", "-");
}

/** Libellé humain pour l'en-tête du document (CSV : première ligne de
 * commentaire ; PDF : sous-titre). */
export function anneeForHeader(annee: string): string {
  return annee === TOUTES_LES_ANNEES ? "Toutes les années" : `Année scolaire ${annee}`;
}
