"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Upload, Loader2, CheckCircle, AlertTriangle, RefreshCw, FileX } from "lucide-react";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

const IMPORT_TIMEOUT_MS = 180_000; // généreux : démarrage à froid (~40-50s observé) + traitement (~1 min)

interface ImportSummary {
  dataset_id: string;
  academic_year: string;
  students_imported: number;
  n_a_risque_observe: number;
  n_a_risque_predit: number;
  coverage_counts: Record<string, number>;
  n_files_discovered: number;
  n_files_quarantined: number;
  quarantined_files: string[];
}

type Phase = "idle" | "submitting" | "retryable-error" | "final-error" | "success";

export function ImportForm() {
  const formRef = useRef<HTMLFormElement>(null);
  const [academicYear, setAcademicYear] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_IMPORT_API_URL;

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

    const formData = new FormData();
    formData.append("academic_year", academicYear);
    for (const file of files) {
      formData.append("files", file);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), IMPORT_TIMEOUT_MS);

    try {
      const response = await fetch(`${apiUrl}/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.status === 502 || response.status === 503 || response.status === 504) {
        setPhase("retryable-error");
        setErrorMessage(
          "Le serveur n'a pas répondu à temps (démarrage à froid probable après une période " +
            "d'inactivité). Ce n'est pas forcément un échec — réessayez, la requête suivante " +
            "aboutit généralement une fois le service réveillé."
        );
        return;
      }

      if (!response.ok) {
        let detail = `Erreur ${response.status}.`;
        try {
          const body = await response.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // corps non-JSON : on garde le message générique
        }
        setPhase("final-error");
        setErrorMessage(detail);
        return;
      }

      const result = (await response.json()) as ImportSummary;
      setSummary(result);
      setPhase("success");
    } catch (err) {
      clearTimeout(timeoutId);
      const isAbort = err instanceof DOMException && err.name === "AbortError";
      setPhase("retryable-error");
      setErrorMessage(
        isAbort
          ? "Aucune réponse après 3 minutes (démarrage à froid probable). Réessayez — le " +
              "service a normalement fini de démarrer."
          : "Impossible de contacter le serveur d'import (coupure réseau ou service indisponible). Réessayez."
      );
    }
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
            <span className="text-muted-foreground">Élèves importés</span>
            <div className="font-semibold text-foreground">{summary.students_imported}</div>
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

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-3">
      <div className="rounded-md border border-border bg-background p-2.5 text-xs text-muted-foreground">
        Le premier import après une période d&apos;inactivité peut prendre jusqu&apos;à ~2
        minutes (démarrage à froid du serveur + environ 1 minute de traitement). Une réponse
        lente n&apos;est pas un signe de panne.
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
          disabled={phase === "submitting"}
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
          disabled={phase === "submitting"}
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm disabled:opacity-60"
        />
        {files.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">{files.length} fichier(s) sélectionné(s)</p>
        )}
      </div>

      {phase === "retryable-error" && errorMessage && (
        <div className="rounded-md border border-warning-bg bg-warning-bg p-2.5 text-xs text-warning">
          <div className="flex items-center gap-1.5 font-medium">
            <AlertTriangle size={13} strokeWidth={2} />
            {errorMessage}
          </div>
          <button
            type="button"
            onClick={() => void runImport()}
            className="mt-2 flex items-center gap-1.5 rounded-md border border-warning px-2.5 py-1.5 text-xs font-medium text-warning hover:bg-warning-bg"
          >
            <RefreshCw size={12} strokeWidth={2} />
            Réessayer
          </button>
        </div>
      )}

      {phase === "final-error" && errorMessage && (
        <div className="flex items-start gap-1.5 rounded-md border border-danger-bg bg-danger-bg p-2.5 text-xs text-danger">
          <AlertTriangle size={13} strokeWidth={2} className="mt-0.5 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={phase === "submitting" || files.length === 0 || !academicYear}
        className="flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground disabled:opacity-60"
      >
        {phase === "submitting" ? (
          <>
            <Loader2 size={14} strokeWidth={2} className="animate-spin" />
            Import en cours... (jusqu&apos;à 2 minutes lors d&apos;un démarrage à froid)
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
