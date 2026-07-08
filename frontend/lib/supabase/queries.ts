import { createSupabaseServerClient } from "./server";
import { fetchAllRows } from "./fetchAll";
import type { Dataset, Subject, Grade, Student, ClusterRow, Prediction, RecommendationRow } from "./types";

const SEUIL_SIGNAL_ETABLISSEMENT = 50; // % d'élèves sous 10/20 dans une matière

export interface StudentJoined {
  id: string;
  student_pseudo: string;
  academic_year: string;
  nom_complet: string | null;
  niveau: string;
  classe: string;
  a_risque: boolean;
  moyenne_generale: number | null;
  nb_matieres_suivies: number | null;
  cluster_label: string | null;
}

/** Élèves + profil de cluster joints en mémoire (~500 lignes par année, un
 * seul aller-retour paginé par table) — base commune pour toutes les pages
 * filtrables par niveau/classe/profil. Évite de refaire une jointure
 * PostgREST par page.
 *
 * `datasetIds` — un ou plusieurs imports (§10, imports additifs multi-
 * années) : un seul id pour une année donnée, plusieurs pour "toutes les
 * années" (cf. getDatasetIdsForYear). Un même élève réapparaît une fois par
 * année où il a été importé — pas de déduplication inter-années ici, chaque
 * ligne `students` est un instantané propre à son import. */
