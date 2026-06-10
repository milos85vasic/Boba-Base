/**
 * @fileoverview Accessibility (a11y) tests for the REAL options entrypoint markup
 * (`src/entrypoints/options/index.html`) — Phase 6, §11.4 anti-bluff covenant.
 *
 * Parses the actual committed HTML off disk (see ./load-html.ts) and asserts the
 * tab/panel ARIA pattern, label associations for every form control, and the
 * save-status live region — all user-observable for assistive technology.
 *
 * ANTI-BLUFF (§11.4 / §11.4.69): each test FAILS if the real affordance is
 * removed — e.g. a tab losing `aria-controls`, an `aria-controls` pointing at a
 * non-existent panel, an `<input>` losing its associated `<label for>`, or the
 * save-status losing `aria-live`. Not tautologies over a self-authored fixture.
 */
import { beforeAll, describe, expect, it } from "vitest";
import {
  OPTIONS_HTML_PATH,
  accessibleName,
  parseEntrypoint,
  requireById,
  requireOne,
} from "./load-html";

describe("options a11y — real entrypoint markup", () => {
  let doc: Document;

  beforeAll(() => {
    doc = parseEntrypoint(OPTIONS_HTML_PATH);
  });

  it("exposes exactly 7 tabs in a tablist (catches: added/removed tab or missing role)", () => {
    requireOne(doc, '[role="tablist"]'); // a [role=tablist] container must exist
    const tabs = Array.from(doc.querySelectorAll('[role="tab"]'));
    expect(tabs.length).toBe(7);
  });

  it("each tab's aria-controls points to an EXISTING tabpanel (catches: dangling aria-controls)", () => {
    const tabs = Array.from(doc.querySelectorAll('[role="tab"]'));
    for (const tab of tabs) {
      const controls = tab.getAttribute("aria-controls");
      expect(controls, `tab #${tab.id} must have aria-controls`).toBeTruthy();
      // requireById throws (test fails) on a dangling reference.
      const panel = requireById(doc, String(controls));
      // The referenced element must actually be a tabpanel — a tab controlling a
      // non-panel is a broken relationship this assertion catches.
      expect(panel.getAttribute("role")).toBe("tabpanel");
    }
  });

  it("each tab declares aria-selected as a valid boolean (catches: removed/invalid selection state)", () => {
    const tabs = Array.from(doc.querySelectorAll('[role="tab"]'));
    for (const tab of tabs) {
      const selected = tab.getAttribute("aria-selected");
      expect(selected, `tab #${tab.id} must declare aria-selected`).toBeTruthy();
      expect(["true", "false"]).toContain(selected);
    }
    // Exactly one tab is selected at rest — a tablist with zero or many selected
    // tabs is an a11y defect.
    const selectedCount = tabs.filter((t) => t.getAttribute("aria-selected") === "true").length;
    expect(selectedCount).toBe(1);
  });

  it("every tabpanel is labelled by its controlling tab (catches: orphaned panel)", () => {
    const panels = Array.from(doc.querySelectorAll('[role="tabpanel"]'));
    expect(panels.length).toBe(7);
    for (const panel of panels) {
      const labelledby = panel.getAttribute("aria-labelledby");
      expect(labelledby, `panel #${panel.id} must be aria-labelledby its tab`).toBeTruthy();
      const tab = requireById(doc, String(labelledby));
      expect(tab.getAttribute("role")).toBe("tab");
      // The relationship must be reciprocal: the tab controls this panel.
      expect(tab.getAttribute("aria-controls")).toBe(panel.id);
    }
  });

  it("every <input> has an associated label (for/id or wrapping) (catches: unlabelled field)", () => {
    const inputs = Array.from(doc.querySelectorAll<HTMLInputElement>("input"));
    expect(inputs.length).toBeGreaterThan(0);
    const unlabelled = inputs.filter((input) => accessibleName(input, doc) === "");
    expect(
      unlabelled.map((el) => `input#${el.id || "(no-id)"}[type=${el.type}]`),
      "inputs without an associated label",
    ).toEqual([]);
  });

  it("every <select> has an associated label (catches: unlabelled dropdown)", () => {
    const selects = Array.from(doc.querySelectorAll<HTMLSelectElement>("select"));
    expect(selects.length).toBeGreaterThan(0);
    const unlabelled = selects.filter((sel) => accessibleName(sel, doc) === "");
    expect(
      unlabelled.map((el) => `select#${el.id || "(no-id)"}`),
      "selects without an associated label",
    ).toEqual([]);
  });

  it("save-status region is a polite live region (catches: silent save feedback)", () => {
    const saveStatus = requireById(doc, "opt-save-status");
    expect(saveStatus.getAttribute("role")).toBe("status");
    expect(saveStatus.getAttribute("aria-live")).toBe("polite");
  });

  it("the settings navigation is a labelled landmark (catches: removed nav label)", () => {
    const nav = requireOne(doc, "nav");
    expect(accessibleName(nav, doc)).not.toBe("");
  });

  it("STRUCTURAL: no interactive control lacks an accessible name (catches: any nameless control)", () => {
    const controls = Array.from(
      doc.querySelectorAll<HTMLElement>("button, input, select, a[href]"),
    );
    expect(controls.length).toBeGreaterThan(0);
    const nameless = controls.filter((el) => accessibleName(el, doc) === "");
    expect(
      nameless.map((el) => `${el.tagName}#${el.id || "(no-id)"}`),
      "interactive controls without an accessible name",
    ).toEqual([]);
  });
});
