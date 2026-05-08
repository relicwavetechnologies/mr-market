export function estimateTokens(text: string): number {
  // ~4 ASCII chars/token; non-ASCII (Devanagari, etc.) tokenizes at ~2 chars/token.
  const nonAscii = (text.match(/[^\x00-\x7F]/g) ?? []).length;
  const ascii = text.length - nonAscii;
  return Math.ceil(ascii / 4 + nonAscii / 2);
}
