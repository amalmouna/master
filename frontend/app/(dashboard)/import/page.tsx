import { redirect } from "next/navigation";
import { getCurrentUserRole } from "@/lib/supabase/roles";
import { ImportForm } from "@/components/admin/ImportForm";

export default async function ImportPage() {
  const role = await getCurrentUserRole();
  if (!role?.isAdmin) {
    redirect("/");
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-lg font-semibold">Importer des données</h1>
      <p className="mt-1 text-xs text-muted-foreground">
        Charge un nouvel export Massar (.xlsx) pour une année scolaire. Le pipeline
        applique les modèles déjà entraînés (aucun réentraînement) et écrit le résultat
        directement dans la base — aucun fichier brut n&apos;est conservé après l&apos;import.
      </p>

      <section className="mt-6 rounded-lg border border-border bg-surface p-4">
        <ImportForm />
      </section>
    </div>
  );
}
