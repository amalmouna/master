"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { deleteUserAction } from "@/app/(dashboard)/utilisateurs/actions";
import type { ManagedUser } from "@/lib/supabase/admin";

export function UsersTable({
  users,
  currentUserId,
}: {
  users: ManagedUser[];
  currentUserId: string;
}) {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete(userId: string) {
    if (!confirm("Supprimer ce compte ? Cette action est irréversible.")) return;
    setPendingId(userId);
    setError(null);
    const result = await deleteUserAction(userId);
    setPendingId(null);
    if (!result.ok) setError(result.error ?? "Erreur inconnue.");
  }

  return (
    <div>
      {error && <p className="px-4 pt-3 text-xs text-danger">{error}</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2 font-medium">Email</th>
            <th className="px-4 py-2 font-medium">Rôle</th>
            <th className="px-4 py-2 font-medium">Classes</th>
            <th className="px-4 py-2 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t border-border">
              <td className="px-4 py-2">{u.email}</td>
              <td className="px-4 py-2 text-muted-foreground">
                {u.role === "admin" ? "Administrateur" : u.role === "scoped_user" ? "Accès limité" : "—"}
              </td>
              <td className="px-4 py-2 text-muted-foreground">
                {u.role === "admin" ? "Toutes" : u.classes.length > 0 ? u.classes.join(", ") : "—"}
              </td>
              <td className="px-4 py-2 text-right">
                {u.id !== currentUserId && (
                  <button
                    onClick={() => handleDelete(u.id)}
                    disabled={pendingId === u.id}
                    className="text-muted-foreground hover:text-danger disabled:opacity-50"
                    title="Supprimer"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
