# BobaLink Browser Extension — Installation Guide

**Document Version**: 1.0.0  
**Last Updated**: 2026-06-06  
**Audience**: System Administrators, End Users  
**Companion Documents**: [User Guide](user-guide.md) | [Technical Specification](technical-specification.md) | [Developer Guide](developer-guide.md)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Browser-Specific Installation](#2-browser-specific-installation)
3. [Manual Installation](#3-manual-installation)
4. [Post-Installation Setup](#4-post-installation-setup)
5. [Configuration Guide](#5-configuration-guide)
6. [Verification](#6-verification)
7. [Updating](#7-updating)
8. [Uninstallation](#8-uninstallation)
9. [Troubleshooting Installation Issues](#9-troubleshooting-installation-issues)

---

## 1. Prerequisites

### 1.1 Infrastructure Requirements

Before installing BobaLink, ensure the following backend infrastructure is in place:

#### Option A: Boba Project (Recommended)

The Boba orchestration server provides the full feature set including search aggregation, SSE progress streaming, and auto-discovery.

| Component | Requirement | Verification Command |
|---|---|---|
| Docker Engine | 24.0+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| Available ports | 8443 (Boba HTTPS) | `netstat -tlnp \| grep 8443` |
| SSL certificate | Valid or self-signed | `curl -k https://localhost:8443/health` |

**Quick verification that Boba is running:**

```bash
# Using curl (replace with your Boba server IP)
curl -k https://192.168.1.100:8443/api/v1/health

# Expected response:
# {"status":"healthy","version":"1.4.2",...}
```

If Boba is not yet installed, refer to the Boba Project documentation for Docker Compose setup before proceeding.

#### Option B: qBitTorrent WebUI (Direct Mode)

For direct connection without the Boba middleware:

| Component | Requirement | Verification |
|---|---|---|
| qBitTorrent | 4.4.0 or later | Check in qBitTorrent → Help → About |
| WebUI enabled | Configured and running | Access `https://your-qbt:8080` |
| HTTPS access | TLS certificate (self-signed OK) | Browser can reach the URL |
| Authentication | Username/password configured | Login page accessible |

**Enabling qBitTorrent WebUI:**

1. Open qBitTorrent on your server.
2. Navigate to **Tools → Options** (or **Edit → Preferences** on Linux).
3. Select **Web UI** from the left sidebar.
4. Check **"Web User Interface (Remote control)"**.
5. Configure the following:

| Setting | Recommended Value | Description |
|---|---|---|
| IP Address | `*` (all interfaces) or specific IP | Which network interface to bind |
| Port | `8080` | WebUI port (change if needed) |
| Use HTTPS | Enabled | Required for secure communication |
| Username | `admin` (change this) | WebUI login username |
| Password | Strong unique password | WebUI login password |
| Bypass authentication for localhost | Disabled | Enforce auth on all connections |

6. If using HTTPS (recommended), configure the certificate:
   - **Option 1**: Use qBitTorrent's built-in self-signed certificate.
   - **Option 2**: Provide your own certificate and private key files.
7. Click **Apply** or **Save**.
8. Restart qBitTorrent to apply changes.

**Verify WebUI accessibility:**

```bash
# Test from the same machine
curl -k -X POST "https://localhost:8080/api/v2/auth/login" \
  -H "Referer: https://localhost:8080" \
  -d "username=admin" \
  -d "password=yourpassword"

# Expected: "Ok.SID" response with Set-Cookie header
```

### 1.2 Browser Requirements

| Browser | Minimum Version | Download URL |
|---|---|---|
| Google Chrome | 88 | https://www.google.com/chrome/ |
| Mozilla Firefox | 109 | https://www.mozilla.org/firefox/ |
| Opera | 74 | https://www.opera.com/download |
| Yandex Browser | 21 | https://browser.yandex.com/ |
| Microsoft Edge | 88 | https://www.microsoft.com/edge |

**Check your browser version:**

| Browser | Method |
|---|---|
| Chrome | Menu (⋮) → Help → About Google Chrome |
| Firefox | Menu (≡) → Help → About Firefox |
| Opera | Menu → Help → About Opera |
| Yandex | Menu → Advanced → About Yandex Browser |
| Edge | Menu (⋯) → Help and feedback → About Microsoft Edge |

### 1.3 Network Requirements

| Requirement | Description |
|---|---|
| Same network (recommended) | Browser and server on the same LAN for lowest latency |
| HTTPS accessibility | Browser must be able to reach the server over HTTPS |
| Certificate trust | Self-signed certificates may require browser exceptions |
| Firewall rules | Ports 8443 (Boba) and/or 8080 (qBitTorrent) must be open |
| No proxy interference | Corporate proxies may need exceptions for local addresses |

**Testing network connectivity:**

```bash
# Replace with your server IP
SERVER_IP="192.168.1.100"

# Test basic connectivity
ping -c 3 $SERVER_IP

# Test port reachability (Boba)
nc -zv $SERVER_IP 8443

# Test port reachability (qBitTorrent)
nc -zv $SERVER_IP 8080

# Test HTTPS endpoint (accepts self-signed certs)
curl -k -I https://$SERVER_IP:8443/api/v1/health

# Test from the browser's context
# Open DevTools Console (F12) and run:
# fetch('https://192.168.1.100:8443/api/v1/health', {mode: 'no-cors'})
#   .then(r => console.log('Reachable'))
#   .catch(e => console.error('Not reachable:', e));
```

---

## 2. Browser-Specific Installation

### 2.1 Chrome (Chrome Web Store)

The recommended installation method for Chrome users.

**Step-by-step:**

1. Open Google Chrome.
2. Navigate to the Chrome Web Store page for BobaLink:
   - Search "BobaLink" in the Chrome Web Store, OR
   - Direct link: `https://chrome.google.com/webstore/detail/bobalink/{extension-id}`
3. Click the **"Add to Chrome"** button.
4. Review the permission request:

| Permission | Why It's Needed |
|---|---|
| Read and change data on websites | Detect magnet links on web pages |
| Storage | Save configuration and queue locally |
| Context menus | Add "Send to Boba" right-click options |
| Notifications | Show download status toasts |

5. Click **"Add extension"** to confirm.
6. The BobaLink icon (tea bubble) appears in the toolbar.

**If the icon is hidden:**
1. Click the extensions icon (puzzle piece) in the Chrome toolbar.
2. Find BobaLink in the list.
3. Click the pin icon to keep it visible in the toolbar.

### 2.2 Chrome (Manual Installation)

For environments where the Chrome Web Store is unavailable (enterprise, air-gapped networks).

**Prerequisites:**
- BobaLink release ZIP file (`bobalink-chrome-v1.0.0.zip`)
- Chrome Developer Mode enabled

**Step-by-step:**

1. Download the release ZIP from GitHub Releases:
   ```bash
   wget https://github.com/bobaproject/bobalink/releases/download/v1.0.0/bobalink-chrome-v1.0.0.zip
   ```

2. Extract the ZIP to a permanent location:
   ```bash
   unzip bobalink-chrome-v1.0.0.zip -d /opt/bobalink/chrome
   ```
   > **Important**: Do not delete this folder while the extension is installed. Chrome reads from this directory.

3. Open Chrome and navigate to `chrome://extensions`.

4. Enable **"Developer mode"** using the toggle in the top-right corner.

5. Click **"Load unpacked"**.

6. Select the extracted folder (`/opt/bobalink/chrome`).

7. BobaLink appears in the extensions list with its extension ID.

8. (Optional) Note the extension ID for debugging:
   ```
   Extension ID: abcdefghijklmnopqrstuvwxyzabcdef (example)
   ```

### 2.3 Firefox (Add-ons Mozilla.org — AMO)

**Step-by-step:**

1. Open Mozilla Firefox.
2. Navigate to `https://addons.mozilla.org/en-US/firefox/addon/bobalink/`.
3. Click **"Add to Firefox"**.
4. Review the permission dialog:

| Permission | Why It's Needed |
|---|---|
| Access browser tabs | Enumerate tab groups for batch sending |
| Access browser storage | Save settings and queue |
| Access your data for all websites | Detect magnet links |
| Display notifications | Show send status |

5. Click **"Add"** to confirm.
6. BobaLink is installed and the icon appears in the toolbar.

### 2.4 Firefox (Manual Installation)

For environments without AMO access.

**Step-by-step:**

1. Download the Firefox XPI or ZIP from GitHub Releases:
   ```bash
   wget https://github.com/bobaproject/bobalink/releases/download/v1.0.0/bobalink-firefox-v1.0.0.zip
   ```

2. Extract to a permanent location:
   ```bash
   unzip bobalink-firefox-v1.0.0.zip -d /opt/bobalink/firefox
   ```

3. Open Firefox and navigate to `about:debugging`.

4. Click **"This Firefox"** on the left sidebar.

5. Click **"Load Temporary Add-on..."**.

6. Navigate to the extracted folder and select `manifest.json`.

7. BobaLink loads as a temporary extension.

> **Note**: Temporary extensions are removed when Firefox closes. For permanent manual installation on Firefox, the extension must be signed by Mozilla or installed via enterprise policies.

**Firefox Enterprise Policy Installation (for managed environments):**

Create or edit the policies file:

```json
// Linux: /etc/firefox/policies/policies.json
// Windows: C:\Program Files\Mozilla Firefox\distribution\policies.json
// macOS: /Applications/Firefox.app/Contents/Resources/distribution/policies.json

{
  "policies": {
    "Extensions": {
      "Install": [
        "https://your-server/bobalink-firefox-v1.0.0-signed.xpi"
      ],
      "Locked": false
    }
  }
}
```

### 2.5 Opera (Opera Addons)

1. Open Opera Browser.
2. Navigate to `https://addons.opera.com/en/extensions/details/bobalink/`.
3. Click **"Add to Opera"**.
4. Confirm the installation when prompted.
5. The icon appears in the Opera toolbar.

### 2.6 Opera (Manual Installation)

Opera is Chromium-based and can install Chrome extensions.

1. Enable the "Install Chrome Extensions" feature:
   - Go to `opera://extensions`.
   - Enable **"Developer mode"**.

2. Download the Chrome release ZIP (same as Chrome manual installation).

3. Extract and load unpacked as described in the Chrome manual section.

4. Alternatively, install the Chrome Web Store version:
   - Install the "Install Chrome Extensions" addon from Opera Addons.
   - Visit the BobaLink Chrome Web Store page.
   - Click **"Add to Opera"**.

### 2.7 Yandex Browser (Manual Installation)

Yandex Browser does not have a dedicated extension store for BobaLink. Use manual installation.

**Step-by-step:**

1. Download the Chrome release ZIP from GitHub.
2. Extract to a permanent location.
3. Open Yandex Browser and navigate to `browser://extensions`.
4. Enable **"Developer mode"**.
5. Click **"Load unpacked"**.
6. Select the extracted Chrome build folder.
7. BobaLink installs and the icon appears in the toolbar.

### 2.8 Chromium (Developer Mode)

For ungoogled-chromium and other Chromium derivatives:

1. Download the Chrome release ZIP.
2. Extract to a permanent location.
3. Navigate to `chrome://extensions`.
4. Enable **"Developer mode"**.
5. Click **"Load unpacked"** and select the extracted folder.

**Command-line installation (advanced):**

```bash
# Launch Chromium with the extension pre-loaded
chromium --load-extension=/opt/bobalink/chrome \
         --enable-logging=stderr \
         --v=1
```

---

## 3. Manual Installation (All Browsers)

This section provides a unified manual installation procedure that works across all supported browsers.

### 3.1 Download Release Package

1. Visit the GitHub Releases page:
   `https://github.com/bobaproject/bobalink/releases`

2. Download the appropriate ZIP for your browser:

| Browser | File |
|---|---|
| Chrome / Opera / Yandex / Edge | `bobalink-chrome-v{version}.zip` |
| Firefox | `bobalink-firefox-v{version}.zip` |

3. Verify the download (optional but recommended):
   ```bash
   # Download the checksum file
   wget https://github.com/bobaproject/bobalink/releases/download/v1.0.0/SHA256SUMS

   # Verify
   sha256sum -c SHA256SUMS
   # Expected: bobalink-chrome-v1.0.0.zip: OK
   ```

### 3.2 Extract Archive

```bash
# Create installation directory
sudo mkdir -p /opt/bobalink

# Extract Chrome build
sudo unzip bobalink-chrome-v1.0.0.zip -d /opt/bobalink/chrome

# Or extract Firefox build
sudo unzip bobalink-firefox-v1.0.0.zip -d /opt/bobalink/firefox

# Set appropriate permissions
sudo chown -R $USER:$USER /opt/bobalink
sudo chmod -R 755 /opt/bobalink
```

> **Windows users**: Use PowerShell `Expand-Archive` or 7-Zip to extract.

### 3.3 Load in Browser

| Browser | Navigation | Action |
|---|---|---|
| Chrome | `chrome://extensions` | Enable Developer mode → Load unpacked |
| Firefox | `about:debugging` → This Firefox | Load Temporary Add-on → Select manifest.json |
| Opera | `opera://extensions` | Enable Developer mode → Load unpacked |
| Yandex | `browser://extensions` | Enable Developer mode → Load unpacked |
| Edge | `edge://extensions` | Enable Developer mode → Load unpacked |

### 3.4 Post-Load Verification

After loading:
1. The extension should appear in the extensions list with version 1.0.0.
2. No error messages should appear.
3. The BobaLink icon should be visible in the browser toolbar.

---

## 4. Post-Installation Setup

### 4.1 Open Options Page

Immediately after installation, configure BobaLink:

1. Click the BobaLink icon in the toolbar.
2. Click the **gear icon** (⚙️) in the popup.
3. The Options page opens in a new tab.

Alternatively:
- Right-click the BobaLink icon → **"Options"**.
- Or navigate to your browser's extensions page and click **"Options"** under BobaLink.

### 4.2 Configure Boba Server URL

**For Boba Server mode:**

1. In Options → Server Settings, ensure **"Boba Server"** is selected as the connection mode.
2. Enter your Boba server URL:
   - Docker on same machine: `https://localhost:8443`
   - Docker on LAN server: `https://192.168.1.100:8443`
   - With custom port: `https://your-server:9000`
3. Select **"API Key"** as the authentication method.
4. Enter your API key.
5. Click **"Test Connection"**.
6. Wait for the green "Connected" indicator.

**For qBitTorrent Direct mode:**

1. In Options → Server Settings, select **"qBitTorrent Direct"**.
2. Enter your qBitTorrent WebUI URL:
   - Same machine: `https://localhost:8080`
   - LAN server: `https://192.168.1.100:8080`
3. Enter your WebUI username and password.
4. Click **"Test Connection"**.
5. Wait for the green "Connected" indicator.

### 4.3 Run Connection Test

The connection test verifies:
- Network reachability (TCP connection).
- TLS/SSL handshake (HTTPS).
- Authentication (valid credentials).
- API compatibility (server version check).

**Successful test output:**
```
Connection Test
  Server:     https://192.168.1.100:8443
  Mode:       Boba Server
  Status:     Connected
  Version:    1.4.2
  Latency:    45ms
  Auth:       OK
  API:        Compatible
```

**If the test fails:**

| Error | Cause | Solution |
|---|---|---|
| `Connection refused` | Server not running | Start Boba/qBitTorrent container |
| `Timeout` | Firewall or network issue | Check ports, verify network |
| `Certificate error` | Self-signed cert not trusted | Accept certificate exception or use trusted cert |
| `Authentication failed` | Wrong credentials | Verify API key or username/password |
| `API incompatible` | Server version too old | Upgrade Boba/qBitTorrent |

### 4.4 Auto-Discover (Optional)

If you don't know your server URL, use auto-discovery:

1. In Options → Server Settings, click **"Discover Servers"**.
2. BobaLink will scan your local network for Boba instances.
3. Discovered servers appear in a list with response times.
4. Click **"Select"** next to your server.
5. Enter credentials and test the connection.

**What auto-discovery checks:**

| URL | Timeout | Purpose |
|---|---|---|
| `https://boba.local:8443/health` | 5s | mDNS/bonjour resolution |
| `https://boba.local:8080/health` | 5s | Alternative port |
| `https://boba:8443/health` | 5s | Docker hostname |
| `https://localhost:8443/health` | 3s | Same-machine Docker |

---

## 5. Configuration Guide

### 5.1 Boba Server Settings

| Setting | Default | Description |
|---|---|---|
| Server URL | (empty) | Full HTTPS URL of your Boba server |
| API Key | (empty) | Authentication key from Boba admin |
| Connection Timeout | 30s | Maximum wait for API responses |
| Health Check Interval | 30s | How often to ping the server |

**Example configuration:**
```
Server URL:          https://boba.home.local:8443
API Key:             bob_live_a1b2c3d4e5f6...
Connection Timeout:  30 seconds
Health Check:        Every 30 seconds
```

### 5.2 qBitTorrent Direct Mode (Without Boba)

| Setting | Default | Description |
|---|---|---|
| Server URL | (empty) | Full HTTPS URL of qBitTorrent WebUI |
| Username | (empty) | WebUI username |
| Password | (empty) | WebUI password |
| Connection Timeout | 30s | Maximum wait for API responses |
| Health Check Interval | 30s | How often to ping the server |

**Note on Referer header:** qBitTorrent WebUI requires the `Referer` header to match the server origin. BobaLink handles this automatically.

### 5.3 Authentication Setup

#### API Key Authentication (Boba)

1. Obtain an API key from your Boba server administrator.
2. In Options → Server Settings, select **"API Key"**.
3. Paste the key into the input field.
4. The key is masked for security. Click the eye icon to reveal.
5. Click **"Test Connection"** to validate.

#### Username/Password (qBitTorrent)

1. In Options → Server Settings, select **"qBitTorrent Direct"**.
2. Enter your WebUI username.
3. Enter your WebUI password.
4. Click **"Test Connection"**.

Bobalink will automatically:
- Authenticate and receive a session cookie.
- Store the cookie for subsequent requests.
- Refresh the session when it expires.

#### Basic Authentication (Advanced)

For servers behind reverse proxies with Basic Auth:

1. Select **"Basic Auth"**.
2. Enter the Basic Auth username and password.
3. BobaLink will send `Authorization: Basic {base64}` headers.

#### Custom Header (Advanced)

For reverse proxies requiring custom headers (e.g., Cloudflare Access):

1. Select **"Custom Header"**.
2. Enter the header name (e.g., `CF-Access-Client-Id`).
3. Enter the header value.

### 5.4 Category Configuration

Categories organize torrents in qBitTorrent. To configure:

1. Open Options → Download Preferences.
2. Enter a default category name (e.g., `movies`).
3. Categories are created automatically in qBitTorrent 4.5+.
4. For older versions, pre-create categories in qBitTorrent WebUI.

**Common category schemes:**

| Category | Use Case |
|---|---|
| `movies` | Film downloads |
| `tv-shows` | Television series |
| `music` | Audio files |
| `software` | Applications and tools |
| `games` | Game files |
| `books` | E-books and documents |
| `browser` | Auto-categorized browser sends |

### 5.5 Download Path Settings

Override the default download directory:

1. Open Options → Download Preferences.
2. Enter an absolute path in **Default Save Path**.

**Path examples:**

| OS | Example Path |
|---|---|
| Linux | `/mnt/downloads/torrents` |
| macOS | `/Users/username/Downloads/Torrents` |
| Windows | `D:\\Downloads\\Torrents` |
| Docker (Linux container) | `/downloads/movies` |

> **Important**: The path must be valid on the **server** (where qBitTorrent runs), not your local machine.

**Using qBitTorrent's Automatic Torrent Management:**

1. In qBitTorrent WebUI → Options → Downloads.
2. Enable **"Automatic Management Mode"**.
3. Set default save paths per category.
4. Torrents are automatically moved to category folders on completion.

---

## 6. Verification

### 6.1 Test on a Known Torrent Site

After configuration, verify that BobaLink works:

1. Open a new browser tab.
2. Navigate to a site with known magnet links. For testing, you can use:
   - `https://ubuntu.com/download/alternative-downloads` (official Ubuntu torrents)
   - Any torrent index site
3. Wait for the page to fully load.
4. Look at the BobaLink icon in the toolbar.

**Expected behavior:**
- The badge shows a number (count of detected torrents).
- The badge is green (connected to server).

### 6.2 Verify Detection

1. Click the BobaLink icon to open the popup.
2. You should see a list of detected torrents.
3. Each torrent shows:
   - Name (e.g., "Ubuntu 24.04 LTS Desktop")
   - Size (if available)
   - Source (magnet link or .torrent file)

**If no torrents are detected:**
- Check that the page actually contains magnet links.
- Try scrolling down to trigger lazy loading.
- Check the [Troubleshooting](#9-troubleshooting-installation-issues) section.

### 6.3 Verify Sending

1. In the popup, check one or more torrents.
2. Click **"Send Selected"**.
3. Wait for the confirmation:
   - Browser notification: "Torrent Sent — {name} added to download queue"
   - Or check the popup status bar.

### 6.4 Check qBitTorrent for Download

1. Open your qBitTorrent WebUI in a browser.
2. Check the transfer list.
3. The sent torrent should appear with status "Downloading" or "Stalled".
4. If using Boba Server, check the Boba dashboard for job status.

**Complete verification checklist:**

| Check | Method | Expected Result |
|---|---|---|
| Extension installed | Icon visible in toolbar | Yes |
| Server connected | Badge is green | Yes |
| Detection works | Badge shows count on torrent page | > 0 |
| Send works | Send a test torrent | Success notification |
| Queue works | Disconnect server, send, reconnect | Item sent after reconnect |
| Settings persist | Restart browser, check Options | Settings retained |

---

## 7. Updating

### 7.1 Automatic Updates from Store

If installed from Chrome Web Store, AMO, or Opera Addons:
- Updates are applied automatically by the browser.
- No user action required.
- Check `chrome://extensions` to see the current version.

### 7.2 Manual Update Process

For manual installations:

1. Download the latest release ZIP from GitHub.
2. Extract to the same location as the previous installation (overwrite).
3. Navigate to your browser's extensions page.
4. Find BobaLink and click the **refresh/reload** icon.
5. Verify the version number updated.

**Chrome:**
```
chrome://extensions → Find BobaLink → Click refresh icon
```

**Firefox:**
```
about:debugging → This Firefox → Find BobaLink → Click Reload
```

### 7.3 Version Compatibility

| BobaLink | Boba Server | qBitTorrent | Status |
|---|---|---|---|
| 1.0.x | 1.0.x – 1.4.x | 4.4+ | Fully compatible |
| 1.0.x | 1.5.x+ | 4.4+ | May have minor issues |
| 1.0.x | < 1.0.x | 4.4+ | Not supported |
| 1.0.x | Any | < 4.4.0 | WebUI API may differ |

**Before updating:**
1. Check the release notes for breaking changes.
2. Back up your configuration (export from Options).
3. Ensure your server versions are compatible.

---

## 8. Uninstallation

### 8.1 Remove from Chrome

**Method 1 — Extensions page:**
1. Navigate to `chrome:///extensions`.
2. Find BobaLink.
3. Click **"Remove"**.
4. Confirm by clicking **"Remove"** again.

**Method 2 — Toolbar icon:**
1. Right-click the BobaLink icon.
2. Select **"Remove from Chrome"**.
3. Confirm.

### 8.2 Remove from Firefox

1. Navigate to `about:addons`.
2. Find BobaLink in the Extensions list.
3. Click the **⋯** menu → **"Remove"**.
4. Confirm.

### 8.3 Remove from Opera

1. Navigate to `opera://extensions`.
2. Find BobaLink.
3. Click **"Remove"**.
4. Confirm.

### 8.4 Remove from Yandex

1. Navigate to `browser://extensions`.
2. Find BobaLink.
3. Click **"Remove"**.
4. Confirm.

### 8.5 Clean Up Stored Data

**Chrome:**
```
chrome://settings/cookies/detail?site=bobalink (if applicable)
```

**All browsers:**
BobaLink stores data in `chrome.storage.local` which is automatically cleared when the extension is removed. This includes:
- Server configuration (URLs, credentials)
- Queue items
- UI preferences
- Encryption keys (session storage, cleared on browser restart)

**Manual cleanup (if data persists):**

```javascript
// Open DevTools for the extension background page
// Run in Console:
chrome.storage.local.getBytesInUse(null, (bytes) => {
  console.log(`Storage used: ${bytes} bytes`);
});

// Clear all data
chrome.storage.local.clear(() => {
  console.log('All extension data cleared');
});
```

---

## 9. Troubleshooting Installation Issues

### 9.1 "This extension is blocked by the administrator"

**Cause**: Enterprise policies restrict extension installation.

**Solutions**:

**Option A — Whitelist the extension (IT Admin):**
```
Windows Registry:
HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Google\Chrome\ExtensionInstallAllowlist
  Add the extension ID

Or via Group Policy:
Administrative Templates → Google Chrome → Extensions →
  Configure extension installation allow list
```

**Option B — Force install (IT Admin):**
```
Group Policy:
Administrative Templates → Google Chrome → Extensions →
  Configure force-installed apps and extensions
  Add: {extension-id};https://clients2.google.com/service/update2/crx
```

### 9.2 "Manifest file is missing or unreadable"

**Cause**: Wrong folder selected when loading unpacked.

**Solution**:
1. Ensure you extracted the ZIP completely.
2. Select the folder containing `manifest.json`, not a parent or subfolder.
3. Verify `manifest.json` exists:
   ```bash
   ls /opt/bobalink/chrome/manifest.json
   ```

### 9.3 "Invalid value for 'content_security_policy'"

**Cause**: Browser version too old for MV3 CSP format.

**Solution**: Upgrade your browser to the minimum required version (Chrome 88+, Firefox 109+).

### 9.4 Extension Loads But Icon Is Gray

**Cause**: Extension not configured.

**Solution**:
1. Click the icon to open the popup.
2. Follow the first-time setup wizard.
3. Configure your server URL and credentials.

### 9.5 "Failed to load extension from..."

**Common causes and solutions:**

| Error Message | Cause | Solution |
|---|---|---|
| `Cannot load extension with file or directory name _metadata` | macOS metadata folder | Delete `__MACOSX` folder from extracted ZIP |
| `Invalid locale file` | Corrupted `_locales` | Re-download the ZIP |
| `Required value version is missing` | Wrong folder selected | Navigate deeper to find `manifest.json` |
| `Permission 'XYZ' is unknown` | Browser doesn't support a permission | Update browser or use a different build |

### 9.6 Certificate Warnings

When using self-signed certificates (common in home lab setups):

**Chrome:**
1. Navigate to your server URL (e.g., `https://192.168.1.100:8443`).
2. Click **"Advanced"** → **"Proceed to {server} (unsafe)"**.
3. The certificate is now trusted for this session.

**For permanent trust:**
```bash
# Export the server certificate
openssl s_client -connect 192.168.1.100:8443 </dev/null 2>/dev/null \
  | openssl x509 -outform PEM > boba-cert.pem

# Install system-wide (Linux)
sudo cp boba-cert.pem /usr/local/share/ca-certificates/boba.crt
sudo update-ca-certificates

# macOS
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain boba-cert.pem

# Windows (PowerShell admin)
Import-Certificate -FilePath boba-cert.pem \
  -CertStoreLocation Cert:\LocalMachine\Root
```

### 9.7 Network Timeouts During Setup

| Symptom | Cause | Solution |
|---|---|---|
| "Connection timed out" | Firewall blocking port | Open port 8443 (Boba) or 8080 (qBT) |
| "Network Error" | HTTPS required but HTTP used | Change URL to `https://` |
| "DNS resolution failed" | `.local` domain not resolving | Use IP address instead of hostname |
| "Connection refused" | Wrong port or service down | Verify port with `netstat` |

### 9.8 Firefox-Specific Issues

| Issue | Solution |
|---|---|
| "Add-on could not be installed" (corrupt) | The XPI must be signed. Use `about:debugging` temporary load for unsigned. |
| `chrome.*` API errors | The `webextension-polyfill` may not be loading. Check build output. |
| Storage quota exceeded | Firefox has stricter storage limits. Clear old queue items. |
| Service worker not persistent | Firefox suspends service workers more aggressively. Use `chrome.alarms` to keep alive. |

### 9.9 Docker-Specific Issues

If running Boba or qBitTorrent in Docker:

```bash
# Verify container is running
docker ps | grep boba

# Check container logs
docker logs boba-container-name

# Verify port mapping
docker port boba-container-name
# Expected: 0.0.0.0:8443->8443/tcp

# Test from inside the container
docker exec -it boba-container-name curl localhost:8443/health

# Check container network
docker network inspect bridge
```

**Common Docker issues:**

| Issue | Cause | Solution |
|---|---|---|
| Port not exposed | Missing `-p` flag | Add `-p 8443:8443` to run command |
| Container exits immediately | Config error | Check logs with `docker logs` |
| Cannot reach from host | Binding to 127.0.0.1 only | Use `-p 0.0.0.0:8443:8443` |
| SSL errors | Certificate not mounted | Mount cert volume: `-v /path/to/certs:/app/certs` |

### 9.10 Getting Help

If you encounter an issue not covered here:

1. Check the [User Guide Troubleshooting](user-guide.md#4-troubleshooting) section.
2. Check GitHub Issues: `https://github.com/bobaproject/bobalink/issues`
3. Enable debug logging (see [Developer Guide](developer-guide.md#93-viewing-service-worker-logs)).
4. Collect the following information for support:
   - Browser and version
   - BobaLink version
   - Server type (Boba/qBitTorrent) and version
   - Error messages (screenshots or text)
   - Steps to reproduce

---

*End of Installation Guide*
