import { defineConfig } from "wxt";

/**
 * WXT build configuration for BobaLink browser extension.
 * WXT is a build tool for web extensions that handles Manifest V3 generation,
 * development server, and production builds.
 *
 * @see https://wxt.dev
 */
export default defineConfig({
  /**
   * Extension metadata used in manifest.json generation.
   */
  manifest: {
    name: "__MSG_extName__",
    description: "__MSG_extDescription__",
    version: "1.0.0",
    manifest_version: 3,
    default_locale: "en",

    /**
     * Minimum Chrome version for MV3 features.
     */
    minimum_chrome_version: "109",

    /**
     * Permissions required for core functionality.
     * - storage: Persist extension settings and encrypted credentials
     * - alarms: Keep service worker alive, periodic health checks
     * - notifications: User notifications for torrent status
     * - activeTab: Privacy-first page interaction (only when user engages)
     * - scripting: Content script injection for scanning
     * - contextMenus: Right-click menu actions
     */
    permissions: [
      "storage",
      "alarms",
      "notifications",
      "activeTab",
      "scripting",
      "contextMenus",
    ],

    /**
     * Host permissions for qBitTorrent API access.
     * CORS bypass is achieved via service worker fetch with host_permissions.
     * http://localhost:7187 - Boba FastAPI server
     * http://localhost:7189 - Boba Go server
     * http://localhost:8080 - qBitTorrent WebUI
     */
    host_permissions: [
      "http://localhost:7187/*",
      "http://localhost:7189/*",
      "http://localhost:8080/*",
    ],

    /**
     * Action configuration for toolbar popup.
     */
    action: {
      default_popup: "popup/index.html",
      default_icon: {
        "16": "icon-16.png",
        "32": "icon-32.png",
      },
      default_title: "__MSG_extName__",
    },

    /**
     * Background service worker configuration.
     */
    background: {
      service_worker: "background.js",
      type: "module",
    },

    /**
     * Content script configuration.
     */
    content_scripts: [
      {
        matches: ["<all_urls>"],
        js: ["content-scripts/content.js"],
        css: ["content-scripts/content.css"],
        run_at: "document_idle",
      },
    ],

    /**
     * Options page for extension settings.
     */
    options_page: "options/index.html",

    /**
     * Web accessible resources for content script assets.
     */
    web_accessible_resources: [
      {
        resources: ["assets/*"],
        matches: ["<all_urls>"],
      },
    ],

    /**
     * Content Security Policy for secure execution.
     * Strict policy with no inline scripts.
     */
    content_security_policy: {
      extension_pages:
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:7187 http://localhost:7189 http://localhost:8080; img-src 'self' data:;",
    },

    /**
     * Keyboard shortcuts for quick actions.
     * - Ctrl+Shift+B: Send current page torrents to Boba
     * - Ctrl+Shift+S: Scan current page
     * - Ctrl+Shift+D: Open Boba Dashboard
     */
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

  /**
   * Build output configuration.
   */
  outDir: "dist",

  /**
   * Enable auto-icons generation from a single SVG source.
   */
  autoIcons: {
    baseIconPath: "src/assets/icon.svg",
  },

  /**
   * Development server configuration.
   */
  dev: {
    port: 3000,
  },

  /**
   * Runner configuration for launching browsers during development.
   */
  runner: {
    disabled: true,
  },
});
