import { createSupabaseServerClient } from "./server";
import { fetchAllRows } from "./fetchAll";
import type { Dataset, Subject, Grade, Student, ClusterRow, Prediction, RecommendationRow } from "./types";

const SEUIL_SIGNAL_ETABLISSEMENT = 50; // % d'élèves sous 10/20 dans une matière

export interface StudentJoined {
  id: string;
  student_pseudo: string;
  nom_complet: string | null;
  niveau: string;
  classe: string;
  a_risque: boolean;
  moyenne_generale: number | null;
  nb_matieres_suivies: number | null;
  cluster_label: string | null;
}

/** Élèves + profil de cluster joints en mémoire (~500 lignes, un seul aller-
 * retour paginé par table) — base commune pour toutes les pages filtrables
 * par niveau/classe/profil. Évite de refaire une jointure PostgREST par page. */
export async function getStudentsJoined(datasetId: string): Promise<StudentJoined[]> {
  const supabase = await createSupabaseServerClient();
  const [students, clusters] = await Promise.all([
    fetchAllRows<Student>((from, to) =>
      supabase.from("students").select("*").eq("dataset_id", datasetId).range(from, to)
    ),
    fetchAllRows<Pick<ClusterRow, "student_id" | "cluster_label">>((from, to) =>
      supabase
        .from("clusters")
        .select("student_id, cluster_label")
        .eq("dataset_id", datasetId)
        .range(from, to)
    ),
  ]);

  const clusterByStudent = new Map(clusters.map((c) => [c.student_id, c.cluster_label]));

  return students.map((s) => ({
    id: s.id,
    student_pseudo: s.student_pseudo,
    nom_complet: s.nom_complet,
    niveau: s.niveau,
    classe: s.classe,
    a_risque: s.a_risque,
    moyenne_generale: s.moyenne_generale,
    nb_matieres_suivies: s.nb_matieres_suivies,
    cluster_label: clusterByStudent.get(s.id) ?? null,
  }));
}

export interface StudentFilters {
  niveau?: string;
  classe?: string;
  profil?: string;
}

export function applyStudentFilters<T extends StudentJoined>(
  students: T[],
  filters: StudentFilters
): T[] {
  return students.filter(
    (s) =>
      (!filters.niveau || s.niveau === filters.niveau) &&
      (!filters.classe || s.classe === filters.classe) &&
      (!filters.profil || s.cluster_label === filters.profil)
  );
}

export interface FilterOptions {
  niveaux: string[];
  classesByNiveau: Record<string, string[]>;
  profils: string[];
}

/** Options de filtre dérivées des élèves réels du dataset (jamais une liste
 * en dur : le périmètre — niveaux/classes/profils — varie d'un import à l'autre). */
export function getFilterOptions(students: StudentJoined[]): FilterOptions {
  const classesByNiveau: Record<string, Set<string>> = {};
  const profils = new Set<string>();

  for (const s of students) {
    (classesByNiveau[s.niveau] ??= new Set()).add(s.classe);
    if (s.cluster_label) profils.add(s.cluster_label);
  }

  return {
    niveaux: Object.keys(classesByNiveau).sort(),
    classesByNiveau: Object.fromEntries(
      Object.entries(classesByNiveau).map(([n, set]) => [n, [...set].sort()])
    ),
    profils: [...profils].sort(),
  };
}

