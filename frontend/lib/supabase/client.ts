import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_URL et NEXT_PUBLIC_SUPABASE_ANON_KEY doivent être " +
      "définis dans frontend/.env.local. Le frontend n'utilise et ne doit " +
      "jamais utiliser la clé service_role (réservée au loader Python)."
  );
}

// Client public, lecture seule (RLS "lecture_publique" sur toutes les tables
// scolaires). Pas de session à persister : aucune authentification pour l'instant.
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: { persistSession: false },
});
