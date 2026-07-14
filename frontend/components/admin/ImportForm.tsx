"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Upload, Loader2, CheckCircle, AlertTriangle, RefreshCw, FileX } from "lucide-react";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

// Généreux : démarrage à froid observé ~30-60s (Render, tier gratuit) + import
// déjà observé jusqu'à ~60s de traitement une fois le service réveillé.
const IMPORT_TIMEOUT_MS = 180_000;
// Ping santé, court : sert juste à réveiller le service, pas à mesurer un délai précis.
const HEALTH_PING_TIMEOUT_MS = 10_000;
// Fenêtre pendant laquelle on retente le ping santé après un premier échec réseau,
// avant d'abandonner et d'afficher un échec définitif.
const HEALTH_WAIT_TOTAL_MS = 75_000;
const HEALTH_WAIT_INTERVAL_MS = 4_000;

interface ImportSummary {
  dataset_id: string;
  academic_year: string;
  students_imported: number;
  students_nouveaux: number;
  students_completes: number;
  n_a_risque_observe: number;
  n_a_risque_predit: number;
  coverage_counts: Record<string, number>;
  n_files_discovered: number;
  n_files_quarantined: number;
  quarantined_files: string[];
}

type Phase = "idle" | "submitting" | "warming" | "final-error" | "success";

type ImportAttemptResult =
  | { kind: "ok"; data: ImportSummary }
  | { kind: "http-error"; status: number; detail: string }
  | { kind: "network-or-timeout" };

/** Ping court, sans conséquence si le service ne répond pas encore — sert
 * uniquement à déclencher le réveil (Render, tier gratuit) avant que
 * l'admin ait fini de remplir le formulaire. Erreurs ignorées : ce n'est
 * qu'une optimisation, jamais une condition bloquante. */
async function pingHealth(apiUrl: string, timeoutMs: number): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const response = await fetch(`${apiUrl}/health`, { signal: controller.signal });
    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    return false;
  }
}

