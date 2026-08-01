# AIMAOS Mobile (Android Native App Shell)

A IMAOS Mobile is a secure native Android application shell built with Kotlin, Jetpack Compose / AndroidX, and Android KeyStore hardware encryption. It connects your Android smartphone directly to your running AIMAOS desktop/server instance over local Wi-Fi, Tailscale mesh VPN, or HTTPS reverse proxy.

---

## 🔒 Security Architecture

Security is paramount for remote and mobile access:

1. **Mandatory Bearer Token Authentication (`AIMAOS_UI_TOKEN`)**:
   - `aimaos_ui.py` requires an explicit access token when bound to non-loopback network interfaces (`0.0.0.0`).
   - The Android app injects `Authorization: Bearer <AIMAOS_UI_TOKEN>` and `X-AIMAOS-Token` into every WebView request and fetch header.
   - Any request missing or presenting an invalid token receives `401 authentication_required`.

2. **Hardware-Backed Credential Storage (`EncryptedSharedPreferences`)**:
   - Server URLs and access tokens are stored in Android `EncryptedSharedPreferences` using AES-256-GCM encryption backed by the hardware Android KeyStore MasterKey module.
   - Credentials are never written or cached in plain text on the mobile file system.

3. **Biometric App Lock**:
   - Optional fingerprint / Face ID / PIN authentication before launching the app shell or accessing saved token credentials.

4. **Transport Security (TLS / HTTPS)**:
   - Restricts unencrypted HTTP cleartext traffic via `network_security_config.xml` while supporting local private subnets during LAN development.

---

## 🚀 Setting Up the Server for Mobile Access

### 1. Launch `aimaos_ui.py` with Non-Loopback Binding & Token

Before connecting from your phone, launch the AIMAOS server on your desktop/server machine with an environment token:

```bash
export AIMAOS_UI_TOKEN="your-secure-32-byte-token-here"
python3 aimaos_ui.py --host 0.0.0.0 --port 8000
```

### 2. Determine Your Server IP or Hostname

- **Local Wi-Fi Network**: Find your machine's local IP address (e.g. `192.168.1.50`).
- **Tailscale / VPN (Recommended for Remote Access)**: Use your machine's Tailscale IP (e.g. `100.x.y.z`).
- **HTTPS Reverse Proxy**: Use your domain URL (e.g. `https://aimaos.yourdomain.com`).

---

## 📱 Using the AIMAOS Mobile App

1. **Launch App**: Open AIMAOS Mobile on your Android device.
2. **First-Time Setup**:
   - Enter **Server URL**: `http://192.168.1.50:8000` (or your domain/Tailscale IP).
   - Enter **Access Token**: Enter the exact `AIMAOS_UI_TOKEN` string set on your server.
   - Toggle **Require Biometric Lock** if desired.
   - Tap **Test & Save**.
3. **Dashboard View**:
   - Upon successful 200 OK authentication check, your dashboard will load with full touch navigation, pull-to-refresh, and document upload capability.
4. **Settings & Retry**:
   - Tap the settings gear icon in the top header bar anytime to update server URL or access tokens.

---

## 🛠️ Building the Android APK

### Using Gradle Command Line:

From the `android/` directory:

```bash
cd android
./gradlew assembleDebug
```

The output APK will be placed at `android/app/build/outputs/apk/debug/app-debug.apk`.

### Using Android CLI:

```bash
android run --apks=android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 🧪 Verification & Health Check

To verify system integrity and test HTTP boundary token rules:

```bash
python3 doctor.py
pytest tests/unit/test_http_boundary.py
```
