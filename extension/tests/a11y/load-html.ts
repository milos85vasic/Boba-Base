/**
 * @fileoverview Shared loader for the a11y suite (§11.4 anti-bluff).
 *
 * The a11y tests assert on the REAL committed entrypoint markup — NOT a fixture
 * copied into the test. We read the actual files
 *   src/entrypoints/popup/index.html
 *   src/entrypoints/options/index.html
 * off disk with `fs` and parse them into the jsdom `document` so every assertion
 * reflects exactly what ships to assistive technology. If a real a11y affordance
 * (role / aria-* / label association) is removed from the source HTML, the
 * corresponding test FAILS — the assertions are not tautologies over a fixture
 * the test itself authored.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Resolve from the process working directory. Vitest is invoked from the
// extension root (the a11y config sets `test.root` to that directory), so
// `process.cwd()` is the extension package root here. We deliberately avoid
// `import.meta.url` because under the jsdom environment it is not a `file:` URL
// and `fileURLToPath` rejects it.
const ENTRYPOINTS = resolve(process.cwd(), "src/entrypoints");

/** Absolute path to the popup entrypoint HTML that actually ships. */
export const POPUP_HTML_PATH = `${ENTRYPOINTS}/popup/index.html`;
/** Absolute path to the options entrypoint HTML that actually ships. */
export const OPTIONS_HTML_PATH = `${ENTRYPOINTS}/options/index.html`;

/** Read the raw HTML text of an entrypoint straight off disk. */
export function readEntrypointHtml(path: string): string {
  return readFileSync(path, "utf8");
}

/**
 * Look up an element by id, throwing a descriptive error if it is absent. This
 * narrows the type to a non-null `Element` WITHOUT a `!` non-null assertion
 * (the project ESLint forbids `@typescript-eslint/no-non-null-assertion`), so a
 * missing required element surfaces as a real test failure with a clear message.
 */
export function requireById(doc: Document, id: string): HTMLElement {
  const el = doc.getElementById(id);
  if (el === null) throw new Error(`expected element #${id} to exist in the markup`);
  return el;
}

/** Same as {@link requireById} but for a CSS selector. */
export function requireOne(root: ParentNode, selector: string): Element {
  const el = root.querySelector(selector);
  if (el === null) throw new Error(`expected an element matching "${selector}" to exist`);
  return el;
}

/**
 * Parse real entrypoint HTML into an isolated `Document` (jsdom) via
 * DOMParser, so multiple suites do not clobber a shared `document.body`.
 */
export function parseEntrypoint(path: string): Document {
  const html = readEntrypointHtml(path);
  return new DOMParser().parseFromString(html, "text/html");
}

/**
 * Compute the accessible name of an interactive control using the affordances
 * this markup actually relies on (a subset of the ARIA accessible-name
 * computation sufficient for these UIs):
 *   1. non-empty `aria-label`
 *   2. `aria-labelledby` → concatenated text of referenced element(s)
 *   3. an associated `<label for=id>` OR a wrapping `<label>`
 *   4. the control's own visible/trimmed text content (buttons/links)
 *   5. for inputs, a non-empty `title` as a last resort
 * Returns the trimmed accessible name, or "" when the control has none.
 */
export function accessibleName(el: Element, doc: Document): string {
  const ariaLabel = el.getAttribute("aria-label");
  if (ariaLabel && ariaLabel.trim() !== "") return ariaLabel.trim();

  const labelledby = el.getAttribute("aria-labelledby");
  if (labelledby) {
    const text = labelledby
      .split(/\s+/)
      .map((id) => doc.getElementById(id)?.textContent?.trim() ?? "")
      .filter((t) => t !== "")
      .join(" ")
      .trim();
    if (text !== "") return text;
  }

  const id = el.getAttribute("id");
  if (id) {
    const forLabel = doc.querySelector<HTMLLabelElement>(`label[for="${id}"]`);
    const forText = forLabel?.textContent?.trim();
    if (forText && forText !== "") return forText;
  }

  const wrappingLabel = el.closest("label");
  const wrapText = wrappingLabel?.textContent?.trim();
  if (wrapText && wrapText !== "") return wrapText;

  const own = el.textContent?.trim();
  if (own && own !== "") return own;

  const title = el.getAttribute("title");
  if (title && title.trim() !== "") return title.trim();

  return "";
}