export async function getStudentsJoined(datasetIds: string[]): Promise<StudentJoined[]> {
  if (datasetIds.length === 0) return [];
  const supabase = await createSupabaseServerClient();
  const [students, clusters] = await Promise.all([
    fetchAllRows<Student>((from, to) =>
      supabase.from("students").select("*").in("dataset_id", datasetIds).range(from, to)
    ),
    fetchAllRows<Pick<ClusterRow, "student_id" | "cluster_label">>((from, to) =>
      supabase
        .from("clusters")
        .select("student_id, cluster_label")
        .in("dataset_id", datasetIds)
        .range(from, to)
    ),
  ]);

  const clusterByStudent = new Map(clusters.map((c) => [c.student_id, c.cluster_label]));

  return students.map((s) => ({
    id: s.id,
    student_pseudo: s.student_pseudo,
    academic_year: s.academic_year,
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

/** Sentinelle du filtre "année scolaire" pour agréger tous les imports —
 * jamais confondu avec un `annee_scolaire` réel (format 'AAAA/AAAA'). */
export const TOUTES_LES_ANNEES = "toutes";

/** Années scolaires disponibles, triées de la plus récente à la plus
 * ancienne — sert à peupler le filtre et à déterminer la valeur par défaut
 * (la plus récente), distincte du filtre "toutes les années" qui doit être
 * choisi explicitement. */
export async function getAvailableAcademicYears(): Promise<string[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from("datasets").select("annee_scolaire");
  if (error) throw new Error(`getAvailableAcademicYears: ${error.message}`);
  const years = new Set(
    (data ?? [])
      .map((d) => (d as { annee_scolaire: string | null }).annee_scolaire)
      .filter((y): y is string => y !== null)
  );
  return [...years].sort().reverse();
}

/** Résout un filtre année scolaire (valeur d'URL, sentinelle TOUTES_LES_ANNEES
 * ou année précise) en la liste des dataset_id correspondants — plusieurs
 * imports peuvent en théorie partager la même annee_scolaire (ex. deux
 * semestres importés séparément), d'où un tableau même pour une année précise. */
export async function getDatasetIdsForYear(year: string): Promise<string[]> {
  const supabase = await createSupabaseServerClient();
  let query = supabase.from("datasets").select("id");
  if (year !== TOUTES_LES_ANNEES) query = query.eq("annee_scolaire", year);
  const { data, error } = await query;
  if (error) throw new Error(`getDatasetIdsForYear: ${error.message}`);
  return (data ?? []).map((d) => (d as { id: string }).id);
}

/** Résout le paramètre d'URL `annee` en valeur effective : absent -> année la
 * plus récente (jamais "toutes les années" par défaut, qui doit être choisi
 * explicitement) ; sinon la valeur telle quelle (année précise ou
 * TOUTES_LES_ANNEES). Si aucun import n'existe encore, retombe sur
 * TOUTES_LES_ANNEES (sans effet : getDatasetIdsForYear renverra alors []). */
export function resolveSelectedAnnee(anneeParam: string | undefined, availableYears: string[]): string {
  if (anneeParam) return anneeParam;
  return availableYears[0] ?? TOUTES_LES_ANNEES;
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

/** Prévalence du risque, globale et par niveau, calculée sur les élèves des
 * dataset(s) sélectionnés (agrégation en mémoire : ~500 lignes par année,
 * largement dans le budget d'un rendu serveur — pas besoin de RPC/vue
 * dédiée à ce volume). */
export async function getRiskSummary(datasetIds: string[]): Promise<RiskSummary> {
  if (datasetIds.length === 0) {
    return { n_eleves: 0, n_a_risque: 0, pct_a_risque: 0, moyenne_generale: null, par_niveau: [] };
  }
  const supabase = await createSupabaseServerClient();
  const students = await fetchAllRows<Pick<Student, "niveau" | "a_risque" | "moyenne_generale">>(
    (from, to) =>
      supabase
        .from("students")
        .select("niveau, a_risque, moyenne_generale")
        .in("dataset_id", datasetIds)
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
  datasetIds: string[],
  studentIds?: Set<string>
): Promise<SubjectSignal[]> {
  if (datasetIds.length === 0) return [];
  const supabase = await createSupabaseServerClient();
  const { data: subjectsData, error: subjectsError } = await supabase.from("subjects").select("*");
  if (subjectsError) throw new Error(`getSubjectSignals (subjects): ${subjectsError.message}`);
  const subjects = (subjectsData ?? []) as Subject[];

  const grades = await fetchAllRows<Pick<Grade, "student_id" | "subject_code" | "moyenne_matiere">>(
    (from, to) =>
      supabase
        .from("grades")
        .select("student_id, subject_code, moyenne_matiere")
        .in("dataset_id", datasetIds)
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
export async function getPredictionsByStudent(datasetIds: string[]): Promise<Map<string, PredictionSummary>> {
  if (datasetIds.length === 0) return new Map();
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
      .in("dataset_id", datasetIds)
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
export async function getClusterPoints(datasetIds: string[]): Promise<ClusterPoint[]> {
  if (datasetIds.length === 0) return [];
  const supabase = await createSupabaseServerClient();
  const [clusters, students] = await Promise.all([
    fetchAllRows<Pick<ClusterRow, "student_id" | "cluster_label" | "pca_1" | "pca_2">>((from, to) =>
      supabase
        .from("clusters")
        .select("student_id, cluster_label, pca_1, pca_2")
        .in("dataset_id", datasetIds)
        .range(from, to)
    ),
    fetchAllRows<Pick<Student, "id" | "niveau" | "classe" | "moyenne_generale" | "dispersion_intermatiere" | "a_risque">>(
      (from, to) =>
        supabase
          .from("students")
          .select("id, niveau, classe, moyenne_generale, dispersion_intermatiere, a_risque")
          .in("dataset_id", datasetIds)
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

/** Fiche élève complète pour une année scolaire précise. Un seul élève
 * scopé par (pseudo, academic_year) — la contrainte unique
 * students_pseudo_academic_year_unique garantit au plus une ligne, donc pas
 * besoin de passer par dataset_id : ça reste correct même si une année
 * finissait par recouvrir plusieurs imports. Pas de pagination nécessaire
 * (au plus 7 notes et quelques recommandations) — RLS (classe) s'applique
 * normalement via createSupabaseServerClient. */
export async function getStudentDetailByYear(pseudo: string, academicYear: string): Promise<StudentDetail | null> {
  const supabase = await createSupabaseServerClient();
  const { data: studentData, error: studentError } = await supabase
    .from("students")
    .select("*")
    .eq("student_pseudo", pseudo)
    .eq("academic_year", academicYear)
    .maybeSingle();
  if (studentError) throw new Error(`getStudentDetailByYear (student): ${studentError.message}`);
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

export interface TrajectoryYear {
  student_id: string;
  academic_year: string;
  niveau: string;
  classe: string;
  moyenne_generale: number | null;
  a_risque: boolean;
}

/** Historique d'un élève à travers les années — student_pseudo est stable
 * (même sel HMAC, cf. anonymization/anonymize.py), donc une simple requête
 * par pseudo suffit à retrouver toutes ses lignes `students`, une par année
 * importée. Pas de pagination : au plus une poignée d'années par élève, ça
 * ne grossit jamais avec le nombre total d'élèves de l'établissement. RLS
 * (classe) s'applique ligne par ligne : un scoped_user ne voit que les
 * années où CET élève était dans une classe qui lui est assignée. */
export async function getStudentTrajectory(pseudo: string): Promise<TrajectoryYear[]> {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase
    .from("students")
    .select("id, academic_year, niveau, classe, moyenne_generale, a_risque")
    .eq("student_pseudo", pseudo)
    .order("academic_year", { ascending: true });
  if (error) throw new Error(`getStudentTrajectory: ${error.message}`);
  return (data ?? []).map((s) => ({
    student_id: (s as { id: string }).id,
    academic_year: (s as { academic_year: string }).academic_year,
    niveau: (s as { niveau: string }).niveau,
    classe: (s as { classe: string }).classe,
    moyenne_generale: (s as { moyenne_generale: number | null }).moyenne_generale,
    a_risque: (s as { a_risque: boolean }).a_risque,
  }));
}

export interface SubjectTrajectory {
  subject_code: string;
  subject_nom_fr: string;
  points: { academic_year: string; moyenne_matiere: number | null }[];
}

/** Moyenne par matière, une série par année, pour les `student_id` déjà
 * résolus par getStudentTrajectory (un id différent par année — chaque
 * import crée une nouvelle ligne `students`/`grades`, liées entre elles par
 * student_pseudo, pas par un id élève partagé). Pas de pagination : au plus
 * (nb années × 7 matières) lignes pour un seul élève. */
export async function getStudentSubjectTrajectory(years: TrajectoryYear[]): Promise<SubjectTrajectory[]> {
  if (years.length === 0) return [];
  const supabase = await createSupabaseServerClient();
  const yearByStudentId = new Map(years.map((y) => [y.student_id, y.academic_year]));
  const studentIds = years.map((y) => y.student_id);

  const [gradesRes, subjectsRes] = await Promise.all([
    supabase
      .from("grades")
      .select("student_id, subject_code, moyenne_matiere")
      .in("student_id", studentIds),
    supabase.from("subjects").select("*"),
  ]);
  if (gradesRes.error) throw new Error(`getStudentSubjectTrajectory (grades): ${gradesRes.error.message}`);
  if (subjectsRes.error) throw new Error(`getStudentSubjectTrajectory (subjects): ${subjectsRes.error.message}`);

  const subjectsByCode = new Map(((subjectsRes.data ?? []) as Subject[]).map((s) => [s.code, s]));
  const bySubject = new Map<string, { academic_year: string; moyenne_matiere: number | null }[]>();

  for (const g of (gradesRes.data ?? []) as Pick<Grade, "student_id" | "subject_code" | "moyenne_matiere">[]) {
    const academicYear = yearByStudentId.get(g.student_id);
    if (!academicYear) continue;
    const list = bySubject.get(g.subject_code) ?? [];
    list.push({ academic_year: academicYear, moyenne_matiere: g.moyenne_matiere });
    bySubject.set(g.subject_code, list);
  }

  return [...bySubject.entries()]
    .map(([code, points]) => ({
      subject_code: code,
      subject_nom_fr: subjectsByCode.get(code)?.nom_fr ?? code,
      points: points.sort((a, b) => a.academic_year.localeCompare(b.academic_year)),
    }))
    .sort((a, b) => a.subject_nom_fr.localeCompare(b.subject_nom_fr));
}
