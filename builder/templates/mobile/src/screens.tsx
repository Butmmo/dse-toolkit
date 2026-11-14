import { useState } from "react";
import { Pressable, Text, TextInput, View, StyleSheet } from "react-native";
import type { Block, FieldDef, Screen, Spec } from "./types";
import { useCollection, type Row } from "./store";
import { useTheme, type Theme } from "./theme";

const money = (n: number, cur: string) => { try { return new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(n); } catch { return `${cur} ${n}`; } };
const defaults = (fields: FieldDef[]) => Object.fromEntries(fields.map((f) => [f.name, f.type === "select" ? f.options?.[0] ?? "" : ""])) as Record<string, string>;

function Button({ t, label, onPress, ghost, danger, small }: { t: Theme; label: string; onPress: () => void; ghost?: boolean; danger?: boolean; small?: boolean }) {
  const bg = ghost || danger ? "transparent" : t.brand;
  const fg = danger ? t.danger : ghost ? t.ink : t.onBrand;
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={({ pressed }) => [styles.btn, small && styles.btnSmall, { backgroundColor: bg, borderColor: danger ? t.danger : ghost ? t.line : bg, opacity: pressed ? 0.8 : 1 }]}>
      <Text style={{ color: fg, fontWeight: "700", fontSize: small ? 13 : 15 }}>{label}</Text>
    </Pressable>
  );
}

function Card({ t, children, featured }: { t: Theme; children: React.ReactNode; featured?: boolean }) {
  return <View style={[styles.card, { backgroundColor: t.surface, borderColor: featured ? t.brand : t.line, borderWidth: featured ? 2 : 1 }]}>{children}</View>;
}

function Fields({ t, fields, values, set }: { t: Theme; fields: FieldDef[]; values: Record<string, string>; set: (n: string, v: string) => void }) {
  return (
    <>
      {fields.map((f) => (
        <View key={f.name} style={{ marginBottom: 12 }}>
          <Text style={{ color: t.ink, fontWeight: "700", marginBottom: 4 }}>{f.label}</Text>
          {f.type === "select" ? (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {f.options?.map((o) => {
                const on = (values[f.name] ?? f.options?.[0]) === o;
                return (
                  <Pressable key={o} onPress={() => set(f.name, o)} style={[styles.chip, { borderColor: on ? t.brand : t.line, backgroundColor: on ? t.tint : "transparent" }]}>
                    <Text style={{ color: on ? t.brandStrong : t.ink, fontWeight: "600" }}>{o}</Text>
                  </Pressable>
                );
              })}
            </View>
          ) : (
            <TextInput
              value={values[f.name] ?? ""} onChangeText={(x) => set(f.name, x)} placeholderTextColor={t.muted}
              placeholder={f.type === "date" ? "YYYY-MM-DD" : f.type === "time" ? "HH:MM" : ""}
              multiline={f.type === "textarea"} keyboardType={f.type === "email" ? "email-address" : f.type === "number" ? "numeric" : "default"}
              autoCapitalize={f.type === "email" ? "none" : "sentences"}
              style={[styles.input, { color: t.ink, borderColor: t.line, backgroundColor: t.surface, minHeight: f.type === "textarea" ? 100 : undefined, textAlignVertical: f.type === "textarea" ? "top" : "center" }]}
            />
          )}
        </View>
      ))}
    </>
  );
}

function FormBlock({ spec, b, t }: { spec: Spec; b: Extract<Block, { type: "form" }>; t: Theme }) {
  const { add } = useCollection(spec.slug, b.collection);
  const [v, setV] = useState(() => defaults(b.fields));
  const [done, setDone] = useState(false);
  return (
    <View style={styles.section}>
      <Text style={[styles.h2, { color: t.ink }]}>{b.title}</Text>
      {b.intro ? <Text style={{ color: t.muted, marginBottom: 12 }}>{b.intro}</Text> : null}
      {done ? <Text style={[styles.note, { backgroundColor: t.tint, color: t.brandStrong }]}>{b.success}</Text> : null}
      <Fields t={t} fields={b.fields} values={v} set={(n, x) => { setDone(false); setV({ ...v, [n]: x }); }} />
      <Button t={t} label={b.submit} onPress={async () => { await add(v as unknown as Omit<Row, "id">); setV(defaults(b.fields)); setDone(true); }} />
    </View>
  );
}

