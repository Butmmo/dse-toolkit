export type FieldDef = { name: string; label: string; type: "text" | "email" | "date" | "time" | "number" | "textarea" | "select"; options?: string[]; required?: boolean };
export type Block =
  | { type: "hero"; eyebrow?: string; headline: string; sub: string; cta?: { label: string; to: string }; cta2?: { label: string; to: string } }
  | { type: "features"; title?: string; items: { title: string; text: string }[] }
  | { type: "stats"; items: { label: string; collection: string; where?: { field: string; equals: string } }[] }
  | { type: "list"; title: string; collection: string; fields: FieldDef[]; titleField: string; badgeField?: string; addable: boolean }
  | { type: "form"; title: string; intro?: string; collection: string; fields: FieldDef[]; submit: string; success: string }
  | { type: "products"; title: string; items: { id: string; name: string; price: number; text: string }[] }
  | { type: "cart"; title: string }
  | { type: "pricing"; title: string; tiers: { name: string; price: string; per: string; features: string[]; featured?: boolean }[] }
  | { type: "text"; title: string; body: string[] };
export type Screen = { id: string; title: string; blocks: Block[] };
export type Spec = { name: string; slug: string; tagline: string; description: string; platform: "web" | "desktop" | "tv"; currency: string; screens: Screen[] };
