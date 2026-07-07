// --- CONSTANTS & CONFIGURATION ---
const DEFAULT_SETTINGS = {
  connectionMode: 'hybrid', // hybrid, local, cloud
  localUrl: 'http://localhost:5000',
  cloudUrl: '',
  refreshInterval: 30 // seconds
};

let settings = { ...DEFAULT_SETTINGS };
let activeIntervalId = null;
let countdownIntervalId = null;

// Countdown State (for real-time timer updates between polls)
let geminiResetSeconds = 0;
let claudeResetSeconds = 0;

// --- DOM ELEMENTS ---
const elements = {
  connectionStatus: document.getElementById('connection-status'),
  settingsModal: document.getElementById('settings-modal'),
  settingsToggle: document.getElementById('settings-toggle'),
  settingsCancel: document.getElementById('settings-cancel'),
  settingsSave: document.getElementById('settings-save'),
  manualRefresh: document.getElementById('manual-refresh'),
  
  // Settings Inputs
  connectionModeSelect: document.getElementById('connection-mode'),
  localUrlInput: document.getElementById('local-bridge-url'),
  cloudUrlInput: document.getElementById('cloud-proxy-url'),
  refreshIntervalInput: document.getElementById('refresh-interval'),
  intervalDisplay: document.getElementById('interval-display'),
  
  // Gemini UI elements
  geminiSprintRing: document.getElementById('gemini-sprint-ring'),
  geminiSprintPct: document.getElementById('gemini-sprint-pct'),
  geminiWeeklyRing: document.getElementById('gemini-weekly-ring'),
  geminiWeeklyPct: document.getElementById('gemini-weekly-pct'),
  geminiSprintUsage: document.getElementById('gemini-sprint-usage'),
  geminiResetTimer: document.getElementById('gemini-reset-timer'),
  geminiEndpoint: document.getElementById('gemini-endpoint'),
  geminiDetailsToggle: document.getElementById('gemini-details-toggle'),
  geminiDetailsPanel: document.getElementById('gemini-details-panel'),
  geminiTpm: document.getElementById('gemini-tpm'),
  geminiRpm: document.getElementById('gemini-rpm'),
  geminiCredits: document.getElementById('gemini-credits'),
  
  // Claude UI elements
  claudeTpmRing: document.getElementById('claude-tpm-ring'),
  claudeTpmPct: document.getElementById('claude-tpm-pct'),
  claudeDailyRing: document.getElementById('claude-daily-ring'),
  claudeDailyPct: document.getElementById('claude-daily-pct'),
  claudeTpmUsage: document.getElementById('claude-tpm-usage'),
  claudeResetTimer: document.getElementById('claude-reset-timer'),
  claudeEndpoint: document.getElementById('claude-endpoint'),
  claudeDetailsToggle: document.getElementById('claude-details-toggle'),
  claudeDetailsPanel: document.getElementById('claude-details-panel'),
  claudeRpm: document.getElementById('claude-rpm'),
  claudeRpd: document.getElementById('claude-rpd'),
  claudeCredits: document.getElementById('claude-credits')
};

// --- CORE UTILITIES ---

