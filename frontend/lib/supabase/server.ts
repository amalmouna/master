import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL et NEXT_PUBLIC_SUPABASE_ANON_KEY doivent être " +
      "définis dans frontend/.env.local."
  );
}

/**
 * Client Supabase par requête, pour les Server Components/Actions. Toujours
 * la clé anon (jamais service_role côté frontend) : l'accès aux données est
 * décidé par RLS sur la base du JWT utilisateur transporté par les cookies
 * de session, pas par le niveau de privilège de la clé elle-même.
 */
export async function createSupabaseServerClient() {
  const cookieStore = await cookies();

  return createServerClient(supabaseUrl!, supabaseAnonKey!, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Appelé depuis un Server Component (pas une Action/Route Handler) :
          // l'écriture de cookie y est interdite. Sans effet ici — le proxy
          // (proxy.ts) est responsable de rafraîchir la session sur chaque
          // requête, donc l'absence d'écriture à cet endroit est bénigne.
        }
      },
    },
  });
}

/** Session utilisateur vérifiée (appel réseau à Auth, jamais getSession() —
 * voir @supabase/ssr README : getSession() n'est pas fiable pour une décision
 * d'autorisation, un cookie forgé pourrait usurper un utilisateur). */
export async function getVerifiedUser() {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();
  if (error || !user) return null;
  return user;
}
