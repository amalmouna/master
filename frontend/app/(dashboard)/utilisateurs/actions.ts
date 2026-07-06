"use server";

import { revalidatePath } from "next/cache";
import { getCurrentUserRole } from "@/lib/supabase/roles";
import { createManagedUser, deleteManagedUser } from "@/lib/supabase/admin";

/**
 * Chaque action revérifie is_admin() sur L'APPELANT (via le client normal,
 * cookies de session) AVANT tout appel au client service_role. Le fait que
 * cette page ne soit pas dans la nav pour un scoped_user n'est qu'un confort
 * d'UI — l'action serait quand même bloquée ici si elle était appelée
 * directement (ex. requête forgée).
 */
async function assertAdmin() {
  const role = await getCurrentUserRole();
  if (!role?.isAdmin) {
    throw new Error("Action réservée aux administrateurs.");
  }
}

export interface ActionResult {
  ok: boolean;
  error?: string;
}

export async function createUserAction(formData: FormData): Promise<ActionResult> {
  try {
    await assertAdmin();

    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    const role = String(formData.get("role") ?? "");
    const classes = formData.getAll("classes").map(String);

    if (!email || !password) return { ok: false, error: "Email et mot de passe requis." };
    if (password.length < 8) return { ok: false, error: "Mot de passe : 8 caractères minimum." };
    if (role !== "admin" && role !== "scoped_user") return { ok: false, error: "Rôle invalide." };
    if (role === "scoped_user" && classes.length === 0) {
      return { ok: false, error: "Au moins une classe est requise pour un compte à accès limité." };
    }

    await createManagedUser({ email, password, role, classes: role === "scoped_user" ? classes : [] });
    revalidatePath("/utilisateurs");
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Erreur inconnue." };
  }
}

export async function deleteUserAction(userId: string): Promise<ActionResult> {
  try {
    await assertAdmin();
    await deleteManagedUser(userId);
    revalidatePath("/utilisateurs");
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Erreur inconnue." };
  }
}
