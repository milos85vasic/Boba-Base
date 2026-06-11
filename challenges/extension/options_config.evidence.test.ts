/**
 * @fileoverview Challenge-scoped evidence harness for the BobaLink OPTIONS
 * config save/load round-trip (Phase 8 — Challenges / §11.4.83).
 *
 * This is NOT a normal unit/integration spec — it is the Node harness invoked by
 * `challenges/extension/options_config_challenge.sh`. It drives the REAL, shipped
 * extension modules end-to-end (no re-implementation) and PERSISTS the captured
 * runtime evidence to `challenges/extension/.evidence/options_config.json`. The
 * bash challenge then re-reads that evidence file and asserts on it, so the PASS
 * verdict is backed by an auditable artefact per §11.4.83 / §11.4.69 (feature
 * class: `storage_write` — the options page persisting the user's config).
 *
 * The options round-trip exercised (identical wiring to the user's real path —
 * the SAME real sendMessage→onMessage bridge the production
 * `tests/integration/popup-background.test.ts` uses, reused verbatim here):
 *
 *   1. LOAD — the REAL {@link initOptions} runs against the REAL options
 *      index.html DOM with an EMPTY store; it populates the Server tab with the
 *      built-in default server URL. We capture the rendered default field value.
 *
 *   2. EDIT + SAVE — the user types a NEW server URL (and name + a numeric
 *      field) into the real form controls; clicking the real Save button (or
 *      calling the REAL {@link saveOptions}) writes the merged config back to the
 *      REAL chrome.storage.local via the committed storage layer.
 *
 *   3. ROUND-TRIP READ-BACK — the REAL background `get-config` message handler
 *      (driven THROUGH the real router over the bridge) reads the SAME persisted
 *      config out of the SAME backing store. We capture the config the background
 *      independently returns.
 *
 *   4. FIELD-FOR-FIELD IDENTITY — we assert the background-returned config's
 *      server url/name + the edited extension-level numeric field exactly equal
 *      what the options page saved (a genuine persist→read-back identity, not the
 *      same in-memory object).
 *
 * The ONLY substituted boundary is `chrome.*` (the in-memory storage/runtime
 * bridge — the SAME fake the production storage suite uses). Both `saveOptions`
 * (writer) and the background `get-config` (reader) hit the SAME chrome.storage
 * fake, so the round-trip is genuine persistence, not a shared object. The spec
 * FAILS (and writes no `pass:true` evidence) if the default is not loaded, the
 * save does not persist, or the read-back diverges from what was saved — so a
 * no-op stub of either initOptions/saveOptions or get-config cannot produce a
 * green run. NO real token, NO credentials (§11.4.10).
 *
 * @module challenges/extension/options_config.evidence
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { createChromeStorageFake } from "../../extension/tests/unit/chrome-fake";
import { STORAGE_KEYS } from "../../extension/src/shared/constants";
import type { ExtensionConfig } from "../../extension/src/types/config";

// ─────────────────────────────────────────────────────────────────────────────
// Known inputs (synthetic, no credentials — §11.4.10). The DEFAULT server URL the
// Server tab renders for an empty store is the :7187 merge service (DEFAULT_URLS
// .FAST_API), per options.ts:DEFAULT_SERVER_URL.
// ─────────────────────────────────────────────────────────────────────────────
const EXPECTED_DEFAULT_URL = "http://localhost:7187";
const NEW_SERVER_URL = "http://192.168.1.50:7187";
const NEW_SERVER_NAME = "Home Boba";
const NEW_HEALTH_INTERVAL = 9; // edited extension-level numeric field

const OPTIONS_HTML_PATH = resolve(
  process.cwd(),
  "src/entrypoints/options/index.html",
);

const EVIDENCE_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  ".evidence",
  "options_config.json",
);

function mustExist<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`expected ${what} to exist`);
  }
  return value;
}

// ─────────────────────────────────────────────────────────────────────────────
// The chrome bridge — runtime.sendMessage REALLY routes into the background's
// registered onMessage listener (so get-config genuinely runs); storage is the
// committed in-memory chrome.storage fake (so saveOptions REALLY persists and the
// background REALLY reads the persisted bytes back).
// ─────────────────────────────────────────────────────────────────────────────

interface ExtMessage {
  type: string;
  payload?: Record<string, unknown>;
}
interface ExtResponse {
  success: boolean;
  data?: Record<string, unknown>;
  error?: string;
}
type MessageHandler = (
  message: ExtMessage,
  sender: { tab?: { id?: number } },
  sendResponse: (response: ExtResponse) => void,
) => boolean | undefined;

function listenerHub<F>() {
  const handlers: F[] = [];
  return {
    addListener: vi.fn((h: F) => {
      handlers.push(h);
    }),
    handlers,
  };
}

function sessionStorageFake() {
  const store = new Map<string, unknown>();
  return {
    api: {
      get(keys?: string | string[] | null): Promise<Record<string, unknown>> {
        const out: Record<string, unknown> = {};
        if (keys === null || keys === undefined) {
          for (const [k, v] of store) out[k] = v;
          return Promise.resolve(out);
        }
        const list = Array.isArray(keys) ? keys : [keys];
        for (const k of list) if (store.has(k)) out[k] = store.get(k);
        return Promise.resolve(out);
      },
      set(items: Record<string, unknown>): Promise<void> {
        for (const [k, v] of Object.entries(items)) store.set(k, v);
        return Promise.resolve();
      },
      remove(keys: string | string[]): Promise<void> {
        const list = Array.isArray(keys) ? keys : [keys];
        for (const k of list) store.delete(k);
        return Promise.resolve();
      },
    },
  };
}

function buildBridgeChrome() {
  const storageFake = createChromeStorageFake();
  const session = sessionStorageFake();
  const onMessage = listenerHub<MessageHandler>();

  function sendMessage(message: ExtMessage): Promise<ExtResponse> {
    const handler = onMessage.handlers[0];
    if (!handler) return Promise.resolve({ success: false });
    return new Promise<ExtResponse>((resolveReply) => {
      handler(message, {}, resolveReply);
    });
  }

  const chrome = {
    storage: { ...storageFake.chrome.storage, session: session.api },
    runtime: {
      sendMessage,
      onMessage,
      onInstalled: listenerHub<(d: { reason: string }) => void>(),
      onStartup: listenerHub<() => void>(),
      openOptionsPage: vi.fn(() => Promise.resolve()),
    },
    contextMenus: {
      create: vi.fn(),
      onClicked: listenerHub<(info: unknown, tab: unknown) => void>(),
    },
    commands: { onCommand: listenerHub<() => void>() },
    alarms: {
      create: vi.fn(),
      onAlarm: listenerHub<(alarm: { name: string }) => void>(),
    },
    action: {
      setBadgeText: vi.fn(() => Promise.resolve()),
      setBadgeBackgroundColor: vi.fn(() => Promise.resolve()),
    },
    notifications: { create: vi.fn() },
    tabs: {
      query: vi.fn(() => Promise.resolve([{ id: 1 }])),
      sendMessage: vi.fn(() => Promise.resolve(null)),
      create: vi.fn(() => Promise.resolve({ id: 99 })),
    },
  };

  return {
    chrome,
    store: storageFake.store,
    /** Drive get-config THROUGH the real background router over the bridge. */
    getConfigViaBackground(): Promise<ExtResponse> {
      return sendMessage({ type: "get-config" });
    },
  };
}

