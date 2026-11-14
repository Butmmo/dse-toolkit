import { useCallback, useEffect, useState } from "react";

// Data lives in the browser (localStorage) so the app works offline and with no server.
// To go online later, replace read/write below with calls to your API (Supabase, Firebase, your own).
const KEY = (spec: string, c: string) => `${spec}:${c}`;
const listeners = new Set<() => void>();
export type Row = Record<string, string | number> & { id: string };

export function read(spec: string, c: string): Row[] {
  try { return JSON.parse(localStorage.getItem(KEY(spec, c)) ?? "[]") as Row[]; } catch { return []; }
}
function write(spec: string, c: string, rows: Row[]) {
  localStorage.setItem(KEY(spec, c), JSON.stringify(rows));
  listeners.forEach((l) => l());
}
export function useCollection(spec: string, c: string) {
  const [rows, setRows] = useState<Row[]>(() => read(spec, c));
  useEffect(() => {
    const on = () => setRows(read(spec, c));
    listeners.add(on);
    window.addEventListener("storage", on);
    return () => { listeners.delete(on); window.removeEventListener("storage", on); };
  }, [spec, c]);
  const add = useCallback((r: Omit<Row, "id">) => write(spec, c, [{ ...r, id: crypto.randomUUID() } as Row, ...read(spec, c)]), [spec, c]);
  const remove = useCallback((id: string) => write(spec, c, read(spec, c).filter((x) => x.id !== id)), [spec, c]);
  return { rows, add, remove };
}
