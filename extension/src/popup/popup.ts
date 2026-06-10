/**
 * @fileoverview Popup UI logic for BobaLink (Phase 3, F popup REFACTOR).
 *
 * Displays the torrents detected on the active tab — queried from the
 * background service worker via `chrome.runtime.sendMessage` — as an
 * accessible list. Each row carries the display name, a short infohash, and a
 * per-torrent Send button; a Send-All button dispatches every detected id; a
 * connection-status indicator reflects the background health-check; a footer
 * link opens the options page.
 *
 * REFACTOR notes vs the reference (`docs/research/.../popup/popup.ts`):
 *  - The reference grabbed DOM nodes at module top-level and auto-ran on
 *    import, so it could not be exercised in jsdom. This module exposes a
 *    pure `initPopup(doc)` factory that takes the document, wires everything,
 *    and returns once the initial render + status check complete — making it
 *    unit-testable. Auto-run only happens in a real document context.
 *  - Torrent data is rendered with safe DOM APIs (`textContent` /
 *    `createElement`), never `innerHTML`, so untrusted names/hashes cannot
 *    inject markup.
 *  - Adds per-row Send buttons + a Send-All button (the spec's
 *    "Send button per torrent + a Send-All button").
 *
 * The popup talks to the background ONLY via messages — it imports no api/
 * client and performs no crypto.
 *
 * @module popup/popup
 */

import { createLogger } from "../shared/logger";
import { truncate } from "../shared/utils";
import { EXT } from "../shared/constants";
import type { DetectedTorrent } from "../types/torrent";
import type {
  ExtensionMessage,
  ExtensionMessageResponse,
  MessageType,
} from "../types/api";

const log = createLogger("Popup");

/** Length of the infohash prefix shown in each row. */
const SHORT_INFOHASH_LEN = 16;

/** Connection-status visual state. */
type StatusState = "online" | "offline" | "warning";

/**
 * Send a typed message to the background service worker.
 *
 * Thin wrapper over `chrome.runtime.sendMessage` so the call sites stay typed
 * and a single place handles the `ExtensionMessageResponse` shape.
 */
async function sendMessage(
  type: MessageType,
  payload?: Record<string, unknown>,
): Promise<ExtensionMessageResponse> {
  const message: ExtensionMessage = payload ? { type, payload } : { type };
  const res: ExtensionMessageResponse | undefined =
    await chrome.runtime.sendMessage(message);
  return res ?? { success: false };
}

/**
 * Initialize the popup against a given document.
 *
 * Queries the active tab + background for detected torrents and health, renders
 * the list, and wires every interactive control. Resolves once the initial
 * render and the status check have both completed, so tests can await it.
 *
 * @param doc - The document to operate on (the real popup document in the
 *   browser, a jsdom document in tests).
 */
