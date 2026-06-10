/**
 * @fileoverview Accessibility (a11y) tests for the REAL popup entrypoint markup
 * (`src/entrypoints/popup/index.html`) — Phase 6, §11.4 anti-bluff covenant.
 *
 * Every assertion parses the actual committed HTML off disk (see ./load-html.ts)
 * and checks a user-observable accessibility property for assistive technology:
 * status live-regions, accessible names on every interactive control, decorative
 * images hidden from AT, and the labelled relationship of the torrent list.
 *
 * ANTI-BLUFF (§11.4 / §11.4.69): each test is written to FAIL if the affordance
 * were removed from the source — e.g. dropping `role="status"`, an `aria-live`,
 * a button `aria-label`, the list `aria-labelledby`, or unhiding a decorative
 * image. They are not tautologies over a self-authored fixture.
 */
import { beforeAll, describe, expect, it } from "vitest";
import {
  POPUP_HTML_PATH,
  accessibleName,
  parseEntrypoint,
  requireById,
} from "./load-html";

describe("popup a11y — real entrypoint markup", () => {
  let doc: Document;

  beforeAll(() => {
    doc = parseEntrypoint(POPUP_HTML_PATH);
  });

  it("connection-status region announces via role=status + aria-live (catches: removed live region)", () => {
    const status = requireById(doc, "connection-status");
    // role="status" is an implicit live region; aria-live="polite" is the explicit one.
    expect(status.getAttribute("role")).toBe("status");
    expect(status.getAttribute("aria-live")).toBe("polite");
  });

  it("action-status SR region is a polite live region for action results (catches: silent results)", () => {
    const actionStatus = requireById(doc, "action-status");
    expect(actionStatus.getAttribute("role")).toBe("status");
    expect(actionStatus.getAttribute("aria-live")).toBe("polite");
  });

  it("connection-warning is an alert region (catches: removed role=alert)", () => {
    const warning = requireById(doc, "connection-warning");
    expect(warning.getAttribute("role")).toBe("alert");
  });

  it("Send-All button has an accessible name (catches: removed aria-label / empty button)", () => {
    const sendAll = requireById(doc, "btn-send-all");
    expect(sendAll.tagName).toBe("BUTTON");
    const name = accessibleName(sendAll, doc);
    expect(name).not.toBe("");
    // The real label names the destination so AT users know what "Send All" does.
    expect(name.toLowerCase()).toContain("send all");
  });

  it("Refresh button has an accessible name (catches: removed aria-label)", () => {
    const refresh = requireById(doc, "btn-refresh");
    const name = accessibleName(refresh, doc);
    expect(name).not.toBe("");
    expect(name.toLowerCase()).toContain("refresh");
  });

  it("the toolbar is a labelled toolbar landmark (catches: removed role/aria-label)", () => {
    const toolbar = requireById(doc, "toolbar");
    expect(toolbar.getAttribute("role")).toBe("toolbar");
    expect(accessibleName(toolbar, doc)).not.toBe("");
  });

  it("every <img> is hidden from AT or carries an alt attribute (catches: unhidden decorative icon)", () => {
    const imgs = Array.from(doc.querySelectorAll("img"));
    expect(imgs.length).toBeGreaterThan(0); // the header icon must be present
    for (const img of imgs) {
      const ariaHidden = img.getAttribute("aria-hidden") === "true";
      const hasAlt = img.hasAttribute("alt"); // alt="" is a valid decorative-hide too
      expect(
        ariaHidden || hasAlt,
        `<img id="${img.id}" src="${img.getAttribute("src")}"> must be aria-hidden or have alt`,
      ).toBe(true);
    }
  });

  it("the torrent list has a labelled relationship via aria-labelledby → existing heading (catches: orphaned list)", () => {
    const list = requireById(doc, "torrent-list");
    const labelledby = list.getAttribute("aria-labelledby");
    expect(labelledby, "torrent-list must be aria-labelledby a heading").toBeTruthy();
    // The referenced id MUST resolve to a real element with text — a dangling
    // aria-labelledby is an a11y bug this assertion catches.
    const heading = requireById(doc, String(labelledby));
    expect(heading.textContent?.trim()).not.toBe("");
  });

  it("STRUCTURAL: no interactive control lacks an accessible name (catches: any nameless button/input)", () => {
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