// Load settings from localStorage
function loadSettings() {
  const saved = localStorage.getItem('ai_quota_settings');
  if (saved) {
    try {
      settings = { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
    } catch (e) {
      console.warn("Failed to parse saved settings, using defaults.");
    }
  }
  
  // Populate UI fields
  elements.connectionModeSelect.value = settings.connectionMode;
  elements.localUrlInput.value = settings.localUrl;
  elements.cloudUrlInput.value = settings.cloudUrl;
  elements.refreshIntervalInput.value = settings.refreshInterval;
  elements.intervalDisplay.textContent = `${settings.refreshInterval}s`;
}

// Save settings to localStorage
function saveSettings() {
  settings.connectionMode = elements.connectionModeSelect.value;
  settings.localUrl = elements.localUrlInput.value.trim();
  settings.cloudUrl = elements.cloudUrlInput.value.trim();
  settings.refreshInterval = parseInt(elements.refreshIntervalInput.value);
  
  localStorage.setItem('ai_quota_settings', JSON.stringify(settings));
  hideSettings();
  setupPolling();
  fetchQuotaData();
}

// Update the circular SVG ring offset
function setProgress(circleElement, pctTextElement, value, max) {
  const radius = 50;
  const circumference = 2 * Math.PI * radius; // ~314.16
  
  // Default to 100% background if values are missing
  if (max <= 0 || value < 0) {
    circleElement.style.strokeDashoffset = circumference;
    pctTextElement.textContent = '--%';
    return;
  }
  
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
  const offset = circumference - (percentage / 100) * circumference;
  
  circleElement.style.strokeDashoffset = offset;
  pctTextElement.textContent = `${Math.round(percentage)}%`;
}

// Format seconds into readable clock formats
function formatTimer(totalSeconds) {
  if (totalSeconds <= 0) return '00:00:00';
  
  const hrs = Math.floor(totalSeconds / 3600).toString().padStart(2, '0');
  const mins = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, '0');
  const secs = (totalSeconds % 60).toString().padStart(2, '0');
  
  return `${hrs}h ${mins}m ${secs}s`;
}

// Real-time countdown updates
function startCountdownTimer() {
  if (countdownIntervalId) clearInterval(countdownIntervalId);
  
  countdownIntervalId = setInterval(() => {
    // Gemini Sprint Countdown
    if (geminiResetSeconds > 0) {
      geminiResetSeconds--;
      elements.geminiResetTimer.textContent = formatTimer(geminiResetSeconds);
    } else {
      elements.geminiResetTimer.textContent = '00h 00m 00s';
    }
    
    // Claude TPM Countdown
    if (claudeResetSeconds > 0) {
      claudeResetSeconds--;
      elements.claudeResetTimer.textContent = `${claudeResetSeconds}s`;
    } else {
      elements.claudeResetTimer.textContent = '0s';
    }
  }, 1000);
}

// Update UI state with connection badge
function updateConnectionBadge(state, text) {
  elements.connectionStatus.className = `status-badge ${state}`;
  elements.connectionStatus.querySelector('.status-text').textContent = text;
}

// --- DATA FETCHING & PARSING ---

async function fetchQuotaData() {
  updateConnectionBadge('warning', 'Syncing...');
  
  const endpointPath = '/api/quota';
  let data = null;
  let connectionSource = '';
  
  // Try local first if mode allows
  if (settings.connectionMode === 'hybrid' || settings.connectionMode === 'local') {
    try {
      const res = await fetch(`${settings.localUrl}${endpointPath}`, { signal: AbortSignal.timeout(4000) });
      if (res.ok) {
        data = await res.json();
        connectionSource = 'Local Bridge';
        elements.geminiEndpoint.textContent = settings.localUrl;
        elements.claudeEndpoint.textContent = settings.localUrl;
      }
    } catch (e) {
      console.warn("Local Bridge connection failed:", e.message);
      if (settings.connectionMode === 'local') {
        updateConnectionBadge('offline', 'Local Offline');
        return;
      }
    }
  }
  
  // Try Cloud fallbacks if data is still empty
  if (!data && (settings.connectionMode === 'hybrid' || settings.connectionMode === 'cloud')) {
    if (settings.cloudUrl) {
      try {
        const res = await fetch(`${settings.cloudUrl}${endpointPath}`, { signal: AbortSignal.timeout(6000) });
        if (res.ok) {
          data = await res.json();
          connectionSource = 'Cloud Proxy';
          elements.geminiEndpoint.textContent = settings.cloudUrl;
          elements.claudeEndpoint.textContent = settings.cloudUrl;
        }
      } catch (e) {
        console.error("Cloud Proxy connection failed:", e.message);
      }
    }
  }
  
  // If fetch failed completely, update UI to offline
  if (!data) {
    updateConnectionBadge('offline', 'Offline');
    return;
  }
  
  // Successfully loaded data
  updateConnectionBadge('online', connectionSource);
  renderDashboard(data);
}

// Format numbers nicely (e.g. 5,200,000 -> 5.2M)
function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  }
  return num;
}

