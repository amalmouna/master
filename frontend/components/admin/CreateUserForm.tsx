"use client";

import { useRef, useState } from "react";
import { createUserAction } from "@/app/(dashboard)/utilisateurs/actions";

export function CreateUserForm({ availableClasses }: { availableClasses: string[] }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [role, setRole] = useState<"admin" | "scoped_user">("scoped_user");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPending(true);
    setMessage(null);
    const formData = new FormData(e.currentTarget);
    const result = await createUserAction(formData);
    setPending(false);
    if (result.ok) {
      setMessage({ ok: true, text: "Utilisateur créé." });
      formRef.current?.reset();
      setRole("scoped_user");
    } else {
      setMessage({ ok: false, text: result.error ?? "Erreur inconnue." });
    }
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-muted-foreground">Email</label>
          <input
            name="email"
            type="email"
            required
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground">Mot de passe</label>
          <input
            name="password"
            type="password"
            required
            minLength={8}
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-muted-foreground">Rôle</label>
        <select
          name="role"
          value={role}
          onChange={(e) => setRole(e.target.value as "admin" | "scoped_user")}
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
        >
          <option value="scoped_user">Accès limité (classes choisies)</option>
          <option value="admin">Administrateur (accès complet)</option>
        </select>
      </div>

      {role === "scoped_user" && (
        <div>
          <label className="block text-xs font-medium text-muted-foreground">Classes autorisées</label>
          <div className="mt-1 grid grid-cols-4 gap-1.5 rounded-md border border-border bg-background p-2">
            {availableClasses.map((c) => (
              <label key={c} className="flex items-center gap-1.5 text-xs">
                <input type="checkbox" name="classes" value={c} />
                {c}
              </label>
            ))}
          </div>
        </div>
      )}

      {message && (
        <p className={`text-xs ${message.ok ? "text-success" : "text-danger"}`}>{message.text}</p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground disabled:opacity-60"
      >
        {pending ? "Création..." : "Créer l'utilisateur"}
      </button>
    </form>
  );
}
