import { useEffect, useState } from "react";
import type { Spec } from "./types";
import { Blocks } from "./sections";

// A tiny hash router: "#/pricing" shows the screen with id "pricing". Works on any host, in Electron and on TV.
function useRoute(spec: Spec) {
  const get = () => location.hash.replace(/^#\/?/, "") || spec.screens[0].id;
  const [id, setId] = useState(get);
  useEffect(() => {
    const on = () => { setId(get()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return spec.screens.find((s) => s.id === id) ?? spec.screens[0];
}

export default function App({ spec }: { spec: Spec }) {
  const screen = useRoute(spec);
  const [open, setOpen] = useState(false);
  useEffect(() => { document.title = `${screen.title} | ${spec.name}`; setOpen(false); }, [screen, spec.name]);
  return (
    <>
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
      <header className="site-header">
        <div className="container bar">
          <a className="brand" href={`#/${spec.screens[0].id}`}><span className="mark">{spec.name.charAt(0).toUpperCase()}</span>{spec.name}</a>
          <button className="menu-btn" aria-expanded={open} aria-controls="nav" onClick={() => setOpen(!open)}>Menu</button>
          <nav id="nav" className={`nav${open ? " open" : ""}`} aria-label="Main">
            {spec.screens.map((s) => (
              <a key={s.id} href={`#/${s.id}`} aria-current={s.id === screen.id ? "page" : undefined}>{s.title}</a>
            ))}
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} style={{ outline: "none" }}>
        <Blocks spec={spec} screen={screen} />
      </main>
      <footer className="site-footer">
        <div className="container">&copy; {new Date().getFullYear()} {spec.name}. {spec.tagline}</div>
      </footer>
    </>
  );
}
