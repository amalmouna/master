const PAGE_SIZE = 1000;

/**
 * Supabase/PostgREST plafonne silencieusement les résultats à `db-max-rows`
 * (1000 par défaut), quelle que soit la taille réelle de la table — sans
 * erreur, juste une troncature (déjà observé avec `grades`, 2599 lignes,
 * `recommendations`, 1003 lignes). Toute requête sur une table dont le
 * volume dépend du nombre d'élèves DOIT paginer explicitement, ou les
 * agrégats deviennent silencieusement faux dès que ce seuil est dépassé.
 */
export async function fetchAllRows<T>(
  buildQuery: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>
): Promise<T[]> {
  const all: T[] = [];
  let from = 0;
  while (true) {
    const { data, error } = await buildQuery(from, from + PAGE_SIZE - 1);
    if (error) throw new Error(`fetchAllRows: ${error.message}`);
    const page = data ?? [];
    all.push(...page);
    if (page.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }
  return all;
}
