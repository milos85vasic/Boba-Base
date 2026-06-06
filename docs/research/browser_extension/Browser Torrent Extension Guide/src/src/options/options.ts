/**
 * @fileoverview Options page logic for BobaLink.
 *
 * Full configuration interface for managing servers, authentication,
 * download preferences, and extension settings. Communicates with
 * the background service worker to persist changes.
 *
 * @module options/options
 */

import { createLogger } from "../shared/logger";
import { storageGet, storageSet } from "../shared/storage";
import { STORAGE_KEYS, DEFAULT_CONFIG, DEFAULT_PORTS } from "../shared/constants";
import { generateId, isValidHttpUrl } from "../shared/utils";
import { encrypt } from "../shared/crypto";
import type { ExtensionConfig, ServerConfig, ConnectionTestResult } from "../types/config";

const log = createLogger("Options");

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

/** Current configuration (mutable during editing). */
let config: ExtensionConfig = { ...DEFAULT_CONFIG };

/** Currently editing server ID (null for new). */
let editingServerId: string | null = null;

/** Whether there are unsaved changes. */
let hasChanges = false;

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Initialize the options page.
 */
async function initialize(): Promise<void> {
  log.debug("Options page initializing");

  await loadConfig();
  setupNavigation();
  setupEventListeners();
  setupFormListeners();
  renderServerList();
  populateFormValues();
}

/**
 * Setup sidebar navigation.
 */
