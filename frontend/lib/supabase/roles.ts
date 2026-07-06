import { createSupabaseServerClient } from "./server";

export interface CurrentUserRole {
  userId: string;
  email: string;
  isAdmin: boolean;
  classes: string[];
}

/**
 * user_roles/user_classes n'ont AUCUNE politique RLS de lecture pour anon/
 * authenticated (voir migration_003) — même l'utilisateur connecté ne peut
 * pas les lire par un simple SELECT. On passe par les fonctions security
 * definer is_admin()/get_user_classes() (RPC), qui contournent RLS en
 * interne mais n'exposent que le strict résultat (booléen / liste de
 * classes), jamais les lignes elles-mêmes.
 */
export async function getCurrentUserRole(): Promise<CurrentUserRole | null> {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const [{ data: isAdmin }, { data: classes }] = await Promise.all([
    supabase.rpc("is_admin"),
    supabase.rpc("get_user_classes"),
  ]);

  return {
    userId: user.id,
    email: user.email ?? "",
    isAdmin: Boolean(isAdmin),
    classes: (classes as string[] | null) ?? [],
  };
}