/** Dernier import chargé (§2.8 — historisation, un dataset = un semestre). */
export async function getLatestDataset(): Promise<Dataset | null> {
  const supabase = await createSupabaseServerClient();
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
  const supabase = await createSupabaseServerClient();
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
 * jamais d'imputation pour une matière hors curriculum). `studentIds`, si
 * fourni, restreint l'agrégat à un sous-ensemble d'élèves déjà filtré
 * (niveau/classe/profil) par l'appelant via applyStudentFilters. */
export async function getSubjectSignals(
  datasetId: string,
  studentIds?: Set<string>
): Promise<SubjectSignal[]> {
  const supabase = await createSupabaseServerClient();
  const { data: subjectsData, error: subjectsError } = await supabase.from("subjects").select("*");
  if (subjectsError) throw new Error(`getSubjectSignals (subjects): ${subjectsError.message}`);
  const subjects = (subjectsData ?? []) as Subject[];

  const grades = await fetchAllRows<Pick<Grade, "student_id" | "subject_code" | "moyenne_matiere">>(
    (from, to) =>
      supabase
        .from("grades")
        .select("student_id, subject_code, moyenne_matiere")
        .eq("dataset_id", datasetId)
        .range(from, to)
  );

  const bySubject = new Map<string, number[]>();
  for (const g of grades) {
    if (g.moyenne_matiere === null) continue;
    if (studentIds && !studentIds.has(g.student_id)) continue;
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

export type PredictionSummary = Pick<
  Prediction,
  "probabilite_risque" | "moyenne_generale_predite" | "explication_risque_fr" | "explication_moyenne_fr"
>;

/** Sorties des modèles retenus (Logistic Regression, Ridge), indexées par élève. */
export async function getPredictionsByStudent(datasetId: string): Promise<Map<string, PredictionSummary>> {
  const supabase = await createSupabaseServerClient();
  const predictions = await fetchAllRows<
    Pick<
      Prediction,
      | "student_id"
      | "probabilite_risque"
      | "moyenne_generale_predite"
      | "explication_risque_fr"
      | "explication_moyenne_fr"
    >
  >((from, to) =>
    supabase
      .from("predictions")
      .select("student_id, probabilite_risque, moyenne_generale_predite, explication_risque_fr, explication_moyenne_fr")
      .eq("dataset_id", datasetId)
      .range(from, to)
  );
  return new Map(predictions.map((p) => [p.student_id, p]));
}

export interface ClusterPoint {
  student_id: string;
  niveau: string;
  classe: string;
  cluster_label: string;
  pca_1: number | null;
  pca_2: number | null;
  moyenne_generale: number | null;
  dispersion_intermatiere: number | null;
  a_risque: boolean;
}

/** Points de cluster joints aux attributs descriptifs de l'élève. Le clustering
 * est fait par niveau (cf. src/models/clustering.py) sur des features de
 * domaine qui ne sont pas persistées telles quelles dans `students` — on
 * caractérise donc chaque cluster avec ce qui est disponible ici
 * (moyenne_generale, dispersion, taux de risque), pas les features exactes
 * du modèle. */
export async function getClusterPoints(datasetId: string): Promise<ClusterPoint[]> {
  const supabase = await createSupabaseServerClient();
  const [clusters, students] = await Promise.all([
    fetchAllRows<Pick<ClusterRow, "student_id" | "cluster_label" | "pca_1" | "pca_2">>((from, to) =>
      supabase
        .from("clusters")
        .select("student_id, cluster_label, pca_1, pca_2")
        .eq("dataset_id", datasetId)
        .range(from, to)
    ),
    fetchAllRows<Pick<Student, "id" | "niveau" | "classe" | "moyenne_generale" | "dispersion_intermatiere" | "a_risque">>(
      (from, to) =>
        supabase
          .from("students")
          .select("id, niveau, classe, moyenne_generale, dispersion_intermatiere, a_risque")
          .eq("dataset_id", datasetId)
          .range(from, to)
    ),
  ]);

  const studentById = new Map(students.map((s) => [s.id, s]));

  return clusters
    .map((c) => {
      const s = studentById.get(c.student_id);
      if (!s) return null;
      return {
        student_id: c.student_id,
        niveau: s.niveau,
        classe: s.classe,
        cluster_label: c.cluster_label,
        pca_1: c.pca_1,
        pca_2: c.pca_2,
        moyenne_generale: s.moyenne_generale,
        dispersion_intermatiere: s.dispersion_intermatiere,
        a_risque: s.a_risque,
      };
    })
    .filter((c): c is ClusterPoint => c !== null);
}

export interface ClusterSummary {
  niveau: string;
  cluster_label: string;
  n: number;
  moyenne_generale: number | null;
  dispersion_intermatiere: number | null;
  pct_a_risque: number;
}

export function summarizeClusters(points: ClusterPoint[]): ClusterSummary[] {
  const groups = new Map<string, ClusterPoint[]>();
  for (const p of points) {
    const key = `${p.niveau}::${p.cluster_label}`;
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(p);
  }

  const avg = (values: number[]) =>
    values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : null;

  return [...groups.entries()]
    .map(([key, group]) => {
      const [niveau, cluster_label] = key.split("::");
      const moyennes = group.map((p) => p.moyenne_generale).filter((v): v is number => v !== null);
      const dispersions = group
        .map((p) => p.dispersion_intermatiere)
        .filter((v): v is number => v !== null);
      return {
        niveau,
        cluster_label,
        n: group.length,
        moyenne_generale: avg(moyennes),
        dispersion_intermatiere: avg(dispersions),
        pct_a_risque: (100 * group.filter((p) => p.a_risque).length) / group.length,
      };
    })
    .sort((a, b) => a.niveau.localeCompare(b.niveau) || (b.moyenne_generale ?? 0) - (a.moyenne_generale ?? 0));
}

export interface GradeDetail extends Grade {
  subject_nom_fr: string;
  subject_domaine: string;
}

export interface StudentDetail {
  student: Student;
  cluster_label: string | null;
  prediction: PredictionSummary | null;
  grades: GradeDetail[];
  recommendations: RecommendationRow[];
}

/** Fiche élève complète. Un seul élève scopé par dataset+pseudo (pas de
 * pagination nécessaire : au plus 7 notes et quelques recommandations). */
export async function getStudentDetail(datasetId: string, pseudo: string): Promise<StudentDetail | null> {
  const supabase = await createSupabaseServerClient();
  const { data: studentData, error: studentError } = await supabase
    .from("students")
    .select("*")
    .eq("dataset_id", datasetId)
    .eq("student_pseudo", pseudo)
    .maybeSingle();
  if (studentError) throw new Error(`getStudentDetail (student): ${studentError.message}`);
  if (!studentData) return null;
  const student = studentData as Student;

  const [clusterRes, predictionRes, gradesRes, subjectsRes, recsRes] = await Promise.all([
    supabase.from("clusters").select("cluster_label").eq("student_id", student.id).maybeSingle(),
    supabase.from("predictions").select("*").eq("student_id", student.id).maybeSingle(),
    supabase.from("grades").select("*").eq("student_id", student.id),
    supabase.from("subjects").select("*"),
    supabase
      .from("recommendations")
      .select("*")
      .eq("student_id", student.id)
      .order("priorite", { ascending: true }),
  ]);

  const subjectsByCode = new Map(((subjectsRes.data ?? []) as Subject[]).map((s) => [s.code, s]));
  const grades: GradeDetail[] = ((gradesRes.data ?? []) as Grade[]).map((g) => ({
    ...g,
    subject_nom_fr: subjectsByCode.get(g.subject_code)?.nom_fr ?? g.subject_code,
    subject_domaine: subjectsByCode.get(g.subject_code)?.domaine ?? "",
  }));

  return {
    student,
    cluster_label: (clusterRes.data as { cluster_label: string } | null)?.cluster_label ?? null,
    prediction: (predictionRes.data as PredictionSummary | null) ?? null,
    grades,
    recommendations: (recsRes.data ?? []) as RecommendationRow[],
  };
}
