# BobaLink Browser Extension — User Guide

**Document Version**: 1.0.0  
**Last Updated**: 2026-06-06  
**Audience**: End Users  
**Companion Documents**: [Installation Guide](installation-guide.md) | [API Reference](api-reference.md)

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Using BobaLink](#2-using-bobalink)
3. [Configuration](#3-configuration)
4. [Troubleshooting](#4-troubleshooting)
5. [Tips and Tricks](#5-tips-and-tricks)
6. [Frequently Asked Questions](#6-frequently-asked-questions)

---

## 1. Getting Started

### 1.1 What is BobaLink?

BobaLink is a browser extension that bridges the gap between finding torrents on the web and downloading them to your private server. It automatically detects magnet links and `.torrent` files on any web page you visit, and with a single click, sends them to your Boba server or directly to qBitTorrent for download.

**Key Features:**

| Feature | Description |
|---|---|
| Automatic Detection | Magnet links and `.torrent` files are detected as you browse — no manual copying required. |
| One-Click Send | Right-click any detected torrent and send it immediately. |
| Tab Group Batching | Send all torrents from an entire tab group at once. |
| Offline Queue | Failed sends are automatically retried when your server comes back online. |
| Real-time Progress | Badge on the toolbar icon shows download status at a glance. |
| Auto-Discovery | BobaLink can find your Boba server automatically on your local network. |
| Cross-Browser | Works on Chrome, Firefox, Opera, and Yandex Browser. |

### 1.2 System Requirements

Before installing BobaLink, ensure you have the following:

| Requirement | Details |
|---|---|
| **Browser** | Chrome 88+, Firefox 109+, Opera 74+, or Yandex Browser 21+ |
| **Boba Server** (recommended) | Docker container running on your local network or server; OR |
| **qBitTorrent** (direct mode) | qBitTorrent 4.4+ with WebUI enabled and accessible via HTTPS |
| **Network** | Your browser must be able to reach the Boba server or qBitTorrent WebUI over HTTPS |
| **Operating System** | Windows 10+, macOS 11+, or any modern Linux distribution |

### 1.3 Installation

BobaLink can be installed from your browser's official extension store or manually. For detailed installation instructions, see the [Installation Guide](installation-guide.md).

**Quick Install:**

| Browser | Store Link | Method |
|---|---|---|
| Chrome | Chrome Web Store | Click "Add to Chrome" |
| Firefox | addons.mozilla.org | Click "Add to Firefox" |
| Opera | Opera Addons | Click "Add to Opera" |
| Yandex | Manual only | See Installation Guide |

After installation, the BobaLink icon (a stylized tea bubble) will appear in your browser's toolbar.

### 1.4 First-Time Setup

Upon first installation, BobaLink will guide you through a quick setup process:

#### Step 1: Choose Connection Mode

BobaLink supports two connection modes:

| Mode | Description | Best For |
|---|---|---|
| **Boba Server** (recommended) | Connects through a Boba orchestration server that proxies requests to qBitTorrent | Users running the Boba project with Docker; users who want search aggregation and SSE progress |
| **qBitTorrent Direct** | Connects directly to qBitTorrent's WebUI API | Users who want a simple, direct connection without the Boba middleware |

#### Step 2: Server Discovery (Boba Mode)

If you selected Boba Server mode, BobaLink will attempt to automatically discover your server:

1. Click **"Discover Servers"** on the welcome page.
2. BobaLink will scan common local addresses (`boba.local:8443`, `boba:8443`).
3. Discovered servers will appear in a list, ranked by response speed.
4. Select your server from the list and click **"Connect"**.

If auto-discovery does not find your server:
1. Click **"Manual Configuration"**.
2. Enter your Boba server URL (e.g., `https://192.168.1.100:8443`).
3. Enter your API key (obtain from your Boba server admin).
4. Click **"Test Connection"** to verify.

#### Step 3: qBitTorrent Direct Setup

If you selected qBitTorrent Direct mode:

1. Enter your qBitTorrent WebUI URL (e.g., `https://192.168.1.100:8080`).
2. Enter your WebUI username and password.
3. Click **"Test Connection"** to verify credentials.
4. Optionally set a default category and download path.

#### Step 4: Finish

Click **"Finish Setup"**. BobaLink is now ready to use. You can always change these settings later via the Options page.

### 1.5 Connecting to Boba

After initial setup, the BobaLink icon in your toolbar indicates the connection status:

| Icon State | Meaning | Action Needed |
|---|---|---|
| Green dot | Connected to server | None |
| Blue spinner | Connecting / sending | Wait |
| Orange dot | Queued items pending | None — will retry automatically |
| Red dot | Connection error | Check server or credentials |
| Gray dot | Not configured | Open Options and configure server |

**To check connection status:**
1. Click the BobaLink icon in the toolbar.
2. The header shows the current connection state.
3. Click the refresh icon to force a health check.

---

## 2. Using BobaLink

### 2.1 Browsing and Detection

BobaLink automatically detects torrents as you browse the web. No manual action is required for detection.

#### What Gets Detected

| Type | Detection Method | Example |
|---|---|---|
| Magnet links | `href="magnet:?xt=..."` | `<a href="magnet:?xt=urn:btih:abc123...">Download</a>` |
| `.torrent` links | URL ends with `.torrent` | `<a href="https://site.com/file.torrent">Torrent</a>` |
| Magnet text | Plain text magnet URIs | Page text containing `magnet:?xt=...` |

#### How Detection Works

When you visit a web page, BobaLink's content script:

1. Scans all `<a>` elements on the page for magnet or `.torrent` links.
2. Watches for dynamically loaded content (single-page apps, infinite scroll).
3. Parses magnet URIs to extract metadata (name, trackers, size).
4. Displays a subtle badge count on the BobaLink toolbar icon showing the number of detected torrents on the current page.

**Privacy Note:** Detection happens entirely within your browser. No data is sent to any server until you explicitly choose to send a torrent.

#### Visual Indicators on Web Pages

BobaLink does not modify web pages by default. If you enable the optional **"Highlight torrents on page"** setting:

- Magnet links get a subtle green underline.
- `.torrent` links get a subtle blue underline.
- Hovering shows a tooltip with the torrent name and size.

To enable: Open Options → Detection → Check "Highlight torrents on page".

### 2.2 Sending Magnet Links

Once BobaLink has detected magnet links on a page, you have several ways to send them:

#### Method 1: Context Menu (Right-Click)

1. Right-click on any magnet link on the page.
2. Select **"Send Magnet to Boba"** from the context menu.
3. The link is immediately sent to your configured server.
4. A brief notification confirms the send (if notifications are enabled).

#### Method 2: Popup Interface

1. Click the BobaLink icon in the toolbar.
2. The popup shows a list of all detected torrents on the current page.
3. Check the box next to the torrent(s) you want to send.
4. Click the **"Send Selected"** button.

#### Method 3: Keyboard Shortcut

1. Press `Ctrl+Shift+B` (Windows/Linux) or `Cmd+Shift+B` (macOS).
2. All detected torrents on the current page are sent automatically.

#### Method 4: Send All on Page

1. Click the BobaLink icon in the toolbar.
2. Click **"Send All"** to send every detected torrent on the page.

**Send Confirmation:**

After sending, you'll see:
- A browser notification (if enabled): "Torrent Sent — {name} added to download queue"
- The badge count updates to reflect sent items
- If the send fails, the item is added to the offline queue for automatic retry

### 2.3 Sending .torrent Files

When BobaLink detects a link to a `.torrent` file (not a magnet link), it can download and send the actual file.

#### Context Menu Method

1. Right-click on a `.torrent` file link.
2. Select **"Download .torrent to Boba"** from the context menu.
3. BobaLink downloads the file (up to 10 MB), parses it, and sends it to your server.

#### Popup Method

1. Click the BobaLink icon.
2. `.torrent` file links appear in the detected list with a file icon.
3. Select and send as with magnet links.

**Note on CORS:** Some websites block direct `.torrent` file downloads. In these cases:
- If using Boba Server mode, the file is proxied through Boba automatically.
- If using qBitTorrent Direct mode, you'll see a "CORS blocked" message. Right-click the link and select "Copy link address," then paste it into qBitTorrent manually.

### 2.4 Using Tab Groups for Batch Downloads

Chrome's Tab Groups feature allows you to organize tabs. BobaLink can send torrents from all tabs in a group simultaneously.

#### Setting Up Tab Groups

1. In Chrome, right-click any tab and select **"Add tab to new group"**.
2. Give the group a name and choose a color.
3. Add multiple torrent pages to the group.

#### Sending a Tab Group

**Method 1 — Popup:**
1. Click the BobaLink icon.
2. Click the **"Tab Groups"** tab in the popup.
3. You'll see all your tab groups listed.
4. Click **"Send"** next to the group you want to process.

**Method 2 — Context Menu:**
1. Right-click on any tab in the group.
2. Select **"Send Tab Group to Boba"**.

**Method 3 — Keyboard Shortcut:**
1. Ensure a tab within the target group is active.
2. Press `Ctrl+Shift+G` (Windows/Linux) or `Cmd+Shift+G` (macOS).

**What Happens:**
1. BobaLink scans every tab in the group.
2. All detected torrents are collected.
3. Duplicates across tabs are automatically removed.
4. The unique torrents are sent as a batch.
5. A summary notification appears: "Batch Complete — 12 torrents sent, 0 failed."

### 2.5 Managing Download Queue

When sends fail (network issues, server offline), torrents are placed in the offline queue for automatic retry.

#### Viewing the Queue

1. Click the BobaLink icon.
2. Click the **"Queue"** tab.
3. You'll see a table of queued items with the following columns:

| Column | Description |
|---|---|
| Name | Torrent display name |
| Status | Pending / Retrying / Failed / Dead Letter |
| Attempts | Number of send attempts |
| Next Retry | Countdown to next automatic retry |
| Actions | Retry now / Remove |

#### Queue Actions

| Action | How To | Result |
|---|---|---|
| Retry now | Click the circular arrow icon | Immediate retry attempt |
| Remove | Click the X icon | Item removed from queue (no recovery) |
| Retry all failed | Click **"Retry All Failed"** | Retries all items with status "Failed" |
| Clear queue | Click **"Clear Queue"** → Confirm | Removes all items (use with caution) |

#### Queue Behavior

- **Automatic retry**: Items are retried with exponential backoff (5s, 10s, 20s, 40s, 80s).
- **Max retries**: Default is 5 attempts. After that, the item moves to "Dead Letter" status.
- **Dead letter items**: These require manual intervention. You can retry them individually or remove them.
- **Queue persistence**: The queue survives browser restarts and computer reboots.

### 2.6 Viewing Download Progress

BobaLink provides real-time download progress information.

#### Toolbar Badge

The BobaLink icon badge shows:
- **Number**: Count of items currently queued or sending.
- **Color**:

| Color | Meaning |
|---|---|
| Green | All clear — connected, no pending items |
| Blue | Currently sending torrent(s) |
| Orange | Items in queue, waiting for retry |
| Red | Connection error or send failures |
| Gray | Extension not configured |

#### Popup Progress View

1. Click the BobaLink icon.
2. Click the **"Downloads"** tab.
3. If connected to Boba Server with SSE enabled, you'll see:

| Column | Description |
|---|---|
| Name | Torrent name |
| Progress | Visual progress bar + percentage |
| Speed | Download speed (e.g., "5.2 MB/s") |
| ETA | Estimated time remaining |
| Status | Downloading / Seeding / Paused / Error |

**Note:** Real-time progress via SSE requires Boba Server mode. qBitTorrent Direct mode does not support live progress in the popup (but you can check progress directly in qBitTorrent's WebUI).

### 2.7 Keyboard Shortcuts Reference

All shortcuts are customizable via your browser's extension shortcuts page.

| Action | Windows/Linux | macOS | Customizable |
|---|---|---|---|
| Send all torrents on current page | `Ctrl+Shift+B` | `Cmd+Shift+B` | Yes |
| Open BobaLink popup | `Ctrl+Shift+L` | `Cmd+Shift+L` | Yes |
| Send current tab's group | `Ctrl+Shift+G` | `Cmd+Shift+G` | Yes |
| Scan page (without sending) | `Ctrl+Shift+S` | `Cmd+Shift+S` | Yes |

**To customize shortcuts:**

| Browser | Path |
|---|---|
| Chrome | `chrome://extensions/shortcuts` |
| Firefox | `about:addons` → Gear icon → Manage Extension Shortcuts |
| Opera | `opera://extensions/shortcuts` |
| Yandex | `browser://extensions/shortcuts` |

---

## 3. Configuration

### 3.1 Options Page Walkthrough

The Options page is the central configuration hub for BobaLink. To open it:

- **Method 1**: Click the BobaLink icon → Click the gear icon.
- **Method 2**: Right-click the BobaLink icon → Select "Options".
- **Method 3**: Navigate to your browser's extensions page and click "Options" under BobaLink.

The Options page is organized into tabs:

#### Server Settings Tab

Configure your connection to Boba or qBitTorrent.

| Setting | Description | Default |
|---|---|---|
| Connection Mode | Boba Server or qBitTorrent Direct | — |
| Server URL | Base URL of your server | — |
| Authentication | API Key, Username/Password, or Custom Header | — |
| Test Connection | Verifies connectivity and shows server version | — |
| Connection Timeout | Seconds to wait for API responses | 30 |
| Health Check Interval | Seconds between automatic health checks | 30 |

#### Download Preferences Tab

Configure default behavior when sending torrents.

| Setting | Description | Default |
|---|---|---|
| Default Category | qBitTorrent category for new torrents | — |
| Default Tags | Comma-separated tags (e.g., `browser,auto`) | — |
| Default Save Path | Override download directory | — |
| Pause After Add | Add torrents in paused state | Off |
| Skip Hash Check | Skip initial hash verification | Off |
| Sequential Download | Download pieces in order | Off |
| First/Last Piece Priority | Prioritize first and last pieces | Off |

#### Queue Settings Tab

Configure offline queue behavior.

| Setting | Description | Default |
|---|---|---|
| Max Queue Size | Maximum items to retain | 1,000 |
| Max Retries | Attempts before dead-letter | 5 |
| Base Retry Delay | Initial retry wait time (seconds) | 5 |
| Max Retry Delay | Longest retry wait time (seconds) | 300 |

#### Notification Settings Tab

Configure when BobaLink shows browser notifications.

| Event | Default | Description |
|---|---|---|
| Send Success | Enabled | Toast when torrent is successfully sent |
| Send Failed | Enabled | Toast when send fails (immediately, not on retry) |
| Batch Complete | Enabled | Summary after tab group batch send |
| Queue Retry | Disabled | Toast on each retry attempt |

#### Detection Settings Tab

Configure torrent detection behavior.

| Setting | Description | Default |
|---|---|---|
| Dynamic Scanning | Watch for newly added content on SPA pages | On |
| Highlight on Page | Visually mark torrent links on web pages | Off |
| Max File Size | Maximum `.torrent` file size to download (MB) | 10 |
| Tab Group Scanning | Enable tab group batch features | On |

#### UI Settings Tab

Configure the user interface.

| Setting | Options | Default |
|---|---|---|
| Theme | System / Light / Dark | System |
| Show Badge | Show numeric badge on toolbar icon | On |
| Badge Color | Custom colors for each state | Default |

#### Security Settings Tab

Configure security preferences.

| Setting | Description | Default |
|---|---|---|
| Require Password | Ask for password on browser startup | Off |
| Auto-Lock | Lock credentials after minutes of inactivity | 30 |
| HTTPS Only | Refuse non-HTTPS server URLs | On |
| Certificate Pinning | Pin expected server certificate | Off |

### 3.2 Server Settings in Detail

#### Switching Between Boba and qBitTorrent Direct

1. Open Options → Server Settings.
2. Change the **Connection Mode** dropdown.
3. Enter the appropriate URL and credentials.
4. Click **"Test Connection"**.
5. Click **"Save"**.

#### Changing Server URL

1. Open Options → Server Settings.
2. Update the **Server URL** field.
3. Click **"Test Connection"** to verify.
4. Click **"Save"**.

Your queue and history are preserved when changing servers.

### 3.3 Download Preferences

#### Categories

Categories help organize torrents in qBitTorrent. To set up:

1. Open Options → Download Preferences.
2. Enter a default category name (e.g., `movies`, `tv-shows`).
3. The category must already exist in qBitTorrent, or qBitTorrent will create it automatically (depending on version).

To manage categories in qBitTorrent:
1. Open qBitTorrent WebUI.
2. Go to **View → Categories**.
3. Add or edit categories with optional default save paths.

#### Tags

Tags provide additional metadata. Multiple tags are comma-separated:

```
browser,auto,hd
```

These appear in qBitTorrent's Tags column and can be used for filtering and automation rules.

#### Download Path Override

To save torrents to a specific directory (overriding qBitTorrent's default):

1. Open Options → Download Preferences.
2. Enter an absolute path in **Default Save Path**.
3. Example: `/downloads/movies` (Linux) or `C:\Downloads\Movies` (Windows).

### 3.4 Notification Settings

Browser notifications appear as operating system-level toasts. To enable or disable:

1. Open Options → Notification Settings.
2. Toggle individual notification types.
3. Your browser may also ask for permission the first time a notification is shown.

**Granting Notification Permission:**

| Browser | Steps |
|---|---|
| Chrome | Click the lock icon in the address bar → Site settings → Notifications → Allow |
| Firefox | Click the permissions icon in the address bar → Allow notifications |
| Opera | Settings → Privacy & Security → Site settings → Notifications |

### 3.5 Security Settings

#### Password Protection

For shared computers, enable password protection:

1. Open Options → Security Settings.
2. Enable **"Require Password on Startup"**.
3. Enter and confirm a password.
4. Click **"Save"**.

On the next browser startup, BobaLink will prompt for the password before decrypting stored credentials. The password is never stored — only used to derive the encryption key.

**Forgot Password?** There is no recovery. You must reset the extension (which clears all stored credentials) and reconfigure.

---

## 4. Troubleshooting

### 4.1 "Cannot Connect to Boba"

| Symptom | The BobaLink icon shows a red dot, and the popup says "Disconnected" or "Connection Error." |
|---|---|

**Step-by-step diagnosis:**

1. **Check the server URL**
   - Open Options → Server Settings.
   - Verify the URL is correct (e.g., `https://192.168.1.100:8443`).
   - Common mistake: Using `http://` instead of `https://`.
   - Common mistake: Wrong port number.

2. **Test from the browser directly**
   - Open a new tab and navigate to `{your-server-url}/api/v1/health`.
   - You should see a JSON response with version information.
   - If you get a certificate error, your browser may not trust the server's certificate.

3. **Check credentials**
   - Open Options → Server Settings.
   - Click **"Test Connection"**.
   - If it returns "Authentication failed," verify your API key or username/password.
   - For qBitTorrent Direct, ensure the WebUI is enabled in qBitTorrent settings.

4. **Check network connectivity**
   - Ensure your computer can reach the server:
     ```bash
     ping 192.168.1.100
     curl -k https://192.168.1.100:8443/api/v1/health
     ```

5. **Check firewall rules**
   - Ensure port 8443 (Boba) or 8080 (qBitTorrent) is open.
   - If using Docker, ensure the container port is mapped:
     ```bash
     docker ps
     # Look for 0.0.0.0:8443->8443/tcp
     ```

6. **Check certificate validity**
   - Self-signed certificates may be rejected.
   - In Options → Security, you may need to disable "HTTPS Only" temporarily for testing (not recommended for production).

### 4.2 "Torrent Not Detected"

| Symptom | You see a magnet link on the page, but BobaLink shows "0 torrents detected." |
|---|---|

**Possible causes and solutions:**

1. **The link was loaded dynamically**
   - Some sites load content via JavaScript after the initial page load.
   - Wait a few seconds and check the BobaLink popup again.
   - Enable **"Dynamic Scanning"** in Options → Detection (it's on by default).

2. **The link is in an iframe**
   - Content inside iframes may not be accessible.
   - Open the iframe content directly in a new tab if possible.

3. **The link is not a standard `<a>` tag**
   - Some sites use JavaScript click handlers instead of actual links.
   - Try right-clicking and selecting "Copy link address," then check if it's a valid magnet URI.

4. **The page uses a non-standard magnet format**
   - Some sites abbreviate or encode magnet links differently.
   - Manually copy the link and paste it into qBitTorrent.

5. **Extension permissions**
   - Ensure BobaLink has permission to access the site:
     - Click the lock icon in the address bar.
     - Check if extensions are allowed.
     - Try clicking the BobaLink icon and granting permission when prompted.

### 4.3 "Send Failed" Errors

| Symptom | You click "Send" but get a "Send Failed" notification or the item appears in the queue. |
|---|---|

**Common causes:**

1. **Server is temporarily unreachable**
   - Check if your Boba/qBitTorrent server is running.
   - The item will be queued and retried automatically.

2. **Authentication expired**
   - For qBitTorrent Direct, the session cookie may have expired.
   - Open Options → Server Settings → Test Connection.
   - If it fails, re-enter credentials.

3. **Torrent already exists**
   - qBitTorrent rejects duplicate torrents.
   - Check qBitTorrent — the torrent may already be downloading or completed.

4. **Invalid torrent data**
   - The magnet link may be malformed.
   - The `.torrent` file may be corrupted or not a valid torrent.

5. **Rate limiting**
   - If sending many torrents rapidly, you may hit rate limits.
   - Wait a moment and retry.

### 4.4 "Extension Not Working on Site X"

| Symptom | BobaLink doesn't detect anything on a specific website. |
|---|---|

**Troubleshooting steps:**

1. **Check if the site requires login**
   - Some torrent sites only show links to logged-in users.
   - Ensure you're logged in and the links are visible.

2. **JavaScript-rendered content**
   - Some sites render all content via JavaScript.
   - Try waiting a few seconds after the page appears "loaded."
   - Scroll down to trigger lazy loading.

3. **Content Security Policy (CSP) restrictions**
   - Some sites have strict CSP headers that limit extension functionality.
   - BobaLink respects these restrictions and will not inject scripts on such pages.

4. **Extension conflict**
   - Other extensions may interfere.
   - Try disabling other extensions temporarily.

5. **Report the site**
   - If a popular torrent site consistently fails, please report it:
     - Click BobaLink icon → **"Report Issue"**.
     - Include the site URL and a description of what you expected vs. what happened.

### 4.5 Badge Shows Error

| Badge Color | Meaning | Solution |
|---|---|---|
| Red | Connection error | Check server status and credentials |
| Red with "E" | Extension error | Check the popup for details; try reloading the extension |
| Orange | Queue has retrying items | Normal — wait for automatic retry |
| Gray | Not configured | Open Options and set up your server |
| No badge | No torrents on current page | Normal — browse to a page with torrent links |

**To reload the extension:**

| Browser | Steps |
|---|---|
| Chrome | `chrome://extensions` → Toggle BobaLink off and on |
| Firefox | `about:addons` → BobaLink → Toggle off and on |
| Opera | `opera://extensions` → Toggle BobaLink off and on |

---

## 5. Tips and Tricks

### 5.1 Organizing Torrents in Tab Groups

Efficient batch downloading with tab groups:

1. **Create themed groups**: Organize tabs by category before sending.
   - "Movies — 2026 Releases" (group color: red)
   - "TV Shows — Season Finales" (group color: blue)
   - "Software — Linux Distros" (group color: green)

2. **Use group colors as visual cues**: BobaLink shows the group color in the popup, making it easy to identify.

3. **Name groups descriptively**: The group name appears in batch send notifications.

4. **Pre-set categories**: Before sending a group, configure the default category in Options. All torrents from the group will use that category.

### 5.2 Keyboard Shortcut Cheat Sheet

**Print this section for quick reference:**

```
┌─────────────────────────────────────┬────────────────────┐
│ Action                              │ Shortcut           │
├─────────────────────────────────────┼────────────────────┤
│ Send all torrents on current page   │ Ctrl+Shift+B       │
│                                     │ (Cmd+Shift+B Mac)  │
├─────────────────────────────────────┼────────────────────┤
│ Open BobaLink popup                 │ Ctrl+Shift+L       │
│                                     │ (Cmd+Shift+L Mac)  │
├─────────────────────────────────────┼────────────────────┤
│ Send current tab's group            │ Ctrl+Shift+G       │
│                                     │ (Cmd+Shift+G Mac)  │
├─────────────────────────────────────┼────────────────────┤
│ Scan page (no send)                 │ Ctrl+Shift+S       │
│                                     │ (Cmd+Shift+S Mac)  │
└─────────────────────────────────────┴────────────────────┘
```

### 5.3 Privacy Best Practices

1. **Use HTTPS only**: Always connect to your server over HTTPS. BobaLink enforces this by default.

2. **Enable password protection**: On shared computers, enable **"Require Password on Startup"** in Security Settings.

3. **Review permissions**: BobaLink uses the `activeTab` permission, which means it only accesses the page you're currently viewing. It does not read browsing history or all tabs.

4. **No data collection**: BobaLink does not send any data to third parties. All communication is between your browser and your server.

5. **Credential storage**: Credentials are encrypted using AES-256-GCM. The encryption key is stored only in browser memory and cleared on restart (unless password protection is disabled).

6. **Clear data on uninstall**: When you remove BobaLink, all stored data (including encrypted credentials and queue) is automatically deleted.

### 5.4 Power User Workflows

**Workflow: Nightly Batch Download**
1. Throughout the day, add torrent pages to a Chrome tab group named "To Download."
2. Before bed, press `Ctrl+Shift+G` to send the entire group.
3. Check qBitTorrent in the morning — all downloads are ready.

**Workflow: Category-Based Organization**
1. In Options → Download Preferences, set categories for different content types.
2. Use qBitTorrent's "Automatic Torrent Management" to auto-move completed downloads based on category.
3. Your downloads are automatically organized into folders.

**Workflow: Monitoring Large Batches**
1. Enable all notifications in Options → Notification Settings.
2. Send a large tab group batch.
3. Watch browser notifications for real-time status of each torrent.
4. Check the Queue tab for any failures.

---

## 6. Frequently Asked Questions

### General Questions

**Q1: What is BobaLink?**
> BobaLink is a browser extension that automatically detects magnet links and `.torrent` files on web pages and sends them to your Boba server or qBitTorrent client with a single click. It eliminates the need to manually copy and paste magnet links.

**Q2: Is BobaLink free?**
> Yes, BobaLink is free and open-source software. You can use it, modify it, and distribute it under its license terms.

**Q3: What browsers are supported?**
> Chrome 88+, Firefox 109+, Opera 74+, and Yandex Browser 21+. Edge is also compatible as it's Chromium-based.

**Q4: Does BobaLink work on mobile browsers?**
> No. Mobile browsers (Chrome for Android, Safari for iOS) do not support the full WebExtensions API that BobaLink requires, particularly the background service worker and tab group APIs.

### Setup and Configuration

**Q5: Do I need the Boba server, or can I use qBitTorrent directly?**
> You can use either. Boba Server provides additional features like search aggregation, SSE progress streaming, and auto-discovery. qBitTorrent Direct is simpler and doesn't require the Boba middleware.

**Q6: How do I find my Boba server URL?**
> If Boba is running on your local network, try clicking "Discover Servers" in the setup wizard. If that doesn't work, check your Docker configuration or ask your server administrator for the IP address and port.

**Q7: Where do I get an API key?**
> API keys are generated by your Boba server administrator. Check the Boba server dashboard or configuration files.

**Q8: What is the qBitTorrent WebUI, and how do I enable it?**
> The WebUI is qBitTorrent's built-in web interface for remote control. To enable it:
> 1. Open qBitTorrent → **Tools → Options**.
> 2. Select **Web UI** from the left sidebar.
> 3. Check **"Web User Interface (Remote control)"**.
> 4. Set a port (default 8080) and authentication.
> 5. Click **Apply**.

**Q9: Can I use BobaLink with multiple servers?**
> Not simultaneously. BobaLink supports one active server configuration at a time. You can switch between servers in Options → Server Settings, but only one is active.

**Q10: How do I change the toolbar icon position?**
> Click and drag the icon to reposition it in the browser toolbar. On some browsers, you may need to click the extensions icon (puzzle piece) and use the pin option.

### Usage Questions

**Q11: Does BobaLink automatically download torrents without my permission?**
> No. BobaLink only detects torrents on the page. Nothing is sent to your server until you explicitly click "Send" or use a keyboard shortcut.

**Q12: Can I select which torrents to send?**
> Yes. Open the BobaLink popup to see all detected torrents. Check or uncheck individual items before clicking "Send Selected."

**Q13: What happens if my server is offline when I send a torrent?**
> The torrent is added to the offline queue. BobaLink will automatically retry sending it when the server comes back online, using exponential backoff.

**Q14: How long does the queue retain failed items?**
> By default, up to 30 days or until 1,000 items accumulate. These limits are configurable in Options → Queue Settings.

**Q15: Can I send torrents from private trackers?**
> Yes, as long as the magnet link or `.torrent` file is accessible. BobaLink works with any torrent source. Note that private tracker torrents may require specific passkeys in the tracker URL.

**Q16: Does BobaLink work with magnet links that don't have a display name?**
> Yes. If the `dn` (display name) parameter is missing, BobaLink will show "Unknown Torrent" in the interface. The actual torrent name will be resolved by qBitTorrent from the metadata.

**Q17: Can I send the same torrent twice?**
> BobaLink deduplicates by infohash. If you try to send a torrent that's already in your queue or downloading, it will be skipped with a "duplicate" status.

**Q18: What file types can BobaLink detect?**
> BobaLink detects:
> - Magnet URI links (`magnet:?xt=...`)
> - `.torrent` file links
> - Plain text magnet URIs on the page

### Privacy and Security

**Q19: Does BobaLink collect my browsing data?**
> No. BobaLink operates entirely locally. It does not send browsing history, page URLs, or detected torrents to any third party. All communication is directly between your browser and your configured server.

**Q20: How are my credentials stored?**
> Credentials are encrypted using AES-256-GCM (a military-grade encryption standard) via the Web Crypto API. The encryption key is stored only in browser memory and is never persisted to disk.

**Q21: What permissions does BobaLink need?**
> BobaLink uses the `activeTab` permission, which means it only accesses the web page you are currently viewing and only when you interact with the extension. It does not read your browsing history, bookmarks, or other tabs.

**Q22: Can someone steal my credentials if they access my computer?**
> If you enabled password protection, credentials cannot be decrypted without the password. If password protection is disabled, anyone with physical access to your unlocked computer could potentially access the extension's in-memory key. Always lock your computer when unattended.

### Troubleshooting

**Q23: Why does the badge show a red dot?**
> A red dot indicates a connection error. Check that your server is running, the URL is correct, and your credentials are valid. Open the popup for more details.

**Q24: Why are some torrents not detected?**
> See the ["Torrent Not Detected"](#42-torrent-not-detected) troubleshooting section. Common causes include dynamic content loading, iframe isolation, and non-standard link formats.

**Q25: How do I clear the queue?**
> Open the BobaLink popup → Queue tab → Click "Clear Queue" → Confirm. This removes all queued items permanently.

**Q26: How do I reset BobaLink to defaults?**
> Open Options → scroll to the bottom → Click "Reset to Defaults" → Confirm. This clears all settings, credentials, and queue data.

**Q27: BobaLink slows down my browser. What can I do?**
> BobaLink is designed for minimal performance impact. If you experience slowness:
> 1. Disable "Highlight torrents on page" in Options → Detection.
> 2. Reduce the number of open tabs with detected torrents.
> 3. Ensure you're using the latest version of BobaLink.

**Q28: How do I report a bug?**
> Click the BobaLink icon → "Report Issue" or visit the GitHub Issues page. Include:
> - Your browser and version
> - BobaLink version
> - Steps to reproduce
> - Expected vs. actual behavior
> - Screenshots if applicable

**Q29: How do I update BobaLink?**
> If installed from a store (Chrome Web Store, AMO), updates are automatic. For manual installs, download the latest release ZIP and reload the extension.

**Q30: Where can I get help?**
> - Read this user guide thoroughly.
> - Check the [Troubleshooting](#4-troubleshooting) section.
> - Visit the GitHub Discussions page.
> - Join the community Discord/forum (links on the project website).

---

*End of User Guide*
