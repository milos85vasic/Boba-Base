/**
 * @fileoverview Popup UI logic for BobaLink.
 *
 * Displays detected torrents from the active tab with checkboxes for selection,
 * send functionality, and connection status. Communicates with the background
 * service worker via chrome.runtime.sendMessage.
 *
 * @module popup/popup
 */

import { createLogger } from "../shared/logger";
import { truncate, escapeHtml } from "../shared/utils";
import type { DetectedTorrent } from "../types/torrent";

const log = createLogger("Popup");

// ─────────────────────────────────────────────────────────────────────────────
// UI References
// ─────────────────────────────────────────────────────────────────────────────

/** Container for the torrent list. */
const torrentListEl = document.getElementById("torrent-list") as HTMLDivElement;

/** Empty state displayed when no torrents found. */
const emptyStateEl = document.getElementById("empty-state") as HTMLDivElement;

/** Footer with send button. */
const footerEl = document.getElementById("popup-footer") as HTMLElement;

/** Selection info text. */
const selectionInfoEl = document.getElementById("selection-info") as HTMLDivElement;

/** Send button. */
const sendBtn = document.getElementById("btn-send") as HTMLButtonElement;

/** Connection status dot. */
const statusDotEl = document.getElementById("status-dot") as HTMLSpanElement;

/** Connection status text. */
const statusTextEl = document.getElementById("status-text") as HTMLSpanElement;

/** Connection warning banner. */
const connectionWarningEl = document.getElementById("connection-warning") as HTMLDivElement;

/** Progress overlay. */
const progressOverlayEl = document.getElementById("progress-overlay") as HTMLDivElement;

/** Progress text. */
const progressTextEl = document.getElementById("progress-text") as HTMLDivElement;

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

/** Currently displayed torrents. */
let currentTorrents: DetectedTorrent[] = [];

/** Currently selected torrent IDs. */
const selectedIds = new Set<string>();

/** ID of the active tab. */
let activeTabId: number | null = null;

// ─────────────────────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Initialize the popup when DOM is ready.
 */
function initialize(): void {
  log.debug("Popup initializing");

  setupEventListeners();
  loadTorrents();
  checkConnectionStatus();
}

/**
 * Setup all event listeners for popup UI elements.
 */
