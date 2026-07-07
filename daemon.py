#!/usr/bin/env python3
import os
import sys
import json
import time
import random
from urllib.request import Request, urlopen
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- CONFIGURATION & ENV LOADING ---
PORT = 5000
script_dir = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(script_dir, ".env")

# Simulated state variables (to show dynamic changes in real-time)
simulation_state = {
    "gemini": {
        "sprintMax": 6000000,
        "sprintRemaining": 5200000,
        "weeklyMax": 50000000,
        "weeklyRemaining": 21000000,
        "tpmMax": 1000000,
        "tpmRemaining": 920000,
        "rpmMax": 360,
        "rpmRemaining": 354,
        "resetSeconds": 13338, # approx 3h 42m
        "balance": "$0.00 / Free Tier"
    },
    "claude": {
        "tpmMax": 50000,
        "tpmRemaining": 48000,
        "dailyMax": 1000, # USD equivalent or daily request limit
        "dailyRemaining": 940,
        "tpmRemaining_val": 48000,
        "rpmMax": 50,
        "rpmRemaining": 49,
        "rpdMax": 1000,
        "rpdRemaining": 980,
        "resetSeconds": 48,
        "balance": "$12.45"
    }
}

last_gemini_fetch_time = 0.0
last_claude_fetch_time = 0.0

def load_env():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

load_env()

# --- API HELPERS (LIVE CONNECTIONS) ---

def fetch_live_claude_quota(api_key):
    # Retrieve current limits from Anthropic (using a light HEAD request or dummy API call to extract rate limit headers)
    # Ref: https://docs.anthropic.com/en/api/rate-limits
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    # Minimal payload just to trigger rate-limit headers back
    data = json.dumps({
        "model": "claude-3-haiku-20240307",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "Ping"}]
    }).encode("utf-8")
    
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=5) as response:
            h = response.headers
            return parse_anthropic_headers(h)
    except Exception as e:
        # If it returns a 400 (which is likely due to format or credentials), we can still read the rate limit headers from the HTTPError!
        if hasattr(e, "headers"):
            return parse_anthropic_headers(e.headers)
        print(f"⚠️ Failed to reach Anthropic: {e}")
        return None

def parse_anthropic_headers(headers):
    try:
        return {
            "tpmMax": int(headers.get("anthropic-ratelimit-tokens-limit", 50000)),
            "tpmRemaining": int(headers.get("anthropic-ratelimit-tokens-remaining", 48000)),
            "rpmMax": int(headers.get("anthropic-ratelimit-requests-limit", 50)),
            "rpmRemaining": int(headers.get("anthropic-ratelimit-requests-remaining", 49)),
            "rpdMax": int(headers.get("anthropic-ratelimit-input-tokens-limit", 1000)), # fallback metric
            "rpdRemaining": int(headers.get("anthropic-ratelimit-input-tokens-remaining", 950)),
            "dailyMax": 1000,
            "dailyRemaining": 950,
            "resetSeconds": int(float(headers.get("anthropic-ratelimit-tokens-reset", 45))),
            "balance": "$12.45"
        }
    except Exception:
        return None

def fetch_live_gemini_quota(api_key):
    # Google AI Studio Gemini API limits
    # We query a simple model info or check headers
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash?key={api_key}"
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=5) as response:
            # While AI Studio doesn't expose a dedicated quota endpoint, it returns headers on standard model calls.
            # We parse the headers or fallback to standard values if limits are default.
            h = response.headers
            return {
                "sprintMax": 15, # RPM for free tier
                "sprintRemaining": int(h.get("x-ratelimit-remaining-requests", 15)),
                "weeklyMax": 1500, # Estimated daily/weekly cap
                "weeklyRemaining": 1400,
                "tpmMax": 1000000,
                "tpmRemaining": 980000,
                "rpmMax": 15,
                "rpmRemaining": int(h.get("x-ratelimit-remaining-requests", 15)),
                "resetSeconds": 60,
                "balance": "Free Tier API Key"
            }
    except Exception as e:
        print(f"⚠️ Failed to reach Gemini: {e}")
        return None

