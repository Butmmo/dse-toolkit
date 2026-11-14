import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useEffect, useState } from "react";

// Data is saved on the phone (AsyncStorage), so the app works offline with no server.
// To go online later, replace load/save with calls to your API (Supabase, Firebase, your own).
export type Row = Record<string, string | number> & { id: string };
const listeners = new Set<() => void>();
const key = (spec: string, c: string) => `${spec}:${c}`;
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

async function load(spec: string, c: string): Promise<Row[]> {
  try { return JSON.parse((await AsyncStorage.getItem(key(spec, c))) ?? "[]") as Row[]; } catch { return []; }
}
async function save(spec: string, c: string, rows: Row[]) {
  await AsyncStorage.setItem(key(spec, c), JSON.stringify(rows));
  listeners.forEach((l) => l());
}

export function useCollection(spec: string, c: string) {
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => {
    let alive = true;
    const on = () => { load(spec, c).then((r) => alive && setRows(r)); };
    on();
    listeners.add(on);
    return () => { alive = false; listeners.delete(on); };
  }, [spec, c]);
  const add = useCallback(async (r: Omit<Row, "id">) => save(spec, c, [{ ...r, id: uid() } as Row, ...(await load(spec, c))]), [spec, c]);
  const remove = useCallback(async (id: string) => save(spec, c, (await load(spec, c)).filter((x) => x.id !== id)), [spec, c]);
  return { rows, add, remove };
}
