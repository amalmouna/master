import { createBrowserClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL et NEXT_PUBLIC_SUPABASE_ANON_KEY doivent être " +
      "définis dans frontend/.env.local. Le frontend n'utilise et ne doit " +
      "jamais utiliser la clé service_role (réservée au loader Python)."
  );
}

/** Client Supabase navigateur (page de connexion uniquement) — clé anon,
 * session gérée via cookies pour rester synchronisée avec le serveur
 * (Server Components, proxy). */
export function createSupabaseBrowserClient() {
  return createBrowserClient(supabaseUrl!, supabaseAnonKey!);
}
