import { supabase } from "./client";
import { fetchAllRows } from "./fetchAll";
import type { Dataset, Subject, Grade, Student } from "./types";

const SEUIL_SIGNAL_ETABLISSEMENT = 50; // % d'élèves sous 10/20 dans une matière

/** Dernier import chargé (§2.8 — historisation, un dataset = un semestre). */
export async function getLatestDataset(): Promise<Dataset | null> {
  const { data, error } = await supabase
    .from("datasets")
    .select("*")
    .order("date_import", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) throw new Error(`getLatestDataset: ${error.message}`);
  return data as Dataset | null;
}

export interface RiskByNiveau {
  niveau: string;
  n: number;
  n_a_risque: number;
  pct_a_risque: number;
}

export interface RiskSummary {
  n_eleves: number;
  n_a_risque: number;
  pct_a_risque: number;
  moyenne_generale: number | null;
  par_niveau: RiskByNiveau[];
}

/** Prévalence du risque, globale et par niveau, calculée sur les élèves du
 * dataset (agrégation en mémoire : ~500 lignes, largement dans le budget d'un
 * rendu serveur — pas besoin de RPC/vue dédiée à ce volume). */
export async function getRiskSummary(datasetId: string): Promise<RiskSummary> {
  const students = await fetchAllRows<Pick<Student, "niveau" | "a_risque" | "moyenne_generale">>(
    (from, to) =>
      supabase
        .from("students")
        .select("niveau, a_risque, moyenne_generale")
        .eq("dataset_id", datasetId)
        .range(from, to)
  );

  const parNiveau = new Map<string, { n: number; n_a_risque: number }>();
  let sommeMoyennes = 0;
  let nAvecMoyenne = 0;

  for (const s of students) {
    const entry = parNiveau.get(s.niveau) ?? { n: 0, n_a_risque: 0 };
    entry.n += 1;
    if (s.a_risque) entry.n_a_risque += 1;
    parNiveau.set(s.niveau, entry);
    if (s.moyenne_generale !== null) {
      sommeMoyennes += s.moyenne_generale;
      nAvecMoyenne += 1;
    }
  }

  const nEleves = students.length;
  const nARisque = students.filter((s) => s.a_risque).length;

  return {
    n_eleves: nEleves,
    n_a_risque: nARisque,
    pct_a_risque: nEleves > 0 ? (100 * nARisque) / nEleves : 0,
    moyenne_generale: nAvecMoyenne > 0 ? sommeMoyennes / nAvecMoyenne : null,
    par_niveau: [...parNiveau.entries()]
      .map(([niveau, { n, n_a_risque }]) => ({
        niveau,
        n,
        n_a_risque,
        pct_a_risque: n > 0 ? (100 * n_a_risque) / n : 0,
      }))
      .sort((a, b) => a.niveau.localeCompare(b.niveau)),
  };
}

export interface SubjectSignal {
  code: string;
  nom_fr: string;
  domaine: string;
  n_suivi: number;
  moyenne: number;
  pct_sous_10: number;
  pct_sous_8: number;
}

/** Moyenne et taux d'échec par matière, sur les élèves qui la suivent
 * réellement (une ligne `grades` n'existe que si la matière est suivie —
 * jamais d'imputation pour une matière hors curriculum). */
export async function getSubjectSignals(datasetId: string): Promise<SubjectSignal[]> {
  const { data: subjectsData, error: subjectsError } = await supabase.from("subjects").select("*");
  if (subjectsError) throw new Error(`getSubjectSignals (subjects): ${subjectsError.message}`);
  const subjects = (subjectsData ?? []) as Subject[];

  const grades = await fetchAllRows<Pick<Grade, "subject_code" | "moyenne_matiere">>((from, to) =>
    supabase
      .from("grades")
      .select("subject_code, moyenne_matiere")
      .eq("dataset_id", datasetId)
      .range(from, to)
  );

  const bySubject = new Map<string, number[]>();
  for (const g of grades) {
    if (g.moyenne_matiere === null) continue;
    const list = bySubject.get(g.subject_code) ?? [];
    list.push(g.moyenne_matiere);
    bySubject.set(g.subject_code, list);
  }

  return subjects
    .map((subject) => {
      const moyennes = bySubject.get(subject.code) ?? [];
      const n = moyennes.length;
      const sousBarre = (seuil: number) =>
        n > 0 ? (100 * moyennes.filter((m) => m < seuil).length) / n : 0;
      return {
        code: subject.code,
        nom_fr: subject.nom_fr,
        domaine: subject.domaine,
        n_suivi: n,
        moyenne: n > 0 ? moyennes.reduce((a, b) => a + b, 0) / n : 0,
        pct_sous_10: sousBarre(10),
        pct_sous_8: sousBarre(8),
      };
    })
    .filter((s) => s.n_suivi > 0)
    .sort((a, b) => b.pct_sous_10 - a.pct_sous_10);
}

export interface EtablissementSignal {
  matiere: string;
  pct_sous_10: number;
  pct_sous_8: number;
  message: string;
}

/** Signaux à l'échelle de l'établissement (ex. Histoire-Géo à 56% sous 10) —
 * distincts des recommandations individuelles, pour la vue d'ensemble. */
export function extractEtablissementSignals(signals: SubjectSignal[]): EtablissementSignal[] {
  return signals
    .filter((s) => s.pct_sous_10 > SEUIL_SIGNAL_ETABLISSEMENT)
    .map((s) => ({
      matiere: s.nom_fr,
      pct_sous_10: s.pct_sous_10,
      pct_sous_8: s.pct_sous_8,
      message: `${s.nom_fr} : ${s.pct_sous_10.toFixed(1)}% des élèves suivis sont sous 10/20 (${s.pct_sous_8.toFixed(1)}% sous 8/20) — faiblesse à l'échelle de l'établissement.`,
    }));
}
