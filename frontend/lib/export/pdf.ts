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
 * le PDF les affiche en glyphes corrompus, illisibles.
 *
 * IMPORTANT — ne PAS pré-traiter le texte arabe soi-même. jsPDF a un plugin
 * "arabic" interne (jsPDFAPI.processArabic) qui s'exécute automatiquement à
 * CHAQUE appel de doc.text() (et donc aussi depuis jspdf-autotable, qui
 * appelle doc.text() en interne) via un hook "preProcessText" — il fait le
 * "shaping" (formes de lettres liées) ET le réordonnancement visuel
 * droite-à-gauche tout seul. Vérifié empiriquement : passer la chaîne
 * source brute donne l'ordre visuel correct (comparé caractère par
 * caractère à la référence arabic-reshaper + python-bidi). Une tentative
 * précédente rappelait processArabic() manuellement PUIS inversait la
 * chaîne soi-même avant de la passer à autoTable — cela déclenchait le hook
 * une seconde fois (processArabic reconnaît aussi le bloc Unicode "formes
 * de présentation" en sortie) et inversait l'ordre une deuxième fois,
 * annulant le premier réordonnancement : le nom entier apparaissait dans le
 * bon sens de lecture MAIS lettre par lettre à l'envers dans chaque mot.
 * Confirmé en comparant les positions x réelles des glyphes dans le PDF
 * généré à la référence bidi, pas seulement "à l'œil". */
const ARABIC_RANGE = /[؀-ۿݐ-ݿ]/;

/** Aligne à droite les cellules arabes (lecture RTL) plutôt que de les
 * laisser à gauche par défaut — sinon la mise en page suggère du texte
 * latin mal centré, alors que le contenu se lit dans l'autre sens. jsPDF
 * gère le shaping/réordonnancement des glyphes tout seul (cf. note
 * ci-dessus) ; ceci ne touche qu'à la position de la cellule, jamais au
 * contenu texte lui-même. */
function alignCellForPdf(cell: string | number): string | number | { content: string | number; styles: { halign: "right" } } {
  if (typeof cell !== "string" || !ARABIC_RANGE.test(cell)) return cell;
  return { content: cell, styles: { halign: "right" } };
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
      doc.text(table.title, marginLeft, cursorY);
      cursorY += 6;
    }
    autoTable(doc, {
      head: [table.head],
      body: table.body.map((row) => row.map((cell) => alignCellForPdf(cell))),
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
