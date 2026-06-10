import { defineConfig } from "wxt";

/**
 * WXT configuration for BobaLink (Boba Project browser extension).
 *
 * Generates a Manifest V3 manifest. Permissions follow least-privilege
 * (Plan E §3.1): only storage/alarms/notifications/activeTab/contextMenus.
 * host_permissions are scoped to the Boba merge service on localhost:7187 only
 * (the reference :8080 qBittorrent direct + :7189 Go ports are intentionally
 * dropped for Phase 1; the merge service on 7187 is the single foundation
 * endpoint, see _analysis/04 §8 + Plan E §2 delegation model).
 *
 * NOTE (Boba constitution Hard Stop): no CI/CD, no .github/workflows. This
 * file generates the manifest only — it never wires any pipeline.
 */
export default defineConfig({
  srcDir: "src",
  outDir: ".output",
  manifest: {
    manifest_version: 3,
    name: "__MSG_extName__",
    description: "__MSG_extDescription__",
    version: "1.0.0",
    default_locale: "en",
    minimum_chrome_version: "109",

    // Least-privilege (Plan E §3.1): scripting intentionally NOT requested.
    permissions: [
      "storage",
      "alarms",
      "notifications",
      "activeTab",
      "contextMenus",
      // Phase 5 tab-group batch send: read the clicked tab's group membership and
      // query the group's tabs via chrome.tabs.query({groupId}). `tabGroups` grants
      // NO host/content/URL access. `tabs` is intentionally NOT requested — the
      // batcher reads only tab.id (not url/title/favIconUrl), which per the Chrome
      // docs requires no `tabs` permission (least-privilege, Plan E §3.1).
      "tabGroups",
    ],

    // localhost:7187 (Boba merge service) only — see _analysis/04 §8.
    host_permissions: ["http://localhost:7187/*"],

    action: {
      // `default_popup` is auto-wired by WXT from
      // `src/entrypoints/popup/index.html` (→ popup.html). Action/manifest icons
      // are supplied by @wxt-dev/auto-icons (manifest.icons → icons/<size>.png),
      // rasterized from `src/assets/icon.png` at build time — so no manual
      // default_icon map (which would reference non-existent files).
      default_title: "__MSG_extName__",
    },

    // MV3 CSP object form (Plan E §3.2): script-src 'self' only, no
    // unsafe-inline/unsafe-eval; connect-src scoped to the merge service.
    content_security_policy: {
      extension_pages:
        "default-src 'self'; script-src 'self'; object-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:7187; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'",
    },

    commands: {
      "send-to-boba": {
        suggested_key: {
          default: "Ctrl+Shift+B",
          mac: "Command+Shift+B",
        },
        description: "__MSG_cmdSendToBoba__",
      },
      "scan-page": {
        suggested_key: {
          default: "Ctrl+Shift+S",
          mac: "Command+Shift+S",
        },
        description: "__MSG_cmdScanPage__",
      },
      "open-dashboard": {
        suggested_key: {
          default: "Ctrl+Shift+D",
          mac: "Command+Shift+D",
        },
        description: "__MSG_cmdOpenDashboard__",
      },
    },
  },

  // @wxt-dev/auto-icons rasterizes icon sizes from one SVG at build time.
  modules: ["@wxt-dev/auto-icons"],

  dev: {
    server: {
      port: 3000,
    },
  },

  runner: {
    disabled: true,
  },
});
