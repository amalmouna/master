/** Génération CSV minimale, dédiée aux exports administratifs (§2.7). Pas de
 * dépendance : le format est simple (une ligne d'en-tête + lignes de
 * données), l'échappement RFC 4180 tient en quelques lignes. */
function escapeCsvCell(value: string | number | null): string {
  if (value === null) return "";
  const s = String(value);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** BOM UTF-8 en tête : sans lui, Excel (Windows, le contexte réel de ce
 * projet) affiche les caractères accentués comme du charabia. */
const UTF8_BOM = "﻿";

export function buildCsv(headers: string[], rows: (string | number | null)[][]): string {
  const lines = [headers, ...rows].map((row) => row.map(escapeCsvCell).join(","));
  return UTF8_BOM + lines.join("\r\n") + "\r\n";
}