type Bridge = ReturnType<typeof buildBridgeChrome>;

/** Load the real options index.html body into the jsdom document. */
function loadOptionsDom(): void {
  const html = readFileSync(OPTIONS_HTML_PATH, "utf8");
  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  document.body.innerHTML = bodyMatch ? (bodyMatch[1] ?? "") : html;
  for (const s of Array.from(document.querySelectorAll("script"))) s.remove();
}

function setFieldValue(id: string, value: string): void {
  const el = document.getElementById(id) as
    | HTMLInputElement
    | HTMLSelectElement
    | null;
  mustExist(el, `#${id}`).value = value;
}

/** Import the REAL background + options modules fresh and register the router. */
async function loadModules() {
  vi.resetModules();
  const bg = await import("../../extension/src/background/index");
  const options = await import("../../extension/src/options/options");
  bg.initBackground();
  return {
    initOptions: options.initOptions,
    saveOptions: options.saveOptions,
  };
}

let bridge: Bridge;

beforeEach(() => {
  bridge = buildBridgeChrome();
  (globalThis as unknown as { chrome: unknown }).chrome = bridge.chrome;
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
  delete (globalThis as unknown as { chrome?: unknown }).chrome;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("CHALLENGE: BobaLink options config save/load round-trip (real modules)", () => {
  it("loads defaults, saves an edited config, and the background reads back the SAME config", async () => {
    loadOptionsDom();
    const { initOptions, saveOptions } = await loadModules();

    // ── STAGE 1: LOAD — real initOptions populates the Server tab default ──────
    expect(bridge.store.has(STORAGE_KEYS.CONFIG)).toBe(false); // empty store
    await initOptions(document);
    const urlField = mustExist(
      document.getElementById("opt-server-url") as HTMLInputElement | null,
      "#opt-server-url",
    );
    const loadedDefaultUrl = urlField.value;
    expect(loadedDefaultUrl).toBe(EXPECTED_DEFAULT_URL);

    // ── STAGE 2: EDIT + SAVE — type a new URL/name/interval, then real save ────
    setFieldValue("opt-server-url", NEW_SERVER_URL);
    setFieldValue("opt-server-name", NEW_SERVER_NAME);
    setFieldValue("opt-health-interval", String(NEW_HEALTH_INTERVAL));
    const saved = await saveOptions(document);

    // It really persisted (the same key the background reads).
    expect(bridge.store.has(STORAGE_KEYS.CONFIG)).toBe(true);
    expect(saved.servers[0]?.url).toBe(NEW_SERVER_URL);

    // ── STAGE 3: ROUND-TRIP — background get-config reads the SAME persisted set
    const reply = await bridge.getConfigViaBackground();
    expect(reply.success).toBe(true);
    const readBack = mustExist(
      reply.data?.["config"] as ExtensionConfig | undefined,
      "background-returned config",
    );

    // ── STAGE 4: FIELD-FOR-FIELD IDENTITY ─────────────────────────────────────
    const savedServer = mustExist(saved.servers[0], "saved server");
    const readServer = mustExist(readBack.servers[0], "read-back server");
    expect(readServer.url).toBe(NEW_SERVER_URL);
    expect(readServer.url).toBe(savedServer.url);
    expect(readServer.name).toBe(NEW_SERVER_NAME);
    expect(readServer.name).toBe(savedServer.name);
    expect(readServer.id).toBe(savedServer.id);
    expect(readBack.healthCheckInterval).toBe(NEW_HEALTH_INTERVAL);
    expect(readBack.healthCheckInterval).toBe(saved.healthCheckInterval);
    expect(readBack.activeServerId).toBe(saved.activeServerId);
    expect(readBack.activeServerId).toBe(savedServer.id);

    // ── EVIDENCE: persist the captured runtime data for the bash challenge ─────
    const evidence = {
      pass: true,
      capturedAt: new Date().toISOString(),
      feature: "storage_write", // §11.4.69 taxonomy class
      load: {
        storeEmptyBeforeLoad: true,
        loadedDefaultUrl,
      },
      save: {
        persisted: bridge.store.has(STORAGE_KEYS.CONFIG),
        savedServerUrl: savedServer.url,
        savedServerName: savedServer.name,
        savedServerId: savedServer.id,
        savedHealthInterval: saved.healthCheckInterval,
        savedActiveServerId: saved.activeServerId,
      },
      roundTrip: {
        backgroundSuccess: reply.success,
        readServerUrl: readServer.url,
        readServerName: readServer.name,
        readServerId: readServer.id,
        readHealthInterval: readBack.healthCheckInterval,
        readActiveServerId: readBack.activeServerId,
        urlMatches: readServer.url === savedServer.url,
        nameMatches: readServer.name === savedServer.name,
        idMatches: readServer.id === savedServer.id,
        healthIntervalMatches:
          readBack.healthCheckInterval === saved.healthCheckInterval,
        activeServerMatches: readBack.activeServerId === saved.activeServerId,
      },
      expected: {
        defaultUrl: EXPECTED_DEFAULT_URL,
        newUrl: NEW_SERVER_URL,
        newName: NEW_SERVER_NAME,
        newHealthInterval: NEW_HEALTH_INTERVAL,
      },
    };
    mkdirSync(dirname(EVIDENCE_PATH), { recursive: true });
    writeFileSync(EVIDENCE_PATH, JSON.stringify(evidence, null, 2) + "\n", "utf8");
  });
});
