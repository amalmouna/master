import { redirect } from "next/navigation";
import { getCurrentUserRole } from "@/lib/supabase/roles";
import { listManagedUsers } from "@/lib/supabase/admin";
import {
  getDatasetIdsForYear,
  getStudentsJoined,
  getFilterOptions,
  TOUTES_LES_ANNEES,
} from "@/lib/supabase/queries";
import { CreateUserForm } from "@/components/admin/CreateUserForm";
import { UsersTable } from "@/components/admin/UsersTable";

export default async function UtilisateursPage() {
  const role = await getCurrentUserRole();
  if (!role?.isAdmin) {
    redirect("/");
  }

  // Toutes les années : une classe assignable à un scoped_user doit rester
  // proposée même si elle n'apparaît que dans un import passé (cf. §10 —
  // un scoped_user assigné à une classe la voit pour toutes les années où
  // elle apparaît, pas seulement le dernier import).
  const datasetIds = await getDatasetIdsForYear(TOUTES_LES_ANNEES);
  const students = await getStudentsJoined(datasetIds);
  const options = getFilterOptions(students);
  const allClasses = Object.values(options.classesByNiveau).flat().sort();

  const users = await listManagedUsers();

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-lg font-semibold">Utilisateurs</h1>
      <p className="mt-1 text-xs text-muted-foreground">
        Créez des comptes administration. Un compte à accès limité ne voit que les
        classes qui lui sont assignées — appliqué au niveau de la base de données (RLS),
        pas seulement dans l&apos;interface.
      </p>

      <section className="mt-6 rounded-lg border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold">Créer un utilisateur</h2>
        <div className="mt-3">
          <CreateUserForm availableClasses={allClasses} />
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-border bg-surface">
        <h2 className="border-b border-border px-4 py-3 text-sm font-semibold">
          Comptes existants ({users.length})
        </h2>
        <UsersTable users={users} currentUserId={role.userId} />
      </section>
    </div>
  );
}
