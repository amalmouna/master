import "server-only";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

/**
 * Client service_role — contourne RLS, capable de créer/supprimer des
 * comptes Auth. `import "server-only"` fait échouer le BUILD si ce module
 * est jamais importé depuis un composant Client (garantie à la compilation,
 * pas seulement une convention). N'est appelé QUE depuis des Server Actions
 * qui vérifient d'abord is_admin() sur l'appelant (cf. app/(dashboard)/utilisateurs/actions.ts) —
 * ce fichier lui-même ne fait AUCUNE vérification d'autorisation, il fait
 * confiance à son appelant.
 */
function createSupabaseAdminClient() {
  if (!supabaseUrl || !serviceRoleKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY doivent être définis " +
        "(serveur uniquement — jamais NEXT_PUBLIC_, jamais exposé au navigateur)."
    );
  }
  return createClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

export interface ManagedUser {
  id: string;
  email: string;
  role: "admin" | "scoped_user" | null;
  classes: string[];
  createdAt: string;
}

export async function listManagedUsers(): Promise<ManagedUser[]> {
  const admin = createSupabaseAdminClient();

  const { data: usersPage, error: usersError } = await admin.auth.admin.listUsers({ perPage: 200 });
  if (usersError) throw new Error(`listManagedUsers (auth.users) : ${usersError.message}`);

  const [{ data: roles, error: rolesError }, { data: classes, error: classesError }] = await Promise.all([
    admin.from("user_roles").select("user_id, role"),
    admin.from("user_classes").select("user_id, classe"),
  ]);
  if (rolesError) throw new Error(`listManagedUsers (user_roles) : ${rolesError.message}`);
  if (classesError) throw new Error(`listManagedUsers (user_classes) : ${classesError.message}`);

  const roleByUser = new Map((roles ?? []).map((r) => [r.user_id, r.role as "admin" | "scoped_user"]));
  const classesByUser = new Map<string, string[]>();
  for (const c of classes ?? []) {
    const list = classesByUser.get(c.user_id) ?? [];
    list.push(c.classe);
    classesByUser.set(c.user_id, list);
  }

  return usersPage.users
    .map((u) => ({
      id: u.id,
      email: u.email ?? "",
      role: roleByUser.get(u.id) ?? null,
      classes: (classesByUser.get(u.id) ?? []).sort(),
      createdAt: u.created_at,
    }))
    .sort((a, b) => a.email.localeCompare(b.email));
}

export async function createManagedUser(params: {
  email: string;
  password: string;
  role: "admin" | "scoped_user";
  classes: string[];
}): Promise<void> {
  const admin = createSupabaseAdminClient();

  const { data, error } = await admin.auth.admin.createUser({
    email: params.email,
    password: params.password,
    email_confirm: true,
  });
  if (error) throw new Error(`createManagedUser (createUser) : ${error.message}`);
  const userId = data.user.id;

  const { error: roleError } = await admin
    .from("user_roles")
    .insert({ user_id: userId, role: params.role });
  if (roleError) throw new Error(`createManagedUser (user_roles) : ${roleError.message}`);

  if (params.role === "scoped_user" && params.classes.length > 0) {
    const { error: classesError } = await admin
      .from("user_classes")
      .insert(params.classes.map((classe) => ({ user_id: userId, classe })));
    if (classesError) throw new Error(`createManagedUser (user_classes) : ${classesError.message}`);
  }
}

export async function deleteManagedUser(userId: string): Promise<void> {
  const admin = createSupabaseAdminClient();
  // user_roles/user_classes ont une contrainte ON DELETE CASCADE sur auth.users(id) :
  // supprimer le compte Auth suffit à nettoyer les deux tables.
  const { error } = await admin.auth.admin.deleteUser(userId);
  if (error) throw new Error(`deleteManagedUser : ${error.message}`);
}