function setupEventListeners(): void {
  // Select all
  document.getElementById("btn-select-all")?.addEventListener("click", () => {
    for (const torrent of currentTorrents) {
      if (!torrent.sent) {
        selectedIds.add(torrent.id);
      }
    }
    updateCheckboxes();
    updateSelectionInfo();
  });

  // Deselect all
  document.getElementById("btn-deselect-all")?.addEventListener("click", () => {
    selectedIds.clear();
    updateCheckboxes();
    updateSelectionInfo();
  });

  // Refresh
  document.getElementById("btn-refresh")?.addEventListener("click", () => {
    loadTorrents();
  });

  // Scan page
  document.getElementById("btn-scan-page")?.addEventListener("click", async () => {
    if (activeTabId) {
      try {
        await chrome.tabs.sendMessage(activeTabId, { type: "scan-now" });
        showProgress("Scanning page...");
        // Wait a bit then reload
        setTimeout(() => {
          loadTorrents();
          hideProgress();
        }, 2000);
      } catch (err) {
        log.error("Scan failed", err);
        showError("Cannot scan this page");
      }
    }
  });

  // Send selected
  sendBtn.addEventListener("click", sendSelectedTorrents);

  // Open options
  document.getElementById("open-options")?.addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Data Loading
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load detected torrents from the active tab via background script.
 */
async function loadTorrents(): Promise<void> {
  try {
    // Get the active tab
    const tabs = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    const tab = tabs[0];
    activeTabId = tab?.id ?? null;

    if (!tab?.id) {
      showEmptyState("No active tab");
      return;
    }

    // Request detected torrents from background
    const response = await chrome.runtime.sendMessage({
      type: "get-detected",
      payload: { tabId: tab.id },
    });

    if (response?.success && response.data?.result) {
      const result = response.data.result as {
        items: DetectedTorrent[];
        magnetCount: number;
        torrentFileCount: number;
      };
      currentTorrents = result.items;
      renderTorrentList();
    } else {
      // Try direct content script query
      try {
        const contentResponse = await chrome.tabs.sendMessage(tab.id, {
          type: "get-detected",
        });
        if (contentResponse?.torrents) {
          // Convert simplified format back to DetectedTorrent
          currentTorrents = contentResponse.torrents as DetectedTorrent[];
          renderTorrentList();
        } else {
          showEmptyState();
        }
      } catch {
        showEmptyState();
      }
    }
  } catch (err) {
    log.error("Failed to load torrents", err);
    showEmptyState("Cannot access page");
  }
}

/**
 * Check the connection status to the configured server.
 */
async function checkConnectionStatus(): Promise<void> {
  try {
    const response = await chrome.runtime.sendMessage({
      type: "health-check",
    });

    if (response?.success && response.data?.results) {
      const results = response.data.results as Array<{
        status: string;
        url: string;
      }>;

      if (results.length === 0) {
        setStatus("warning", "No server");
        connectionWarningEl.style.display = "flex";
        return;
      }

      const healthy = results.some((r) => r.status === "healthy");
      const degraded = results.some((r) => r.status === "degraded");

      if (healthy) {
        setStatus("online", "Connected");
      } else if (degraded) {
        setStatus("warning", "Degraded");
      } else {
        setStatus("offline", "Disconnected");
      }

      connectionWarningEl.style.display = "none";
    } else {
      setStatus("warning", "No server");
      connectionWarningEl.style.display = "flex";
    }
  } catch (err) {
    log.error("Health check failed", err);
    setStatus("offline", "Error");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Rendering
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Render the list of detected torrents.
 */
function renderTorrentList(): void {
  if (currentTorrents.length === 0) {
    showEmptyState();
    return;
  }

  // Hide empty state, show list
  emptyStateEl.style.display = "none";
  footerEl.style.display = "flex";

  // Clear existing items (except empty state)
  const existingItems = torrentListEl.querySelectorAll(".torrent-item");
  for (const el of existingItems) {
    el.remove();
  }

  // Render each torrent
  for (const torrent of currentTorrents) {
    const el = createTorrentElement(torrent);
    torrentListEl.appendChild(el);
  }

  updateSelectionInfo();
}

/**
 * Create a DOM element for a single torrent item.
 *
 * @param torrent - The torrent to display
 * @returns List item element
 */
function createTorrentElement(torrent: DetectedTorrent): HTMLElement {
  const item = document.createElement("div");
  item.className = `torrent-item ${torrent.sent ? "torrent-sent" : ""}`;
  item.dataset.id = torrent.id;

  const typeIcon = torrent.type === "magnet" ? "&#127759;" : "&#128190;";
  const typeLabel = torrent.type === "magnet" ? "Magnet" : "Torrent";
  const displayName = escapeHtml(truncate(torrent.displayName, 60));

  const isSelected = selectedIds.has(torrent.id);
  const checkboxState = torrent.sent ? "checked disabled" : isSelected ? "checked" : "";

  item.innerHTML = `
    <label class="torrent-checkbox-label">
      <input type="checkbox" class="torrent-checkbox" 
        ${torrent.sent ? "checked disabled" : isSelected ? "checked" : ""}
        ${torrent.sent ? "disabled" : ""}
        data-id="${torrent.id}">
    </label>
    <div class="torrent-info">
      <div class="torrent-name" title="${escapeHtml(torrent.displayName)}">${displayName}</div>
      <div class="torrent-meta">
        <span class="torrent-type">${typeIcon} ${typeLabel}</span>
        ${torrent.magnet ? `<span class="torrent-hash" title="Infohash">${escapeHtml(torrent.magnet.infohash.slice(0, 16))}...</span>` : ""}
        ${torrent.sent ? '<span class="torrent-status">&#10003; Sent</span>' : ""}
      </div>
    </div>
  `;

  // Handle checkbox changes
  const checkbox = item.querySelector(".torrent-checkbox") as HTMLInputElement;
  if (!torrent.sent) {
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedIds.add(torrent.id);
      } else {
        selectedIds.delete(torrent.id);
      }
      updateSelectionInfo();
    });
  }

  return item;
}

