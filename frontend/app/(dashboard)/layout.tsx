import { redirect } from "next/navigation";
import { Sidebar } from "@/components/nav/Sidebar";
import { getCurrentUserRole } from "@/lib/supabase/roles";

/**
 * Deuxième ligne de défense après proxy.ts (cf. guide Next.js sur l'auth :
 * le proxy fait des vérifications "optimistic", la vérification proche de la
 * source de données — ici, juste avant tout accès aux tables scolaires —
 * reste nécessaire). Aucune page du groupe (dashboard) ne rend sans session
 * vérifiée par le serveur Auth (getUser(), jamais getSession()).
 */
export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const role = await getCurrentUserRole();
  if (!role) redirect("/login");

  return (
    <div className="flex min-h-full">
      <Sidebar userEmail={role.email} isAdmin={role.isAdmin} />
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