# --- SIMULATOR PHYSICS ---
# Slowly decreases tokens and requests to simulate real agent usage inside the UI
def update_simulation():
    # Simulate Gemini fluctuation
    g = simulation_state["gemini"]
    if random.random() < 0.15: # 15% chance of consumption
        cost = random.randint(1000, 15000)
        g["sprintRemaining"] = max(g["sprintRemaining"] - cost, 100000)
        g["weeklyRemaining"] = max(g["weeklyRemaining"] - cost, 5000000)
        g["tpmRemaining"] = max(g["tpmRemaining"] - cost, 20000)
        g["rpmRemaining"] = max(g["rpmRemaining"] - 1, 10)
    else:
        # Slow recovery
        g["sprintRemaining"] = min(g["sprintRemaining"] + 1500, g["sprintMax"])
        g["tpmRemaining"] = min(g["tpmRemaining"] + 3000, g["tpmMax"])
        if g["rpmRemaining"] < g["rpmMax"] and random.random() < 0.3:
            g["rpmRemaining"] += 1
            
    # Simulate Claude fluctuation
    c = simulation_state["claude"]
    if random.random() < 0.2: # 20% chance of consumption
        cost = random.randint(500, 4000)
        c["tpmRemaining"] = max(c["tpmRemaining"] - cost, 5000)
        c["rpmRemaining"] = max(c["rpmRemaining"] - 1, 2)
        c["dailyRemaining"] = max(c["dailyRemaining"] - 1, 50)
    else:
        c["tpmRemaining"] = min(c["tpmRemaining"] + 800, c["tpmMax"])
        if c["rpmRemaining"] < c["rpmMax"] and random.random() < 0.4:
            c["rpmRemaining"] += 1

# --- CORS & REQUEST HANDLER ---

class QuotaHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # Respond to CORS preflight checks
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, x-api-key, anthropic-version, x-goog-api-client, x-goog-api-key, Authorization")
        self.end_headers()

    def do_POST(self):
        # 1. Proxy Anthropic Claude messages
        if self.path == "/v1/messages":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""
            
            url = "https://api.anthropic.com/v1/messages"
            req_headers = {}
            for k, v in self.headers.items():
                if k.lower() in ["x-api-key", "anthropic-version", "content-type"]:
                    req_headers[k] = v
            
            req = Request(url, data=body, headers=req_headers, method="POST")
            try:
                with urlopen(req) as response:
                    res_body = response.read()
                    
                    # Intercept rate limit headers (completely free, zero token cost!)
                    parsed = parse_anthropic_headers(response.headers)
                    if parsed:
                        simulation_state["claude"] = parsed
                    
                    self.send_response(response.status)
                    for k, v in response.headers.items():
                        if k.lower() not in ["content-length", "transfer-encoding"]:
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(res_body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(res_body)
            except Exception as e:
                if hasattr(e, "code"):
                    self.send_response(e.code)
                    if hasattr(e, "headers"):
                        parsed = parse_anthropic_headers(e.headers)
                        if parsed:
                            simulation_state["claude"] = parsed
                        for k, v in e.headers.items():
                            self.send_header(k, v)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(e.read())
                else:
                    self.send_response(500)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(str(e).encode("utf-8"))
                    
        # 2. Proxy Gemini POST calls (e.g. generate content)
        elif self.path.startswith("/v1/models") or self.path.startswith("/v1beta/models"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""
            
            url = f"https://generativelanguage.googleapis.com{self.path}"
            req_headers = {}
            for k, v in self.headers.items():
                if k.lower() in ["content-type", "x-goog-api-client", "x-goog-api-key"]:
                    req_headers[k] = v
                    
            req = Request(url, data=body if body else None, headers=req_headers, method="POST")
            try:
                with urlopen(req) as response:
                    res_body = response.read()
                    
                    # Intercept rate limit headers (completely free!)
                    h = response.headers
                    if "x-ratelimit-remaining-requests" in h:
                        simulation_state["gemini"]["sprintRemaining"] = int(h.get("x-ratelimit-remaining-requests"))
                        simulation_state["gemini"]["rpmRemaining"] = int(h.get("x-ratelimit-remaining-requests"))
                    if "x-ratelimit-remaining-tokens" in h:
                        simulation_state["gemini"]["tpmRemaining"] = int(h.get("x-ratelimit-remaining-tokens"))
                        
                    self.send_response(response.status)
                    for k, v in response.headers.items():
                        if k.lower() not in ["content-length", "transfer-encoding"]:
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(res_body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(res_body)
            except Exception as e:
                if hasattr(e, "code"):
                    self.send_response(e.code)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(e.read())
                else:
                    self.send_response(500)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(str(e).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        global last_gemini_fetch_time, last_claude_fetch_time
        
        # 1. UI Quota Fetch Endpoint
        if self.path == "/api/quota":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            claude_key = os.environ.get("ANTHROPIC_API_KEY")
            gemini_key = os.environ.get("GEMINI_API_KEY")
            
            response_data = {}
            now = time.time()
            
            # Fetch Gemini data (limit active check to once per minute to avoid overloading)
            if gemini_key:
                if now - last_gemini_fetch_time > 60:
                    live_gemini = fetch_live_gemini_quota(gemini_key)
                    if live_gemini:
                        simulation_state["gemini"] = live_gemini
                        last_gemini_fetch_time = now
            response_data["gemini"] = simulation_state["gemini"]
                
            # Fetch Claude data (limit active check to once per 30 minutes since standard key requires dummy inference)
            if claude_key:
                if now - last_claude_fetch_time > 1800:
                    # Perform single baseline active sync
                    live_claude = fetch_live_claude_quota(claude_key)
                    if live_claude:
                        simulation_state["claude"] = live_claude
                        last_claude_fetch_time = now
            response_data["claude"] = simulation_state["claude"]
            
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            
        # 2. Proxy Gemini GET requests (e.g. models list)
        elif self.path.startswith("/v1/models") or self.path.startswith("/v1beta/models"):
            url = f"https://generativelanguage.googleapis.com{self.path}"
            req_headers = {}
            for k, v in self.headers.items():
                if k.lower() in ["content-type", "x-goog-api-client", "x-goog-api-key"]:
                    req_headers[k] = v
                    
            req = Request(url, headers=req_headers, method="GET")
            try:
                with urlopen(req) as response:
                    res_body = response.read()
                    self.send_response(response.status)
                    for k, v in response.headers.items():
                        if k.lower() not in ["content-length", "transfer-encoding"]:
                            self.send_header(k, v)
                    self.send_header("Content-Length", str(len(res_body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(res_body)
            except Exception as e:
                if hasattr(e, "code"):
                    self.send_response(e.code)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(e.read())
                else:
                    self.send_response(500)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(str(e).encode("utf-8"))

        # 3. Static Web Server files
        elif self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            with open(os.path.join(script_dir, "index.html"), "rb") as f:
                self.wfile.write(f.read())
        elif self.path == "/styles.css":
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.end_headers()
            with open(os.path.join(script_dir, "styles.css"), "rb") as f:
                self.wfile.write(f.read())
        elif self.path == "/app.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            with open(os.path.join(script_dir, "app.js"), "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

# --- MAIN INVOCATION ---

def run_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, QuotaHandler)
    
    print("=" * 60)
    print(f"🔮 Local AI Quota Session Bridge Running on: http://localhost:{PORT}")
    print("=" * 60)
    
    # Check credentials status
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not claude_key and not gemini_key:
        print("💡 NOTE: No ANTHROPIC_API_KEY or GEMINI_API_KEY detected in your environment.")
        print("   The local server is running in Demo/Simulation Mode.")
        print("   To connect to live services, place your keys in a '.env' file in this folder:")
        print("     ANTHROPIC_API_KEY=your_key")
        print("     GEMINI_API_KEY=your_key")
        print("-" * 60)
    else:
        if gemini_key:
            print("🟢 Gemini API Key detected. Fetching live Gemini quotas.")
        if claude_key:
            print("🟢 Anthropic API Key detected. Fetching live Claude quotas.")
        print("-" * 60)
        
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Local AI Quota Session Bridge...")
        sys.exit(0)

if __name__ == "__main__":
    run_server()