function setupNavigation(): void {
  const navItems = document.querySelectorAll(".nav-item");

  for (const item of navItems) {
    item.addEventListener("click", () => {
      const sectionId = item.getAttribute("data-section");
      if (!sectionId) return;

      // Update active nav
      for (const nav of navItems) nav.classList.remove("active");
      item.classList.add("active");

      // Show section
      for (const section of document.querySelectorAll(".section")) {
        section.classList.remove("active");
      }
      document.getElementById(`section-${sectionId}`)?.classList.add("active");
    });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load configuration from storage.
 */
async function loadConfig(): Promise<void> {
  try {
    const data = await storageGet<ExtensionConfig>(STORAGE_KEYS.CONFIG);
    if (data) {
      config = data;
    }
  } catch (err) {
    log.error("Failed to load config", err);
  }
}

/**
 * Save configuration to storage and notify background.
 */
async function saveConfig(): Promise<void> {
  try {
    config = { ...config, lastUpdated: Date.now() };
    await storageSet(STORAGE_KEYS.CONFIG, config);

    // Notify background of config change
    await chrome.runtime.sendMessage({
      type: "set-config",
      payload: { config },
    });

    hasChanges = false;
    showSaveStatus("Settings saved!", "success");
    log.info("Configuration saved");
  } catch (err) {
    log.error("Failed to save config", err);
    showSaveStatus("Failed to save settings", "error");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Server Management
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Render the server list.
 */
function renderServerList(): void {
  const container = document.getElementById("server-list");
  if (!container) return;

  container.innerHTML = "";

  if (config.servers.length === 0) {
    container.innerHTML = `
      <div class="empty-servers">
        <p>No servers configured. Add your first qBitTorrent server.</p>
      </div>
    `;
    return;
  }

  for (const server of config.servers) {
    const card = createServerCard(server);
    container.appendChild(card);
  }
}

/**
 * Create a server card element.
 *
 * @param server - Server config
 * @returns Card element
 */
function createServerCard(server: ServerConfig): HTMLElement {
  const card = document.createElement("div");
  card.className = `server-card ${server.active ? "server-active" : ""}`;
  card.dataset.id = server.id;

  card.innerHTML = `
    <div class="server-header">
      <div class="server-info">
        <h4 class="server-name">${escapeHtml(server.name)}</h4>
        <span class="server-url">${escapeHtml(server.url)}</span>
      </div>
      <div class="server-badges">
        ${server.active ? '<span class="badge badge-active">Active</span>' : ""}
        <span class="badge badge-auth">${escapeHtml(server.authMethod)}</span>
      </div>
    </div>
    <div class="server-actions">
      <button class="btn btn-sm btn-secondary btn-set-active" data-id="${server.id}">
        ${server.active ? "Active" : "Set Active"}
      </button>
      <button class="btn btn-sm btn-secondary btn-edit-server" data-id="${server.id}">Edit</button>
      <button class="btn btn-sm btn-danger btn-delete-server" data-id="${server.id}">Delete</button>
    </div>
  `;

  // Set active
  card.querySelector(".btn-set-active")?.addEventListener("click", () => {
    setActiveServer(server.id);
  });

  // Edit
  card.querySelector(".btn-edit-server")?.addEventListener("click", () => {
    openServerModal(server);
  });

  // Delete
  card.querySelector(".btn-delete-server")?.addEventListener("click", () => {
    deleteServer(server.id);
  });

  return card;
}

/**
 * Set the active server.
 *
 * @param serverId - Server ID to activate
 */
function setActiveServer(serverId: string): void {
  config = {
    ...config,
    servers: config.servers.map((s) => ({
      ...s,
      active: s.id === serverId,
    })),
    activeServerId: serverId,
  };
  hasChanges = true;
  renderServerList();
  updateSaveBar();
}

/**
 * Delete a server.
 *
 * @param serverId - Server ID to delete
 */
function deleteServer(serverId: string): void {
  if (!confirm("Are you sure you want to delete this server?")) return;

  const newServers = config.servers.filter((s) => s.id !== serverId);
  config = {
    ...config,
    servers: newServers,
    activeServerId:
      config.activeServerId === serverId
        ? newServers[0]?.id ?? null
        : config.activeServerId,
  };
  hasChanges = true;
  renderServerList();
  updateSaveBar();
}

// ─────────────────────────────────────────────────────────────────────────────
// Server Modal
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Open the server edit/add modal.
 *
 * @param server - Existing server to edit, or null for new
 */
function openServerModal(server?: ServerConfig): void {
  editingServerId = server?.id ?? null;

  const modal = document.getElementById("server-modal");
  const title = document.getElementById("modal-title");
  if (!modal || !title) return;

  title.textContent = server ? "Edit Server" : "Add Server";

  // Populate form
  (document.getElementById("server-id") as HTMLInputElement).value = server?.id ?? "";
  (document.getElementById("server-name") as HTMLInputElement).value = server?.name ?? "";
  (document.getElementById("server-url") as HTMLInputElement).value = server?.url ?? "";
  (document.getElementById("server-auth") as HTMLSelectElement).value = server?.authMethod ?? "cookie";
  (document.getElementById("server-category") as HTMLInputElement).value = server?.defaultCategory ?? "BobaLink";
  (document.getElementById("server-savepath") as HTMLInputElement).value = server?.defaultSavePath ?? "";

  // Show relevant auth fields
  updateAuthFieldsVisibility();

  // Clear test result
  const testResult = document.getElementById("test-result");
  if (testResult) testResult.innerHTML = "";

  modal.style.display = "flex";
}

/**
 * Close the server modal.
 */
function closeServerModal(): void {
  const modal = document.getElementById("server-modal");
  if (modal) modal.style.display = "none";
  editingServerId = null;

  // Reset form
  (document.getElementById("server-form") as HTMLFormElement)?.reset();
}

/**
 * Update visibility of auth fields based on selected auth method.
 */
function updateAuthFieldsVisibility(): void {
  const method = (document.getElementById("server-auth") as HTMLSelectElement).value;

  for (const el of document.querySelectorAll(".auth-fields")) {
    (el as HTMLElement).style.display = "none";
  }

  const fieldMap: Record<string, string> = {
    cookie: "auth-fields-cookie",
    api_key: "auth-fields-apikey",
    basic: "auth-fields-basic",
  };

  const fieldsId = fieldMap[method];
  if (fieldsId) {
    const fields = document.getElementById(fieldsId);
    if (fields) fields.style.display = "block";
  }
}

/**
 * Save a server from the modal form.
 */
async function saveServerFromForm(): Promise<void> {
  const form = document.getElementById("server-form") as HTMLFormElement;
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }

  const name = (document.getElementById("server-name") as HTMLInputElement).value.trim();
  const url = (document.getElementById("server-url") as HTMLInputElement).value.trim();
  const authMethod = (document.getElementById("server-auth") as HTMLSelectElement).value as ServerConfig["authMethod"];
  const category = (document.getElementById("server-category") as HTMLInputElement).value.trim() || "BobaLink";
  const savePath = (document.getElementById("server-savepath") as HTMLInputElement).value.trim() || null;

  if (!isValidHttpUrl(url)) {
    alert("Please enter a valid HTTP or HTTPS URL");
    return;
  }

  // Encrypt credentials
  const passphrase = "bobalink-extension"; // Fixed passphrase for auto-encryption
  let encryptedPassword: string | null = null;
  let encryptedApiKey: string | null = null;
  let username: string | null = null;

  try {
    if (authMethod === "cookie") {
      const user = (document.getElementById("server-username") as HTMLInputElement).value;
      const pass = (document.getElementById("server-password") as HTMLInputElement).value;
      if (user && pass) {
        username = user;
        const encrypted = await encrypt(pass, passphrase);
        encryptedPassword = JSON.stringify(encrypted);
      }
    } else if (authMethod === "api_key") {
      const key = (document.getElementById("server-apikey") as HTMLInputElement).value;
      if (key) {
        const encrypted = await encrypt(key, passphrase);
        encryptedApiKey = JSON.stringify(encrypted);
      }
    } else if (authMethod === "basic") {
      const user = (document.getElementById("server-basic-username") as HTMLInputElement).value;
      const pass = (document.getElementById("server-basic-password") as HTMLInputElement).value;
      if (user && pass) {
        username = user;
        const encrypted = await encrypt(pass, passphrase);
        encryptedPassword = JSON.stringify(encrypted);
      }
    }
  } catch (err) {
    log.error("Failed to encrypt credentials", err);
    alert("Failed to encrypt credentials. Please try again.");
    return;
  }

  const serverId = editingServerId ?? generateId();
  const isNew = !editingServerId;

  const server: ServerConfig = {
    id: serverId,
    name,
    url,
    authMethod,
    active: isNew ? config.servers.length === 0 : config.servers.find((s) => s.id === serverId)?.active ?? false,
    username,
    encryptedPassword,
    encryptedApiKey,
    requestTimeout: 15000,
    verifySsl: true,
    defaultCategory: category,
    defaultSavePath: savePath,
    startPaused: false,
    skipHashCheck: false,
    contentLayout: "original",
    autoTMM: false,
    uploadLimit: 0,
    downloadLimit: 0,
  };

  if (isNew) {
    config = {
      ...config,
      servers: [...config.servers, server],
      activeServerId: config.activeServerId ?? serverId,
    };
  } else {
    config = {
      ...config,
      servers: config.servers.map((s) => (s.id === serverId ? server : s)),
    };
  }

  hasChanges = true;
  renderServerList();
  closeServerModal();
  updateSaveBar();
}

// ─────────────────────────────────────────────────────────────────────────────
// Auto Discovery
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Run auto-discovery to find servers on common ports.
 */
async function runAutoDiscovery(): Promise<void> {
  const btn = document.getElementById("btn-auto-discover") as HTMLButtonElement;
  const resultsEl = document.getElementById("discovery-results");
  if (!btn || !resultsEl) return;

  btn.disabled = true;
  btn.textContent = "Scanning...";
  resultsEl.innerHTML = "<p>Scanning common ports...</p>";

  try {
    const response = await chrome.runtime.sendMessage({
      type: "auto-discover",
    });

    if (response?.success && response.data?.results) {
      const results = response.data.results as ConnectionTestResult[];
      renderDiscoveryResults(results);
    } else {
      resultsEl.innerHTML = "<p class='error'>Discovery failed</p>";
    }
  } catch (err) {
    resultsEl.innerHTML = `<p class='error'>Error: ${err instanceof Error ? err.message : String(err)}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Discover Servers";
  }
}

/**
 * Render auto-discovery results.
 *
 * @param results - Discovery results
 */
function renderDiscoveryResults(results: ConnectionTestResult[]): void {
  const container = document.getElementById("discovery-results");
  if (!container) return;

  const found = results.filter((r) => r.success);

  if (found.length === 0) {
    container.innerHTML = "<p class='no-results'>No servers found on scanned ports.</p>";
    return;
  }

  let html = `<p class="results-header">Found ${found.length} server(s):</p>`;

  for (const result of found) {
    html += `
      <div class="discovery-item">
        <div class="discovery-info">
          <strong>${escapeHtml(result.url)}</strong>
          <span class="discovery-version">${escapeHtml(result.version ?? "unknown")}</span>
          <span class="discovery-latency">${result.responseTimeMs}ms</span>
        </div>
        <button class="btn btn-sm btn-primary btn-add-discovered" data-url="${escapeHtml(result.url)}">
          Add
        </button>
      </div>
    `;
  }

  container.innerHTML = html;

  // Add click handlers
  for (const btn of container.querySelectorAll(".btn-add-discovered")) {
    btn.addEventListener("click", (e) => {
      const url = (e.currentTarget as HTMLElement).dataset.url;
      if (url) {
        (document.getElementById("server-url") as HTMLInputElement).value = url;
        openServerModal();
      }
    });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Connection Test
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Test connection to a server.
 */
async function testConnection(): Promise<void> {
  const resultEl = document.getElementById("test-result");
  if (!resultEl) return;

  const url = (document.getElementById("server-url") as HTMLInputElement).value;
  if (!url) {
    resultEl.innerHTML = "<p class='error'>Please enter a URL first</p>";
    return;
  }

  resultEl.innerHTML = "<p>Testing connection...</p>";

  try {
    const response = await chrome.runtime.sendMessage({
      type: "test-connection",
      payload: { url },
    });

    if (response?.success && response.data?.result) {
      const result = response.data.result as ConnectionTestResult;
      if (result.success) {
        resultEl.innerHTML = `
          <p class='success'>
            Connected! qBitTorrent v${escapeHtml(result.version ?? "unknown")} 
            (${result.responseTimeMs}ms)
          </p>
        `;
      } else {
        resultEl.innerHTML = `<p class='error'>Failed: ${escapeHtml(result.error ?? "Unknown error")}</p>`;
      }
    } else {
      resultEl.innerHTML = `<p class='error'>Test failed: ${escapeHtml(response?.error ?? "Unknown")}</p>`;
    }
  } catch (err) {
    resultEl.innerHTML = `<p class='error'>Error: ${escapeHtml(err instanceof Error ? err.message : String(err))}</p>`;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Form Handling
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Setup form event listeners.
 */
function setupFormListeners(): void {
  // Auth method change
  document.getElementById("server-auth")?.addEventListener("change", updateAuthFieldsVisibility);
}

/**
 * Populate form values from config.
 */
function populateFormValues(): void {
  // General settings
  const getEl = (id: string) => document.getElementById(id) as HTMLInputElement | null;

  getEl("setting-auto-scan")!.checked = config.autoScan;
  getEl("setting-highlight")!.checked = config.highlightTorrents;
  getEl("setting-highlight-style")!.value = config.highlightStyle;
  getEl("setting-notifications")!.checked = config.showNotifications;
  getEl("setting-auto-send")!.checked = config.autoSend;
  getEl("setting-offline-queue")!.checked = config.offlineQueue;

  // Advanced settings
  getEl("setting-health-interval")!.value = String(config.healthCheckInterval);
  getEl("setting-max-history")!.value = String(config.maxHistoryItems);
  getEl("setting-max-queue")!.value = String(config.maxOfflineQueueSize);
  getEl("setting-request-timeout")!.value = String(Math.round(15000 / 1000));
  getEl("setting-debug")!.checked = config.debugMode;
}

/**
 * Read form values into config.
 */
function readFormValues(): void {
  const getEl = (id: string) => document.getElementById(id) as HTMLInputElement;

  config = {
    ...config,
    autoScan: getEl("setting-auto-scan").checked,
    highlightTorrents: getEl("setting-highlight").checked,
    highlightStyle: getEl("setting-highlight-style").value as "badge" | "border" | "glow",
    showNotifications: getEl("setting-notifications").checked,
    autoSend: getEl("setting-auto-send").checked,
    offlineQueue: getEl("setting-offline-queue").checked,
    healthCheckInterval: parseInt(getEl("setting-health-interval").value, 10),
    maxHistoryItems: parseInt(getEl("setting-max-history").value, 10),
    maxOfflineQueueSize: parseInt(getEl("setting-max-queue").value, 10),
    debugMode: getEl("setting-debug").checked,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Event Listeners
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Setup all event listeners.
 */
function setupEventListeners(): void {
  // Add server button
  document.getElementById("btn-add-server")?.addEventListener("click", () => {
    openServerModal();
  });

  // Modal close
  document.getElementById("modal-close")?.addEventListener("click", closeServerModal);
  document.getElementById("server-modal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeServerModal();
  });

  // Server form submit
  document.getElementById("server-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    saveServerFromForm().catch((err) => log.error("Save server failed", err));
  });

  // Test connection
  document.getElementById("btn-test-connection")?.addEventListener("click", () => {
    testConnection().catch((err) => log.error("Connection test failed", err));
  });

  // Auto discovery
  document.getElementById("btn-auto-discover")?.addEventListener("click", () => {
    runAutoDiscovery().catch((err) => log.error("Auto-discovery failed", err));
  });

  // Save changes
  document.getElementById("btn-save")?.addEventListener("click", () => {
    readFormValues();
    saveConfig().catch((err) => log.error("Save failed", err));
  });

  // Discard changes
  document.getElementById("btn-discard")?.addEventListener("click", () => {
    loadConfig().then(() => {
      renderServerList();
      populateFormValues();
      hasChanges = false;
      updateSaveBar();
    });
  });

  // Reset all
  document.getElementById("btn-reset")?.addEventListener("click", () => {
    if (confirm("This will erase ALL settings and queued items. Are you sure?")) {
      config = { ...DEFAULT_CONFIG };
      saveConfig().catch((err) => log.error("Reset failed", err));
      renderServerList();
      populateFormValues();
    }
  });

  // Track changes on all inputs
  for (const input of document.querySelectorAll("input, select")) {
    input.addEventListener("change", () => {
      hasChanges = true;
      updateSaveBar();
    });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// UI Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Update the save bar visibility.
 */
function updateSaveBar(): void {
  const bar = document.getElementById("save-bar");
  if (bar) {
    bar.style.display = hasChanges ? "flex" : "none";
  }
}

/**
 * Show save status message.
 *
 * @param message - Message to display
 * @param type - Message type
 */
function showSaveStatus(message: string, type: "success" | "error"): void {
  const el = document.getElementById("save-status");
  if (!el) return;

  el.textContent = message;
  el.className = `save-status ${type}`;

  setTimeout(() => {
    el.textContent = "";
    el.className = "save-status";
  }, 3000);
}

/**
 * Escape HTML entities for safe insertion.
 *
 * @param text - Text to escape
 * @returns Escaped text
 */
function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry Point
// ─────────────────────────────────────────────────────────────────────────────

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => initialize());
} else {
  initialize();
}
