import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import { AMIRI_REGULAR_BASE64 } from "./fonts/amiri-base64";

/** Génère un PDF simple : titre, sous-titre (année scolaire), un ou
 * plusieurs tableaux. jsPDF + jspdf-autotable plutôt qu'une dépendance
 * lourde (pdfkit tire fontkit/brotli pour le rendu de police avancé,
 * @react-pdf/renderer un moteur de mise en page complet) — nos exports sont
 * des tableaux plats, pas de mise en page complexe à composer.
 *
 * Police Amiri (arabe + latin, SIL OFL, cf. fonts/OFL.txt) embarquée plutôt
 * que les polices intégrées de jsPDF (Helvetica etc., latin uniquement) :
 * les élèves réels de ce projet ont des noms en écriture arabe — sans ça,
 * le PDF les affiche en glyphes corrompus, illisibles. */
const ARABIC_RANGE = /[؀-ۿݐ-ݿ]/;

/** jsPDF.processArabic() ne fait que le "shaping" (formes initiale/médiane/
 * finale/isolée correctement liées) — pas l'inversion visuelle droite-à-
 * gauche, que jsPDF ne fait pas automatiquement pour du texte de tableau
 * (jspdf-autotable n'a aucun support RTL). Sans cette inversion, les lettres
 * sont bien liées mais dans le mauvais sens de lecture. Une simple
 * inversion de chaîne suffit ici : ce sont des noms/mots isolés, pas des
 * phrases mêlant arabe et ponctuation/chiffres latins qui demanderaient un
 * vrai algorithme bidi (Unicode UAX #9). */
function shapeForPdf(doc: jsPDF, value: string): string {
  if (!ARABIC_RANGE.test(value)) return value;
  const shaped = doc.processArabic(value);
  return [...shaped].reverse().join("");
}

/** Aligne à droite les cellules arabes (lecture RTL) plutôt que de les
 * laisser à gauche par défaut — sinon la mise en page suggère du texte
 * latin mal centré, alors que le contenu se lit dans l'autre sens. Détecté
 * sur la valeur d'origine : après shapeForPdf, les caractères sont dans le
 * bloc Unicode "formes de présentation arabes", pas celui testé ici. */
function shapeCellForPdf(doc: jsPDF, cell: string | number): string | number | { content: string; styles: { halign: "right" } } {
  if (typeof cell !== "string" || !ARABIC_RANGE.test(cell)) return cell;
  return { content: shapeForPdf(doc, cell), styles: { halign: "right" } };
}

export interface PdfTable {
  title?: string;
  head: string[];
  body: (string | number)[][];
}

export function buildPdf(title: string, subtitle: string, tables: PdfTable[]): ArrayBuffer {
  const doc = new jsPDF({ orientation: "landscape", unit: "pt" });
  doc.addFileToVFS("Amiri-Regular.ttf", AMIRI_REGULAR_BASE64);
  doc.addFont("Amiri-Regular.ttf", "Amiri", "normal");
  doc.setFont("Amiri");

  const marginLeft = 32;
  let cursorY = 40;

  doc.setFontSize(14);
  doc.text(title, marginLeft, cursorY);
  cursorY += 18;
  doc.setFontSize(10);
  doc.setTextColor(90);
  doc.text(subtitle, marginLeft, cursorY);
  doc.setTextColor(0);
  cursorY += 10;

  for (const table of tables) {
    if (table.title) {
      cursorY += 16;
      doc.setFontSize(11);
      doc.text(shapeForPdf(doc, table.title), marginLeft, cursorY);
      cursorY += 6;
    }
    autoTable(doc, {
      head: [table.head],
      body: table.body.map((row) => row.map((cell) => shapeCellForPdf(doc, cell))),
      startY: cursorY + 6,
      margin: { left: marginLeft, right: marginLeft },
      styles: { fontSize: 8, cellPadding: 4, font: "Amiri" },
      headStyles: { fillColor: [59, 91, 219], font: "Amiri" }, // --accent
      didDrawPage: (data) => {
        cursorY = data.cursor?.y ?? cursorY;
      },
    });
    // @ts-expect-error — jspdf-autotable étend jsPDF avec cette propriété à l'exécution
    cursorY = doc.lastAutoTable.finalY;
  }

  return doc.output("arraybuffer");
}
