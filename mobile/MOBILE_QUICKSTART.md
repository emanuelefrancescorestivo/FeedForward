# Testing FeedForward on your phone

> The Expo app is an early prototype and predates the web app: it has no
> "My week" planner. On a phone, the web app at `http://<your-computer>:8000/app`
> is the current interface.

The app needs the **backend running on your computer** and the **app running in
Expo Go on your phone**, both on the **same Wi-Fi network**. The API URL is now
auto-detected, so you don't have to edit any IP addresses.

## What you need first

- **Node.js 18+** on your computer — https://nodejs.org
- **Python 3.10+** on your computer (for the backend)
- The **Expo Go** app on your phone (free):
  - iOS: App Store → "Expo Go"
  - Android: Play Store → "Expo Go"
- Your **phone and computer on the same Wi-Fi**.

---

## Step 1 — Start the backend (Terminal 1)

```bash
cd backend
pip install -r requirements.txt

# Bind to 0.0.0.0 so your phone can reach it (not just localhost)
uvicorn feedforward.api.main:app --host 0.0.0.0 --port 8000
```

Leave this running. You should see `Application startup complete`. Test it in a
browser on your computer: http://localhost:8000/docs should show the API.

> There's a shortcut script: `./run_backend.sh` does the same thing.

---

## Step 2 — Start the app (Terminal 2)

```bash
cd mobile
npm install          # first time only; takes a few minutes
npx expo start
```

A **QR code** appears in the terminal.

---

## Step 3 — Open it on your phone

- **iPhone:** open the Camera app, point it at the QR code, tap the banner.
- **Android:** open **Expo Go**, tap "Scan QR code", scan it.

The app downloads to Expo Go and launches. The first load takes a moment.

That's it — browse a goal, tap a food, and you'll see the live recommendations,
evidence badges, bioavailability profile and meal planner, all served by the
backend on your computer.

---

## If something doesn't work

**"Network request failed" / spinner never loads**
The phone can't reach the backend. Check:
1. Backend is running with `--host 0.0.0.0` (not the default), and you can open
   `http://localhost:8000/docs` on your computer.
2. Phone and computer are on the **same Wi-Fi** (not guest network / VPN).
3. Your computer's firewall isn't blocking port 8000. On macOS, allow incoming
   connections for Python when prompted; on Windows, allow Python through the
   firewall.
4. As a fallback, find your computer's local IP and set it explicitly in
   `mobile/app.json` under `expo > extra > apiBaseUrl`, e.g.
   `"apiBaseUrl": "http://192.168.1.23:8000"`, then restart Expo.
   - macOS/Linux: `ipconfig getifaddr en0` or `hostname -I`
   - Windows: `ipconfig` → IPv4 Address

**Expo Go shows a version mismatch**
Update Expo Go from the store, or run `npx expo install --fix` in `mobile/`.

**"Metro bundler" errors on first run**
Delete `node_modules` and reinstall: `rm -rf node_modules && npm install`.

**No physical phone?**
- iOS Simulator (Mac only, needs Xcode): press `i` in the Expo terminal.
- Android Emulator (needs Android Studio): press `a`.
- Quick web preview (not full native, but loads the UI): press `w`.
  For web, the backend URL falls back to `localhost:8000`, which works since it's
  the same machine.

---

## What you're seeing

The app is the consumer surface. Toggle **Professional mode** in the Profile tab
to reveal evidence grades (A–D) and PubMed citations — the same engine, the
richer presentation for clinicians.