export function ImportForm() {
  const formRef = useRef<HTMLFormElement>(null);
  const [academicYear, setAcademicYear] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_IMPORT_API_URL;

  // Réveille le service dès l'ouverture de la page — le temps que l'admin
  // choisisse l'année et les fichiers, le démarrage à froid a des chances
  // d'être déjà terminé au moment du clic sur "Importer".
  useEffect(() => {
    if (apiUrl) void pingHealth(apiUrl, HEALTH_PING_TIMEOUT_MS);
  }, [apiUrl]);

  async function attemptImport(apiUrlValue: string, accessToken: string): Promise<ImportAttemptResult> {
    const formData = new FormData();
    formData.append("academic_year", academicYear);
    for (const file of files) {
      formData.append("files", file);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), IMPORT_TIMEOUT_MS);

    try {
      const response = await fetch(`${apiUrlValue}/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.status === 502 || response.status === 503 || response.status === 504) {
        return { kind: "network-or-timeout" };
      }

      if (!response.ok) {
        let detail = `Erreur ${response.status}.`;
        try {
          const body = await response.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // corps non-JSON : on garde le message générique
        }
        return { kind: "http-error", status: response.status, detail };
      }

      const data = (await response.json()) as ImportSummary;
      return { kind: "ok", data };
    } catch {
      clearTimeout(timeoutId);
      // Fetch a échoué avant même d'obtenir un statut HTTP (TypeError réseau)
      // ou notre propre AbortController a coupé après IMPORT_TIMEOUT_MS —
      // dans les deux cas on ne sait pas si le serveur est réellement en
      // panne ou juste encore en train de démarrer : cf. runImport, qui
      // vérifie /health avant de conclure.
      return { kind: "network-or-timeout" };
    }
  }

  async function runImport() {
    if (!apiUrl) {
      setPhase("final-error");
      setErrorMessage(
        "NEXT_PUBLIC_IMPORT_API_URL n'est pas configuré — l'import ne peut pas être envoyé."
      );
      return;
    }
    if (files.length === 0 || !academicYear) return;

    setPhase("submitting");
    setErrorMessage(null);

    const supabase = createSupabaseBrowserClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) {
      setPhase("final-error");
      setErrorMessage("Session expirée — reconnectez-vous puis réessayez.");
      return;
    }

    const first = await attemptImport(apiUrl, session.access_token);

    if (first.kind === "ok") {
      setSummary(first.data);
      setPhase("success");
      return;
    }

    if (first.kind === "http-error") {
      // Le serveur a répondu (avec une erreur) : il est donc bien réveillé et
      // joignable — l'échec est réel (fichier invalide, 401, doublon
      // d'année...), pas un problème de démarrage à froid.
      setPhase("final-error");
      setErrorMessage(first.detail);
      return;
    }

    // Ni une réponse HTTP franche, ni un succès : on ne sait pas encore si
    // c'est un vrai problème réseau ou juste un démarrage à froid en cours.
    // On l'affiche honnêtement comme un état transitoire, pas comme un échec.
    setPhase("warming");
    const wokeUp = await waitForHealthy(apiUrl);

    const second = await attemptImport(apiUrl, session.access_token);

    if (second.kind === "ok") {
      setSummary(second.data);
      setPhase("success");
      return;
    }

    if (second.kind === "http-error") {
      setPhase("final-error");
      setErrorMessage(second.detail);
      return;
    }

    // Deux échecs de suite, dont un après confirmation (ou tentative) de
    // réveil du service : là, c'est probablement une vraie coupure, pas un
    // simple démarrage à froid.
    setPhase("final-error");
    setErrorMessage(
      wokeUp
        ? "Le serveur a répondu au ping de santé mais l'import a échoué deux fois de suite sans " +
            "réponse claire — probablement une coupure réseau plutôt qu'un démarrage à froid. Réessayez."
        : "Impossible de contacter le serveur d'import après plusieurs tentatives, y compris son " +
            "point de contrôle de santé (/health) — le service semble réellement indisponible, pas " +
            "seulement en train de démarrer."
    );
  }

  /** Sonde /health à intervalles réguliers jusqu'à ce qu'il réponde, ou
   * jusqu'à épuisement de la fenêtre d'attente. Renvoie si le service a
   * fini par répondre — sert seulement à choisir le message d'erreur final,
   * pas à bloquer indéfiniment. */
  async function waitForHealthy(apiUrlValue: string): Promise<boolean> {
    const deadline = Date.now() + HEALTH_WAIT_TOTAL_MS;
    while (Date.now() < deadline) {
      if (await pingHealth(apiUrlValue, HEALTH_PING_TIMEOUT_MS)) return true;
      await new Promise((resolve) => setTimeout(resolve, HEALTH_WAIT_INTERVAL_MS));
    }
    return false;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    void runImport();
  }

  function handleReset() {
    setPhase("idle");
    setSummary(null);
    setErrorMessage(null);
    setAcademicYear("");
    setFiles([]);
    formRef.current?.reset();
  }

  if (phase === "success" && summary) {
    return (
      <div className="rounded-lg border border-success-bg bg-success-bg p-4">
        <div className="flex items-center gap-2 text-success">
          <CheckCircle size={16} strokeWidth={2} />
          <span className="text-sm font-semibold">
            Import terminé — année {summary.academic_year}
          </span>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-muted-foreground">Élèves affectés (nouveaux / complétés)</span>
            <div className="font-semibold text-foreground">
              {summary.students_imported} ({summary.students_nouveaux} / {summary.students_completes})
            </div>
          </div>
          <div>
            <span className="text-muted-foreground">À risque (observé / prédit)</span>
            <div className="font-semibold text-foreground">
              {summary.n_a_risque_observe} / {summary.n_a_risque_predit}
            </div>
          </div>
          <div>
            <span className="text-muted-foreground">Fichiers découverts / en quarantaine</span>
            <div className="font-semibold text-foreground">
              {summary.n_files_discovered} / {summary.n_files_quarantined}
            </div>
          </div>
          <div>
            <span className="text-muted-foreground">Couverture (classe × matière)</span>
            <div className="font-semibold text-foreground">
              {Object.entries(summary.coverage_counts)
                .map(([statut, n]) => `${statut}: ${n}`)
                .join(" · ")}
            </div>
          </div>
        </div>
        {summary.quarantined_files.length > 0 && (
          <div className="mt-3 rounded-md border border-warning-bg bg-warning-bg p-2 text-xs text-warning">
            <div className="flex items-center gap-1.5 font-medium">
              <FileX size={13} strokeWidth={2} />
              Fichiers en quarantaine ({summary.quarantined_files.length})
            </div>
            <ul className="mt-1 list-disc pl-4">
              {summary.quarantined_files.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-4 flex gap-2">
          <Link
            href="/"
            className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
          >
            Voir le tableau de bord
          </Link>
          <button
            type="button"
            onClick={handleReset}
            className="rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-background"
          >
            Nouvel import
          </button>
        </div>
      </div>
    );
  }

  const isBusy = phase === "submitting" || phase === "warming";

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-3">
      <div className="rounded-md border border-border bg-background p-2.5 text-xs text-muted-foreground space-y-1">
        <p>
          Un fichier Massar = une classe × une matière : vous pouvez importer les matières
          d&apos;une classe une à une, à des moments différents, pour la même année scolaire —
          chaque nouvel import complète le profil des élèves déjà importés plutôt que de le
          remplacer.
        </p>
        <p>
          Le premier import après une période d&apos;inactivité peut prendre jusqu&apos;à ~2
          minutes (démarrage à froid du serveur + environ 1 minute de traitement). Une réponse
          lente n&apos;est pas un signe de panne.
        </p>
      </div>

      <div>
        <label className="block text-xs font-medium text-muted-foreground">Année scolaire</label>
        <input
          type="text"
          required
          pattern="\d{4}/\d{4}"
          placeholder="2026/2027"
          value={academicYear}
          onChange={(e) => setAcademicYear(e.target.value)}
          disabled={isBusy}
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm disabled:opacity-60"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-muted-foreground">
          Fichiers Massar (.xlsx)
        </label>
        <input
          type="file"
          required
          multiple
          accept=".xlsx"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          disabled={isBusy}
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm disabled:opacity-60"
        />
        {files.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">{files.length} fichier(s) sélectionné(s)</p>
        )}
      </div>

      {phase === "warming" && (
        <div className="flex items-center gap-1.5 rounded-md border border-warning-bg bg-warning-bg p-2.5 text-xs text-warning">
          <Loader2 size={13} strokeWidth={2} className="animate-spin shrink-0" />
          Le serveur démarre, cela peut prendre jusqu&apos;à une minute avant de reprendre
          l&apos;import automatiquement — pas besoin de réessayer manuellement.
        </div>
      )}

      {phase === "final-error" && errorMessage && (
        <div className="rounded-md border border-danger-bg bg-danger-bg p-2.5 text-xs text-danger">
          <div className="flex items-start gap-1.5">
            <AlertTriangle size={13} strokeWidth={2} className="mt-0.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => void runImport()}
            className="mt-2 flex items-center gap-1.5 rounded-md border border-danger px-2.5 py-1.5 text-xs font-medium text-danger hover:bg-danger-bg"
          >
            <RefreshCw size={12} strokeWidth={2} />
            Réessayer
          </button>
        </div>
      )}

      <button
        type="submit"
        disabled={isBusy || files.length === 0 || !academicYear}
        className="flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground disabled:opacity-60"
      >
        {isBusy ? (
          <>
            <Loader2 size={14} strokeWidth={2} className="animate-spin" />
            {phase === "warming"
              ? "Démarrage du serveur en cours..."
              : "Import en cours... (jusqu'à 2 minutes lors d'un démarrage à froid)"}
          </>
        ) : (
          <>
            <Upload size={14} strokeWidth={2} />
            Importer
          </>
        )}
      </button>
    </form>
  );
}
