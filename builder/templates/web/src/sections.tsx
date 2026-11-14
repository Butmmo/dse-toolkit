import { useState } from "react";
import type { Block, FieldDef, Screen, Spec } from "./types";
import { useCollection, type Row } from "./store";

const money = (n: number, cur: string) => new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(n);

function Fields({ fields, values, set }: { fields: FieldDef[]; values: Record<string, string>; set: (n: string, v: string) => void }) {
  return (
    <>
      {fields.map((f) => (
        <div className="field" key={f.name}>
          <label htmlFor={`f-${f.name}`}>{f.label}</label>
          {f.type === "textarea" ? (
            <textarea id={`f-${f.name}`} required={f.required} value={values[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)} />
          ) : f.type === "select" ? (
            <select id={`f-${f.name}`} required={f.required} value={values[f.name] ?? f.options?.[0] ?? ""} onChange={(e) => set(f.name, e.target.value)}>
              {f.options?.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : (
            <input id={`f-${f.name}`} type={f.type} required={f.required} value={values[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)} />
          )}
        </div>
      ))}
    </>
  );
}

function defaults(fields: FieldDef[]) {
  return Object.fromEntries(fields.map((f) => [f.name, f.type === "select" ? f.options?.[0] ?? "" : ""]));
}

function FormBlock({ spec, b }: { spec: Spec; b: Extract<Block, { type: "form" }> }) {
  const { add } = useCollection(spec.slug, b.collection);
  const [v, setV] = useState<Record<string, string>>(() => defaults(b.fields));
  const [done, setDone] = useState(false);
  return (
    <section className="section"><div className="container" style={{ maxWidth: 640 }}>
      <h2>{b.title}</h2>
      {b.intro && <p className="muted">{b.intro}</p>}
      {done && <p className="note" role="status">{b.success}</p>}
      <form onSubmit={(e) => { e.preventDefault(); add(v as unknown as Omit<Row, "id">); setV(defaults(b.fields)); setDone(true); }}>
        <Fields fields={b.fields} values={v} set={(n, x) => { setDone(false); setV({ ...v, [n]: x }); }} />
        <button className="btn" type="submit">{b.submit}</button>
      </form>
    </div></section>
  );
}

function ListBlock({ spec, b }: { spec: Spec; b: Extract<Block, { type: "list" }> }) {
  const { rows, add, remove } = useCollection(spec.slug, b.collection);
  const [v, setV] = useState<Record<string, string>>(() => defaults(b.fields));
  return (
    <section className="section"><div className="container">
      <h2>{b.title}</h2>
      <div className="grid" style={{ gridTemplateColumns: b.addable ? "repeat(auto-fit,minmax(300px,1fr))" : "1fr", alignItems: "start" }}>
        {b.addable && (
          <form className="card" onSubmit={(e) => { e.preventDefault(); add(v as unknown as Omit<Row, "id">); setV(defaults(b.fields)); }}>
            <h3>Add new</h3>
            <Fields fields={b.fields} values={v} set={(n, x) => setV({ ...v, [n]: x })} />
            <button className="btn" type="submit">Add</button>
          </form>
        )}
        <div className="card">
          {rows.length === 0 ? <p className="empty">Nothing here yet.</p> : rows.map((r) => (
            <div className="row" key={r.id}>
              <div className="grow">
                <strong>{String(r[b.titleField] ?? "")}</strong>
                <div className="muted" style={{ fontSize: ".9rem" }}>{b.fields.filter((f) => f.name !== b.titleField && f.name !== b.badgeField).map((f) => r[f.name]).filter(Boolean).join(" · ")}</div>
              </div>
              {b.badgeField && r[b.badgeField] ? <span className="badge">{String(r[b.badgeField])}</span> : null}
              <button className="btn danger small" onClick={() => remove(r.id)} aria-label={`Delete ${String(r[b.titleField] ?? "item")}`}>Delete</button>
            </div>
          ))}
        </div>
      </div>
    </div></section>
  );
}

function Stat({ spec, it }: { spec: Spec; it: Extract<Block, { type: "stats" }>["items"][number] }) {
  const { rows } = useCollection(spec.slug, it.collection);
  const n = it.where ? rows.filter((r) => String(r[it.where!.field]) === it.where!.equals).length : rows.length;
  return <div className="card"><div className="stat">{n}</div><div className="muted">{it.label}</div></div>;
}

function StatsBlock({ spec, b }: { spec: Spec; b: Extract<Block, { type: "stats" }> }) {
  return (
    <section className="section"><div className="container"><div className="grid">
      {b.items.map((it) => <Stat key={it.label} spec={spec} it={it} />)}
    </div></div></section>
  );
}

function ProductsBlock({ spec, b }: { spec: Spec; b: Extract<Block, { type: "products" }> }) {
  const { rows, add } = useCollection(spec.slug, "cart");
  return (
    <section className="section"><div className="container">
      <h2>{b.title}</h2>
      <div className="grid">
        {b.items.map((p) => (
          <div className="card" key={p.id}>
            <div className="icon">{p.name.charAt(0)}</div>
            <h3>{p.name}</h3><p className="muted">{p.text}</p>
            <div className="price">{money(p.price, spec.currency)}</div>
            <button className="btn" style={{ marginTop: ".75rem" }} onClick={() => add({ name: p.name, price: p.price } as unknown as Omit<Row, "id">)}>Add to cart</button>
          </div>
        ))}
      </div>
      <p className="muted" role="status">{rows.length} in your cart</p>
    </div></section>
  );
}

function CartBlock({ spec, b }: { spec: Spec; b: Extract<Block, { type: "cart" }> }) {
  const { rows, remove } = useCollection(spec.slug, "cart");
  const total = rows.reduce((t, r) => t + Number(r.price), 0);
  return (
    <section className="section"><div className="container" style={{ maxWidth: 720 }}>
      <h2>{b.title}</h2>
      <div className="card">
        {rows.length === 0 ? <p className="empty">Your cart is empty.</p> : rows.map((r) => (
          <div className="row" key={r.id}><div className="grow">{String(r.name)}</div><strong>{money(Number(r.price), spec.currency)}</strong>
            <button className="btn danger small" onClick={() => remove(r.id)}>Remove</button></div>
        ))}
        {rows.length > 0 && <div className="row"><div className="grow"><strong>Total</strong></div><strong className="price" style={{ fontSize: "1.5rem" }}>{money(total, spec.currency)}</strong></div>}
      </div>
      {rows.length > 0 && <p className="muted" style={{ marginTop: "1rem" }}>Checkout is the next thing to build: connect a payment provider (Paystack, Stripe) in this screen.</p>}
    </div></section>
  );
}

function Render({ spec, b }: { spec: Spec; b: Block }) {
  switch (b.type) {
    case "hero":
      return (
        <section className="hero"><div className="container">
          {b.eyebrow && <span className="eyebrow">{b.eyebrow}</span>}
          <h1>{b.headline}</h1><p className="lead">{b.sub}</p>
          <div className="actions">
            {b.cta && <a className="btn" href={`#/${b.cta.to}`}>{b.cta.label}</a>}
            {b.cta2 && <a className="btn ghost" href={`#/${b.cta2.to}`}>{b.cta2.label}</a>}
          </div>
        </div></section>
      );
    case "features":
      return (
        <section className="section"><div className="container">
          {b.title && <h2>{b.title}</h2>}
          <div className="grid">{b.items.map((f, i) => (
            <div className="card" key={f.title}><div className="icon">{i + 1}</div><h3>{f.title}</h3><p className="muted">{f.text}</p></div>
          ))}</div>
        </div></section>
      );
    case "pricing":
      return (
        <section className="section"><div className="container"><h2>{b.title}</h2>
          <div className="grid">{b.tiers.map((t) => (
            <div className={`card${t.featured ? " featured" : ""}`} key={t.name}>
              <h3>{t.name}</h3><div className="price">{t.price} <small>{t.per}</small></div>
              <ul className="ticks">{t.features.map((f) => <li key={f}>{f}</li>)}</ul>
            </div>
          ))}</div>
        </div></section>
      );
    case "text":
      return (
        <section className="section"><div className="container" style={{ maxWidth: 760 }}>
          <h2>{b.title}</h2>{b.body.map((p, i) => <p key={i}>{p}</p>)}
        </div></section>
      );
    case "form": return <FormBlock spec={spec} b={b} />;
    case "list": return <ListBlock spec={spec} b={b} />;
    case "stats": return <StatsBlock spec={spec} b={b} />;
    case "products": return <ProductsBlock spec={spec} b={b} />;
    case "cart": return <CartBlock spec={spec} b={b} />;
  }
}

export function Blocks({ spec, screen }: { spec: Spec; screen: Screen }) {
  return <>{screen.blocks.map((b, i) => <Render key={`${screen.id}-${i}`} spec={spec} b={b} />)}</>;
}
