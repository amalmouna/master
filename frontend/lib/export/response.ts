/** En-têtes communs aux réponses d'export : jamais mis en cache (ni
 * navigateur, ni CDN Vercel/Cloudflare) — ces fichiers contiennent des noms
 * réels d'élèves, un outil interne authentifié, jamais une route publique. */
export function exportHeaders(contentType: string, filename: string): HeadersInit {
  return {
    "Content-Type": contentType,
    "Content-Disposition": `attachment; filename="${filename}"`,
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    Pragma: "no-cache",
  };
}
