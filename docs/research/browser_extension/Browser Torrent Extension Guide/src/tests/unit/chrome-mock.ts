/**
 * Chrome API mock for unit testing.
 *
 * Provides a complete mock of the chrome.* APIs used by BobaLink,
 * including storage, runtime messaging, tabs, alarms, notifications,
 * context menus, and action APIs.
 */

/** Storage area mock implementation. */
class MockStorageArea implements chrome.storage.StorageArea {
  private data = new Map<string, unknown>();

  get(
    keys: string | string[] | Record<string, unknown> | null,
  ): Promise<Record<string, unknown>> {
    return new Promise((resolve) => {
      const result: Record<string, unknown> = {};

      if (keys === null) {
        for (const [key, value] of this.data) {
          result[key] = value;
        }
      } else if (typeof keys === "string") {
        if (this.data.has(keys)) {
          result[keys] = this.data.get(keys);
        }
      } else if (Array.isArray(keys)) {
        for (const key of keys) {
          if (this.data.has(key)) {
            result[key] = this.data.get(key);
          }
        }
      } else {
        for (const key of Object.keys(keys)) {
          if (this.data.has(key)) {
            result[key] = this.data.get(key);
          }
        }
      }

      resolve(result);
    });
  }

  set(items: Record<string, unknown>): Promise<void> {
    return new Promise((resolve) => {
      for (const [key, value] of Object.entries(items)) {
        this.data.set(key, value);
      }
      resolve();
    });
  }

  remove(keys: string | string[]): Promise<void> {
    return new Promise((resolve) => {
      const toRemove = Array.isArray(keys) ? keys : [keys];
      for (const key of toRemove) {
        this.data.delete(key);
      }
      resolve();
    });
  }

  clear(): Promise<void> {
    return new Promise((resolve) => {
      this.data.clear();
      resolve();
    });
  }

  getBytesInUse = (): Promise<number> => Promise.resolve(0);

  onChanged = {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  };
}

/** Mock chrome runtime. */
const mockRuntime: typeof chrome.runtime = {
  id: "test-extension-id",
  onInstalled: {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  },
  onStartup: {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  },
  onMessage: {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  },
  sendMessage: (): Promise<unknown> => Promise.resolve({ success: true }),
  openOptionsPage: (): void => {},
  getManifest: (): chrome.runtime.Manifest => ({
    manifest_version: 3,
    name: "BobaLink",
    version: "1.0.0",
  } as chrome.runtime.Manifest),
  getURL: (path: string): string => `chrome-extension://test-id/${path}`,
} as unknown as typeof chrome.runtime;

/** Mock chrome tabs. */
const mockTabs: typeof chrome.tabs = {
  query: (): Promise<chrome.tabs.Tab[]> =>
    Promise.resolve([
      {
        id: 1,
        url: "https://example.com",
        title: "Example",
        active: true,
        windowId: 1,
      } as chrome.tabs.Tab,
    ]),
  sendMessage: (): Promise<unknown> => Promise.resolve({ success: true }),
  create: (): Promise<chrome.tabs.Tab> =>
    Promise.resolve({ id: 2 } as chrome.tabs.Tab),
} as unknown as typeof chrome.tabs;

/** Mock chrome alarms. */
const mockAlarms: typeof chrome.alarms = {
  create: (): void => {},
  onAlarm: {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  },
} as unknown as typeof chrome.alarms;

/** Mock chrome notifications. */
const mockNotifications: typeof chrome.notifications = {
  create: (): void => {},
} as unknown as typeof chrome.notifications;

/** Mock chrome context menus. */
const mockContextMenus: typeof chrome.contextMenus = {
  create: (): void => {},
  onClicked: {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  },
} as unknown as typeof chrome.contextMenus;

/** Mock chrome action. */
const mockAction: typeof chrome.action = {
  setBadgeText: (): void => {},
  setBadgeBackgroundColor: (): void => {},
} as unknown as typeof chrome.action;

/** Mock chrome storage. */
const mockStorage: typeof chrome.storage = {
  local: new MockStorageArea(),
  onChanged: {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  },
} as unknown as typeof chrome.storage;

/** Mock chrome.commands. */
const mockCommands: typeof chrome.commands = {
  onCommand: {
    addListener: (): void => {},
    removeListener: (): void => {},
    hasListener: (): boolean => false,
    hasListeners: (): boolean => false,
  },
} as unknown as typeof chrome.commands;

/** Complete chrome mock object. */
export const chromeMock: typeof chrome = {
  runtime: mockRuntime,
  storage: mockStorage,
  tabs: mockTabs,
  alarms: mockAlarms,
  notifications: mockNotifications,
  contextMenus: mockContextMenus,
  action: mockAction,
  commands: mockCommands,
} as unknown as typeof chrome;

// Assign to global
(globalThis as unknown as Record<string, unknown>).chrome = chromeMock;
