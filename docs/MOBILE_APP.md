# AIMAOS Android Shell (Experimental)

`android/` contains a Kotlin/AppCompat WebView shell for the desktop workstation. It uses XML layouts and ViewBinding; it is not a Jetpack Compose application and is not a production or app-store release.

Do not use the shell with confidential data until the authentication/origin items in this document are tested end to end.

## Implemented behavior

- server URL and optional access token configuration;
- connection test against the AIMAOS API;
- encrypted preferences via `EncryptedSharedPreferences` and an Android Keystore `MasterKey`;
- optional `BiometricPrompt` gate at launch;
- WebView dashboard, back navigation, pull-to-refresh, retry UI, and file chooser;
- top-level request headers for bearer and `X-AIMAOS-Token` authentication;
- app backup disabled in the manifest.

Keystore-backed encryption does not guarantee hardware-backed keys on every Android device; that depends on device capability and Android implementation.

## Current security limitations

1. The WebView injects the token into top-level navigation requests, but the page's JavaScript `fetch` calls use the browser application's own session-token flow. End-to-end authenticated API behavior has not been demonstrated by an automated Android test.
2. Navigation is not yet restricted to one approved server origin. `shouldOverrideUrlLoading` currently reloads requested URLs with headers, so an origin allowlist is required before production use.
3. No certificate pinning, managed-device policy, remote wipe, release signing procedure, or mobile security assessment is provided.
4. Cleartext network policy permits only emulator/loopback names in the checked-in configuration; it does not permit arbitrary private-LAN IP addresses.
5. The server itself is loopback-first and rejects an unsafe non-loopback launch unless the administrator explicitly configures the documented LAN/TLS boundary.

## Recommended development connection

Keep AIMAOS bound to `127.0.0.1` on its host. Put an authenticated TLS reverse proxy on that host, set a long random `AIMAOS_UI_TOKEN`, and connect the shell only to the HTTPS origin. Do not expose port 8080 directly and do not send a token over HTTP.

Server-side guidance is in [`SECURITY.md`](../SECURITY.md) and [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Build status

The repository includes Gradle build files but does not currently include the Gradle wrapper (`gradlew`). Build with Android Studio or an installed compatible Gradle/Android SDK:

```bash
cd android
gradle assembleDebug
```

Expected debug output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Dependency versions include alpha releases of Android security/biometric libraries; review and update them before a release build.

## Required work before beta distribution

- restrict WebView navigation and token injection to the configured HTTPS origin;
- bridge or redesign browser API authentication so every request is verified;
- add instrumentation tests for valid/invalid tokens, redirects, file upload, logout/credential clearing, and biometric failure;
- remove mixed-content compatibility mode unless a narrowly justified test case requires it;
- add a Gradle wrapper, release signing, dependency review, icons, versioning, and reproducible CI build;
- conduct Android/WebView security and accessibility review;
- document supported Android versions and secure update delivery.

Until those items are complete, use the desktop browser on the AIMAOS host as the supported public-beta interface.