// Render values onto Dashboard UI elements
function renderDashboard(data) {
  // 1. Render Google Gemini Data
  if (data.gemini) {
    const g = data.gemini;
    
    // Sprint limit (e.g. remaining availability)
    const sprintPct = g.sprintMax > 0 ? (g.sprintRemaining / g.sprintMax) : 0;
    setProgress(elements.geminiSprintRing, elements.geminiSprintPct, g.sprintRemaining, g.sprintMax);
    elements.geminiSprintUsage.textContent = `${formatNumber(g.sprintRemaining)} / ${formatNumber(g.sprintMax)} tokens`;
    
    // Weekly baseline limit
    setProgress(elements.geminiWeeklyRing, elements.geminiWeeklyPct, g.weeklyRemaining, g.weeklyMax);
    
    // Reset timers
    geminiResetSeconds = parseInt(g.resetSeconds) || 0;
    elements.geminiResetTimer.textContent = formatTimer(geminiResetSeconds);
    
    // Detailed stats
    elements.geminiTpm.textContent = `${formatNumber(g.tpmRemaining)} / ${formatNumber(g.tpmMax)}`;
    elements.geminiRpm.textContent = `${g.rpmRemaining} / ${g.rpmMax}`;
    elements.geminiCredits.textContent = g.balance || '$0.00 / Free Tier';
  }
  
  // 2. Render Anthropic Claude Data
  if (data.claude) {
    const c = data.claude;
    
    // TPM usage
    setProgress(elements.claudeTpmRing, elements.claudeTpmPct, c.tpmRemaining, c.tpmMax);
    elements.claudeTpmUsage.textContent = `${formatNumber(c.tpmRemaining)} / ${formatNumber(c.tpmMax)} tokens`;
    
    // Daily limits
    setProgress(elements.claudeDailyRing, elements.claudeDailyPct, c.dailyRemaining, c.dailyMax);
    
    // Reset timers
    claudeResetSeconds = parseInt(c.resetSeconds) || 0;
    elements.claudeResetTimer.textContent = `${claudeResetSeconds}s`;
    
    // Detailed stats
    elements.claudeRpm.textContent = `${c.rpmRemaining} / ${c.rpmMax}`;
    elements.claudeRpd.textContent = `${c.rpdRemaining} / ${c.rpdMax}`;
    elements.claudeCredits.textContent = c.balance || '$0.00';
  }
  
  startCountdownTimer();
}

// --- POLLING CONTROLS ---

function setupPolling() {
  if (activeIntervalId) clearInterval(activeIntervalId);
  
  const ms = settings.refreshInterval * 1000;
  activeIntervalId = setInterval(fetchQuotaData, ms);
}

// --- MODALS & DETAILS TOGGLES ---

function showSettings() {
  elements.settingsModal.classList.remove('hidden');
}

function hideSettings() {
  elements.settingsModal.classList.add('hidden');
}

function toggleDetails(panel) {
  panel.classList.toggle('hidden');
}

// --- EVENTS BINDING ---

function bindEvents() {
  elements.settingsToggle.addEventListener('click', showSettings);
  elements.settingsCancel.addEventListener('click', hideSettings);
  elements.settingsSave.addEventListener('click', saveSettings);
  elements.manualRefresh.addEventListener('click', fetchQuotaData);
  
  // Live range display
  elements.refreshIntervalInput.addEventListener('input', (e) => {
    elements.intervalDisplay.textContent = `${e.target.value}s`;
  });
  
  // Detail toggle buttons
  elements.geminiDetailsToggle.addEventListener('click', () => toggleDetails(elements.geminiDetailsPanel));
  elements.claudeDetailsToggle.addEventListener('click', () => toggleDetails(elements.claudeDetailsPanel));
  
  // Close modal when clicking outside content
  elements.settingsModal.addEventListener('click', (e) => {
    if (e.target === elements.settingsModal) {
      hideSettings();
    }
  });
}

// --- INITIALIZATION ---

document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  bindEvents();
  fetchQuotaData();
  setupPolling();
});