export async function initPopup(doc: Document): Promise<void> {
  log.debug("Popup initializing");

  const listNode = doc.getElementById("torrent-list");
  const emptyNode = doc.getElementById("empty-state");
  const sendAllNode = doc.getElementById("btn-send-all") as HTMLButtonElement | null;
  const refreshBtn = doc.getElementById("btn-refresh");
  const statusTextEl = doc.getElementById("status-text");
  const statusDotEl = doc.getElementById("status-dot");
  const warningEl = doc.getElementById("connection-warning");
  const actionStatusEl = doc.getElementById("action-status");

  if (!listNode || !emptyNode || !sendAllNode) {
    log.error("Popup DOM is missing required nodes");
    return;
  }

  // Non-null bindings the nested closures can rely on (the guard above narrows
  // these once; `const` keeps the narrowing inside the closures).
  const listEl: HTMLElement = listNode;
  const emptyEl: HTMLElement = emptyNode;
  const sendAllBtn: HTMLButtonElement = sendAllNode;

  /** The torrents currently rendered (source of truth for Send-All). */
  let current: DetectedTorrent[] = [];

  /** Announce an action result to the screen-reader live region. */
  function announce(text: string): void {
    if (actionStatusEl) actionStatusEl.textContent = text;
  }

  /** Set the connection-status dot + label. */
  function setStatus(state: StatusState, text: string): void {
    if (statusTextEl) statusTextEl.textContent = text;
    if (statusDotEl) {
      statusDotEl.className = "status-dot";
      statusDotEl.classList.add(`status-${state}`);
    }
  }

  /** Build one accessible <li> row for a detected torrent. */
  function makeRow(torrent: DetectedTorrent): HTMLLIElement {
    const item = doc.createElement("li");
    item.className = "torrent-item" + (torrent.sent ? " torrent-sent" : "");
    item.dataset.id = torrent.id;

    const info = doc.createElement("div");
    info.className = "torrent-info";

    const nameEl = doc.createElement("div");
    nameEl.className = "torrent-name";
    nameEl.title = torrent.displayName;
    nameEl.textContent = truncate(
      torrent.displayName,
      EXT.MAX_DISPLAY_NAME_LENGTH,
    );
    info.appendChild(nameEl);

    const meta = doc.createElement("div");
    meta.className = "torrent-meta";

    const typeEl = doc.createElement("span");
    typeEl.className = "torrent-type";
    typeEl.textContent = torrent.type === "magnet" ? "Magnet" : "Torrent";
    meta.appendChild(typeEl);

    const infohash = torrent.magnet?.infohash ?? torrent.torrentFile?.url ?? "";
    if (infohash) {
      const hashEl = doc.createElement("span");
      hashEl.className = "torrent-hash";
      hashEl.title = "Infohash";
      hashEl.textContent = infohash.slice(0, SHORT_INFOHASH_LEN);
      meta.appendChild(hashEl);
    }

    if (torrent.sent) {
      const sentEl = doc.createElement("span");
      sentEl.className = "torrent-status";
      sentEl.textContent = "✓ Sent";
      meta.appendChild(sentEl);
    }

    info.appendChild(meta);
    item.appendChild(info);

    const sendBtn = doc.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "btn btn-primary btn-sm btn-send-one";
    sendBtn.textContent = torrent.sent ? "Sent" : "Send";
    sendBtn.disabled = torrent.sent;
    sendBtn.setAttribute(
      "aria-label",
      `Send ${torrent.displayName} to Boba`,
    );
    sendBtn.addEventListener("click", () => {
      void sendTorrents([torrent.id], sendBtn);
    });
    item.appendChild(sendBtn);

    return item;
  }

  /** Render `current` into the list, toggling the empty state. */
  function render(): void {
    listEl.replaceChildren();

    if (current.length === 0) {
      emptyEl.style.display = "block";
      sendAllBtn.disabled = true;
      return;
    }

    emptyEl.style.display = "none";
    for (const torrent of current) listEl.appendChild(makeRow(torrent));

    // Send-All is enabled only when at least one torrent is still unsent.
    sendAllBtn.disabled = current.every((t) => t.sent);
  }

  /** Dispatch a send-torrent message for the given ids. */
  async function sendTorrents(
    ids: string[],
    trigger?: HTMLButtonElement,
  ): Promise<void> {
    if (ids.length === 0) return;
    if (trigger) trigger.disabled = true;
    announce(`Sending ${ids.length} torrent${ids.length > 1 ? "s" : ""}…`);

    try {
      const res = await sendMessage("send-torrent", { tabId: activeTabId, ids });
      // The background reports each send as a flat SendOutcome
      // `{ id, success, displayName, error }` (background/index.ts) — NOT a
      // nested `{ torrent: { id } }`. Reading `r.id` is the contract fix for the
      // false-failure bug the popup↔background integration test discovered.
      const results =
        (res.data?.["results"] as
          | Array<{ success: boolean; id: string }>
          | undefined) ?? [];
      const ok = new Set(
        results.filter((r) => r.success).map((r) => r.id),
      );
      if (ok.size > 0) {
        current = current.map((t) =>
          ok.has(t.id) ? { ...t, sent: true } : t,
        );
        render();
      }
      const failed = ids.length - ok.size;
      announce(
        failed > 0
          ? `${failed} torrent${failed > 1 ? "s" : ""} failed to send`
          : `Sent ${ok.size} torrent${ok.size > 1 ? "s" : ""}`,
      );
    } catch (err) {
      log.error("Send failed", err);
      announce("Send failed");
      if (trigger) trigger.disabled = false;
    }
  }

  /** ID of the active tab (used as the send/get-detected target). */
  let activeTabId: number | null = null;

  /** Query the active tab + background for detected torrents and render them. */
  async function loadTorrents(): Promise<void> {
    try {
      const tabs = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });
      activeTabId = tabs[0]?.id ?? null;

      const res = await sendMessage("get-detected", {
        tabId: activeTabId,
      });
      const result = res.data?.["result"] as
        | { items: DetectedTorrent[] }
        | undefined;
      current = res.success && result ? [...result.items] : [];
      render();
    } catch (err) {
      log.error("Failed to load torrents", err);
      current = [];
      render();
    }
  }

  /** Drive the connection-status indicator from a background health-check. */
  async function checkStatus(): Promise<void> {
    try {
      const res = await sendMessage("health-check");
      const results =
        (res.data?.["results"] as Array<{ status: string }> | undefined) ?? [];

      if (!res.success || results.length === 0) {
        setStatus("warning", "No server");
        if (warningEl) warningEl.style.display = "flex";
        return;
      }
      if (warningEl) warningEl.style.display = "none";

      if (results.some((r) => r.status === "healthy")) {
        setStatus("online", "Connected");
      } else if (results.some((r) => r.status === "degraded")) {
        setStatus("warning", "Degraded");
      } else {
        setStatus("offline", "Disconnected");
      }
    } catch (err) {
      log.error("Health check failed", err);
      setStatus("offline", "Error");
    }
  }

  // Wire static controls.
  sendAllBtn.addEventListener("click", () => {
    const ids = current.filter((t) => !t.sent).map((t) => t.id);
    void sendTorrents(ids, sendAllBtn);
  });
  refreshBtn?.addEventListener("click", () => {
    void loadTorrents();
  });
  for (const id of ["open-options", "open-options-warning"]) {
    doc.getElementById(id)?.addEventListener("click", (e) => {
      e.preventDefault();
      void chrome.runtime.openOptionsPage();
    });
  }

  await Promise.all([loadTorrents(), checkStatus()]);
}

// ─────────────────────────────────────────────────────────────────────────────
// Auto-run entry point (browser only — never during a Vitest import)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * True when running inside a real extension popup document rather than a test
 * harness. Auto-run is gated on a popup-container node + a usable
 * `chrome.runtime.sendMessage`, AND explicitly suppressed under Vitest so
 * importing the module never races the test's own `initPopup` call (tests
 * drive `initPopup` themselves).
 */
function isPopupRuntime(): boolean {
  const underTest =
    typeof process !== "undefined" && Boolean(process.env?.["VITEST"]);
  return (
    !underTest &&
    typeof document !== "undefined" &&
    document.getElementById("torrent-list") !== null &&
    typeof chrome !== "undefined" &&
    typeof chrome.runtime?.sendMessage === "function"
  );
}

if (isPopupRuntime()) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      void initPopup(document);
    });
  } else {
    void initPopup(document);
  }
}