/**
 * Show the empty state message.
 *
 * @param message - Optional custom message
 */
function showEmptyState(message?: string): void {
  emptyStateEl.style.display = "block";
  footerEl.style.display = "none";

  // Remove all torrent items
  const items = torrentListEl.querySelectorAll(".torrent-item");
  for (const el of items) {
    el.remove();
  }

  if (message) {
    const titleEl = emptyStateEl.querySelector(".empty-title");
    if (titleEl) titleEl.textContent = message;
  }
}

/**
 * Update checkbox states to match selectedIds.
 */
function updateCheckboxes(): void {
  const checkboxes = torrentListEl.querySelectorAll(
    ".torrent-checkbox:not([disabled])",
  ) as NodeListOf<HTMLInputElement>;

  for (const cb of checkboxes) {
    const id = cb.dataset.id;
    if (id) {
      cb.checked = selectedIds.has(id);
    }
  }
}

/**
 * Update the selection info text and send button state.
 */
function updateSelectionInfo(): void {
  const count = selectedIds.size;
  selectionInfoEl.textContent = `${count} selected`;
  sendBtn.disabled = count === 0;
}

// ─────────────────────────────────────────────────────────────────────────────
// Actions
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Send selected torrents to qBitTorrent via background script.
 */
async function sendSelectedTorrents(): Promise<void> {
  if (selectedIds.size === 0 || !activeTabId) return;

  showProgress(`Sending ${selectedIds.size} torrent...${selectedIds.size > 1 ? "s" : ""}`);

  try {
    const response = await chrome.runtime.sendMessage({
      type: "send-torrent",
      payload: {
        tabId: activeTabId,
        ids: Array.from(selectedIds),
      },
    });

    hideProgress();

    if (response?.success && response.data?.results) {
      const results = response.data.results as Array<{
        success: boolean;
        torrent: { id: string; displayName: string };
        error: string | null;
      }>;

      const succeeded = results.filter((r) => r.success).length;
      const failed = results.length - succeeded;

      if (succeeded > 0) {
        // Mark as sent
        for (const r of results) {
          if (r.success) {
            const torrent = currentTorrents.find((t) => t.id === r.torrent.id);
            if (torrent) {
              (torrent as DetectedTorrent).sent = true;
            }
          }
        }
        selectedIds.clear();
        renderTorrentList();
      }

      if (failed > 0) {
        showError(`${failed} torrent${failed > 1 ? "s" : ""} failed to send`);
      }
    } else {
      showError(response?.error || "Send failed");
    }
  } catch (err) {
    hideProgress();
    log.error("Send failed", err);
    showError(err instanceof Error ? err.message : "Send failed");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// UI Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Set the connection status indicator.
 *
 * @param state - Connection state
 * @param text - Status text
 */
function setStatus(
  state: "online" | "offline" | "warning",
  text: string,
): void {
  statusTextEl.textContent = text;
  statusDotEl.className = "status-dot";

  switch (state) {
    case "online":
      statusDotEl.classList.add("status-online");
      break;
    case "offline":
      statusDotEl.classList.add("status-offline");
      break;
    case "warning":
      statusDotEl.classList.add("status-warning");
      break;
  }
}

/**
 * Show the progress overlay.
 *
 * @param text - Progress text
 */
function showProgress(text: string): void {
  progressTextEl.textContent = text;
  progressOverlayEl.style.display = "flex";
}

/**
 * Hide the progress overlay.
 */
function hideProgress(): void {
  progressOverlayEl.style.display = "none";
}

/**
 * Show a temporary error message.
 *
 * @param message - Error message
 */
function showError(message: string): void {
  const errorEl = document.createElement("div");
  errorEl.className = "error-toast";
  errorEl.textContent = message;
  document.querySelector(".popup-container")?.appendChild(errorEl);

  setTimeout(() => {
    errorEl.remove();
  }, 3000);
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry Point
// ─────────────────────────────────────────────────────────────────────────────

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initialize);
} else {
  initialize();
}