function ListBlock({ spec, b, t }: { spec: Spec; b: Extract<Block, { type: "list" }>; t: Theme }) {
  const { rows, add, remove } = useCollection(spec.slug, b.collection);
  const [v, setV] = useState(() => defaults(b.fields));
  return (
    <View style={styles.section}>
      <Text style={[styles.h2, { color: t.ink }]}>{b.title}</Text>
      {b.addable && (
        <Card t={t}>
          <Text style={[styles.h3, { color: t.ink }]}>Add new</Text>
          <Fields t={t} fields={b.fields} values={v} set={(n, x) => setV({ ...v, [n]: x })} />
          <Button t={t} label="Add" onPress={async () => { await add(v as unknown as Omit<Row, "id">); setV(defaults(b.fields)); }} />
        </Card>
      )}
      <Card t={t}>
        {rows.length === 0 ? <Text style={{ color: t.muted, textAlign: "center", padding: 16 }}>Nothing here yet.</Text> : rows.map((r) => (
          <View key={r.id} style={[styles.row, { borderColor: t.line }]}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: t.ink, fontWeight: "700" }}>{String(r[b.titleField] ?? "")}</Text>
              <Text style={{ color: t.muted, fontSize: 13 }}>{b.fields.filter((f) => f.name !== b.titleField && f.name !== b.badgeField).map((f) => r[f.name]).filter(Boolean).join(" · ")}</Text>
            </View>
            {b.badgeField && r[b.badgeField] ? <Text style={[styles.badge, { backgroundColor: t.tint, color: t.brandStrong }]}>{String(r[b.badgeField])}</Text> : null}
            <Button t={t} label="Delete" danger small onPress={() => remove(r.id)} />
          </View>
        ))}
      </Card>
    </View>
  );
}

function Stat({ spec, it, t }: { spec: Spec; it: Extract<Block, { type: "stats" }>["items"][number]; t: Theme }) {
  const { rows } = useCollection(spec.slug, it.collection);
  const n = it.where ? rows.filter((r) => String(r[it.where!.field]) === it.where!.equals).length : rows.length;
  return <View style={{ flex: 1, minWidth: 140 }}><Card t={t}><Text style={{ fontSize: 34, fontWeight: "800", color: t.brandStrong }}>{n}</Text><Text style={{ color: t.muted }}>{it.label}</Text></Card></View>;
}

function Cart({ spec, b, t }: { spec: Spec; b: Extract<Block, { type: "cart" }>; t: Theme }) {
  const { rows, remove } = useCollection(spec.slug, "cart");
  const total = rows.reduce((a, r) => a + Number(r.price), 0);
  return (
    <View style={styles.section}>
      <Text style={[styles.h2, { color: t.ink }]}>{b.title}</Text>
      <Card t={t}>
        {rows.length === 0 ? <Text style={{ color: t.muted, textAlign: "center", padding: 16 }}>Your cart is empty.</Text> : rows.map((r) => (
          <View key={r.id} style={[styles.row, { borderColor: t.line }]}>
            <Text style={{ flex: 1, color: t.ink }}>{String(r.name)}</Text>
            <Text style={{ color: t.ink, fontWeight: "700" }}>{money(Number(r.price), spec.currency)}</Text>
            <Button t={t} label="Remove" danger small onPress={() => remove(r.id)} />
          </View>
        ))}
        {rows.length > 0 && <Text style={{ color: t.ink, fontWeight: "800", fontSize: 18, marginTop: 10 }}>Total {money(total, spec.currency)}</Text>}
      </Card>
    </View>
  );
}

function Products({ spec, b, t }: { spec: Spec; b: Extract<Block, { type: "products" }>; t: Theme }) {
  const { rows, add } = useCollection(spec.slug, "cart");
  return (
    <View style={styles.section}>
      <Text style={[styles.h2, { color: t.ink }]}>{b.title}</Text>
      {b.items.map((p) => (
        <Card key={p.id} t={t}>
          <Text style={[styles.h3, { color: t.ink }]}>{p.name}</Text>
          <Text style={{ color: t.muted, marginBottom: 6 }}>{p.text}</Text>
          <Text style={{ fontSize: 24, fontWeight: "800", color: t.ink, marginBottom: 10 }}>{money(p.price, spec.currency)}</Text>
          <Button t={t} label="Add to cart" onPress={() => add({ name: p.name, price: p.price } as unknown as Omit<Row, "id">)} />
        </Card>
      ))}
      <Text style={{ color: t.muted }}>{rows.length} in your cart</Text>
    </View>
  );
}

