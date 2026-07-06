"use client";

import { useState } from "react";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

export function LoginForm({ next }: { next: string }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    setErrorMessage(null);

    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        // shouldCreateUser: false -> seuls les comptes déjà créés (invitation
        // dashboard) peuvent se connecter. Aucune inscription possible ici,
        // même si le lien magique est intercepté ou l'email inconnu.
        shouldCreateUser: false,
        emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    });

    if (error) {
      setStatus("error");
      setErrorMessage(
        "Connexion impossible pour cet email. Contactez l'administration si vous pensez qu'il s'agit d'une erreur."
      );
      return;
    }
    setStatus("sent");
  }

  if (status === "sent") {
    return (
      <p className="text-sm text-foreground">
        Un lien de connexion a été envoyé à <span className="font-medium">{email}</span>, s&apos;il
        correspond à un compte autorisé. Vérifiez votre boîte de réception.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label htmlFor="email" className="block text-xs font-medium text-muted-foreground">
          Adresse email
        </label>
        <input
          id="email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
          placeholder="prenom.nom@etablissement.ma"
        />
      </div>
      {status === "error" && errorMessage && (
        <p className="text-xs text-danger">{errorMessage}</p>
      )}
      <button
        type="submit"
        disabled={status === "sending"}
        className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground disabled:opacity-60"
      >
        {status === "sending" ? "Envoi en cours..." : "Recevoir un lien de connexion"}
      </button>
    </form>
  );
}
