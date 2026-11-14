// TV remote support: arrow keys move focus to the nearest focusable item in that direction,
// OK/Enter presses it, and Back goes to the previous screen. Works with Samsung Tizen, LG webOS,
// Android TV browsers and a plain keyboard.
const SELECTOR = "a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex='-1'])";
const BACK_KEYS = new Set(["Escape", "Backspace", "BrowserBack", "GoBack"]);
const BACK_CODES = new Set([10009 /* Tizen */, 461 /* webOS */, 4 /* Android */]);

function visible(el: HTMLElement) {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
}
function nearest(from: HTMLElement, dir: string): HTMLElement | null {
  const a = from.getBoundingClientRect();
  const ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  let best: HTMLElement | null = null, bestScore = Infinity;
  document.querySelectorAll<HTMLElement>(SELECTOR).forEach((el) => {
    if (el === from || !visible(el)) return;
    const b = el.getBoundingClientRect();
    const dx = b.left + b.width / 2 - ax, dy = b.top + b.height / 2 - ay;
    const ok = dir === "ArrowRight" ? dx > 8 : dir === "ArrowLeft" ? dx < -8 : dir === "ArrowDown" ? dy > 8 : dy < -8;
    if (!ok) return;
    const along = dir === "ArrowLeft" || dir === "ArrowRight" ? Math.abs(dx) : Math.abs(dy);
    const across = dir === "ArrowLeft" || dir === "ArrowRight" ? Math.abs(dy) : Math.abs(dx);
    const score = along + across * 2.2;
    if (score < bestScore) { bestScore = score; best = el; }
  });
  return best;
}

export function startDpad() {
  document.addEventListener("keydown", (e) => {
    const t = e.target as HTMLElement;
    const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement;
    if (BACK_KEYS.has(e.key) || BACK_CODES.has(e.keyCode)) {
      if (typing && e.key === "Backspace") return;
      e.preventDefault();
      history.length > 1 ? history.back() : undefined;
      return;
    }
    if (!e.key.startsWith("Arrow")) return;
    const cur = (document.activeElement as HTMLElement) ?? document.body;
    if (typing && (e.key === "ArrowLeft" || e.key === "ArrowRight")) return;
    const next = cur === document.body ? document.querySelector<HTMLElement>(SELECTOR) : nearest(cur, e.key);
    if (next) { e.preventDefault(); next.focus({ preventScroll: false }); next.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }); }
  });
  window.addEventListener("load", () => document.querySelector<HTMLElement>(SELECTOR)?.focus());
}