function Render({ spec, b, t, go }: { spec: Spec; b: Block; t: Theme; go: (id: string) => void }) {
  switch (b.type) {
    case "hero":
      return (
        <View style={[styles.hero, { backgroundColor: t.tint }]}>
          {b.eyebrow ? <Text style={[styles.eyebrow, { color: t.brandStrong }]}>{b.eyebrow.toUpperCase()}</Text> : null}
          <Text style={[styles.h1, { color: t.ink }]}>{b.headline}</Text>
          <Text style={{ color: t.muted, fontSize: 16, marginBottom: 16 }}>{b.sub}</Text>
          <View style={{ flexDirection: "row", gap: 10, flexWrap: "wrap" }}>
            {b.cta ? <Button t={t} label={b.cta.label} onPress={() => go(b.cta!.to)} /> : null}
            {b.cta2 ? <Button t={t} label={b.cta2.label} ghost onPress={() => go(b.cta2!.to)} /> : null}
          </View>
        </View>
      );
    case "features":
      return (
        <View style={styles.section}>
          {b.title ? <Text style={[styles.h2, { color: t.ink }]}>{b.title}</Text> : null}
          {b.items.map((f, i) => <Card key={f.title} t={t}><Text style={{ color: t.brandStrong, fontWeight: "800" }}>{i + 1}</Text><Text style={[styles.h3, { color: t.ink }]}>{f.title}</Text><Text style={{ color: t.muted }}>{f.text}</Text></Card>)}
        </View>
      );
    case "pricing":
      return (
        <View style={styles.section}>
          <Text style={[styles.h2, { color: t.ink }]}>{b.title}</Text>
          {b.tiers.map((x) => (
            <Card key={x.name} t={t} featured={x.featured}>
              <Text style={[styles.h3, { color: t.ink }]}>{x.name}</Text>
              <Text style={{ fontSize: 28, fontWeight: "800", color: t.ink }}>{x.price} <Text style={{ fontSize: 14, color: t.muted }}>{x.per}</Text></Text>
              {x.features.map((f) => <Text key={f} style={{ color: t.ink, marginTop: 6 }}>{"✓  "}{f}</Text>)}
            </Card>
          ))}
        </View>
      );
    case "text":
      return <View style={styles.section}><Text style={[styles.h2, { color: t.ink }]}>{b.title}</Text>{b.body.map((p, i) => <Text key={i} style={{ color: t.ink, marginBottom: 10, lineHeight: 22 }}>{p}</Text>)}</View>;
    case "stats":
      return <View style={[styles.section, { flexDirection: "row", flexWrap: "wrap", gap: 10 }]}>{b.items.map((it) => <Stat key={it.label} spec={spec} it={it} t={t} />)}</View>;
    case "form": return <FormBlock spec={spec} b={b} t={t} />;
    case "list": return <ListBlock spec={spec} b={b} t={t} />;
    case "products": return <Products spec={spec} b={b} t={t} />;
    case "cart": return <Cart spec={spec} b={b} t={t} />;
  }
}

export function Blocks({ spec, screen, go }: { spec: Spec; screen: Screen; go: (id: string) => void }) {
  const t = useTheme();
  return <>{screen.blocks.map((b, i) => <Render key={`${screen.id}-${i}`} spec={spec} b={b} t={t} go={go} />)}</>;
}

const styles = StyleSheet.create({
  section: { paddingHorizontal: 16, paddingVertical: 14 },
  hero: { padding: 20, paddingTop: 28, paddingBottom: 28 },
  eyebrow: { fontSize: 12, fontWeight: "800", letterSpacing: 1.2, marginBottom: 8 },
  h1: { fontSize: 32, fontWeight: "800", letterSpacing: -0.5, marginBottom: 10 },
  h2: { fontSize: 24, fontWeight: "800", letterSpacing: -0.3, marginBottom: 10 },
  h3: { fontSize: 17, fontWeight: "700", marginBottom: 4 },
  card: { borderRadius: 16, padding: 16, marginBottom: 12 },
  btn: { borderWidth: 1.5, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 18, alignItems: "center", alignSelf: "flex-start" },
  btnSmall: { paddingVertical: 6, paddingHorizontal: 10, borderRadius: 10 },
  input: { borderWidth: 1.5, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16 },
  chip: { borderWidth: 1.5, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  badge: { fontSize: 12, fontWeight: "800", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  note: { padding: 12, borderRadius: 12, fontWeight: "700", marginBottom: 12, overflow: "hidden" },
});
