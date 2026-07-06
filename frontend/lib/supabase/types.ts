/** Types alignés sur supabase/schema.sql. Toute divergence de nom de colonne
 * doit être corrigée ici en premier — ne pas dupliquer la définition ailleurs. */

export type Domaine = "scientifique" | "linguistique" | "sciences_humaines";
export type ModelRunType = "classification" | "regression" | "clustering";
export type Priorite = 1 | 2 | 3;

export interface QualitySummary {
  n_files_discovered: number;
  n_files_parsed_ok: number;
  n_files_quarantined: number;
  n_students_uniques: number;
  n_enregistrements: number;
  niveaux: string[];
  classes: string[];
  matieres: string[];
  coverage_counts: Record<string, number>;
  n_anomalies_bornes: number;
  n_doublons: number;
  remplissage_composantes_pct: Record<string, number | null>;
  composantes_disponibilite: Record<
    string,
    { pct_enregistrements_avec_colonne: number; pct_rempli_quand_colonne_existe: number | null }
  >;
}

export interface RiskConfig {
  definition: string;
  regle: string;
  passing_grade: number;
  proportion_threshold: number;
  cible_regression: string;
  colonnes_fuite_exclues: string[];
}

export interface Dataset {
  id: string;
  label: string;
  annee_scolaire: string | null;
  semestre: string | null;
  date_import: string;
  n_eleves: number | null;
  n_enregistrements: number | null;
  statut: "charge" | "archive";
  quality_summary: QualitySummary | null;
  risk_config: RiskConfig | null;
  created_at: string;
}

export interface Subject {
  code: string;
  nom_fr: string;
  domaine: Domaine;
}

export interface Student {
  id: string;
  dataset_id: string;
  student_pseudo: string; // hash stable — clé technique, jamais le code national
  nom_complet: string | null; // nom réel (architecture privée/authentifiée, cf. supabase/schema.sql)
  age: number | null;
  niveau: string;
  classe: string;
  nb_matieres_suivies: number | null;
  moyenne_generale: number | null;
  dispersion_intermatiere: number | null;
  tendance_globale: number | null;
  a_risque: boolean;
  remarque_encodee: number | null;
}

export interface Grade {
  id: string;
  dataset_id: string;
  student_id: string;
  subject_code: string;
  c1: number | null;
  c2: number | null;
  c3: number | null;
  c4: number | null;
  activites: number | null;
  c1_colonne_existe: boolean;
  c2_colonne_existe: boolean;
  c3_colonne_existe: boolean;
  c4_colonne_existe: boolean;
  activites_colonne_existe: boolean;
  moyenne_matiere: number | null;
  n_composantes: number | null;
  tendance_matiere: number | null;
  remarque_fr: string | null;
}

export interface ModelRun {
  id: string;
  dataset_id: string;
  type: ModelRunType;
  algo: string;
  niveau: string | null;
  params: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  feature_columns: string[] | null;
  random_state: number | null;
  created_at: string;
}

export interface ClusterRow {
  id: string;
  dataset_id: string;
  student_id: string;
  model_run_id: string | null;
  cluster_id: number;
  cluster_label: string;
  pca_1: number | null;
  pca_2: number | null;
}

export interface Prediction {
  id: string;
  dataset_id: string;
  student_id: string;
  model_run_classification_id: string | null;
  model_run_regression_id: string | null;
  a_risque_predit: boolean | null;
  probabilite_risque: number | null;
  moyenne_generale_predite: number | null;
  explication_risque_fr: string | null;
  explication_moyenne_fr: string | null;
}

export interface RecommendationRow {
  id: string;
  dataset_id: string;
  student_id: string;
  priorite: Priorite;
  type: string;
  justification: string;
  action: string;
  matieres_concernees: string[];
  profil: string | null;
  tendance_previsionnelle_moyenne_predite: number | null;
  created_at: string;
}
