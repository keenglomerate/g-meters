# 🔮 G-Meters: Multi-Model AI Quota & Token Monitor

A cross-platform, real-time widget designed to monitor token usage and API rate limits for **Google Antigravity/Gemini** and **Anthropic Claude**. 

The tool utilizes a hybrid architecture: it can connect to a secure **Local Bridge** on your machine or fall back to a **Serverless Cloud Proxy** to check your status safely without exposing credentials or bloating your main billing limits.

---

## ✨ Features

- **Double Circular Progress Rings:** Renders remaining Sprint Limits and Weekly Baselines using SVG paths.
- **Micro-Animations:** Fluid glassmorphic UI card designs, pulsing connection states, and rotating refresh transitions.
- **Dual Connection Modes:** Attempts to sync via the Local Bridge, falling back to your Cloud Proxy URL if you are away from your development machine.
- **Multitasking Alert Details:** Expand detailed statistics for TPM (Tokens/Minute), RPM (Requests/Minute), and daily quotas.

---

## 🚀 Getting Started

### 1. Launch the Local Bridge Daemon
Run the lightweight background server (written in pure standard Python, no external libraries required):
```bash
./daemon.py
```
This runs a local CORS-enabled API server at `http://localhost:5000/api/quota`.

### 2. Open the Widget
Simply double-click the **`index.html`** file to run it in any web browser, or host the folder on a local dev server.

---

## 🔑 Fetching Live API Quotas

By default, if no keys are found, the daemon runs in **Simulation Mode** (demonstrating real-time updates and consumption changes).

To connect to live services:
1. Create a **`.env`** file inside the `g-meters` directory:
   ```env
   GEMINI_API_KEY="your-google-ai-studio-api-key"
   ANTHROPIC_API_KEY="your-anthropic-api-key"
   ```
2. Restart `daemon.py`. The local bridge will automatically pull live limits and remaining quotas directly from the provider headers!

---

## ⚡ Serverless Cloud Setup (Optional)
If you want to view your token widget on other platforms (like your smartphone or tablet) while away from your computer:
1. Copy the logic from `daemon.py` into a **Cloudflare Worker** or **Vercel Serverless Function**.
2. Store your API keys securely inside the cloud environment variables.
3. Pass the resulting worker URL into the **Connection Settings** popup panel inside the widget.
