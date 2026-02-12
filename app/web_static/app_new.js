// MyBlink Web Interface - Tabbed Version

class MyBlinkApp {
    constructor() {
        this.state = { syncs: [], configured: false };
        this.config = {};
        this.theme = 'dark';
        this.activeTab = null;
        this.logPollingInterval = null;
        this.webLogs = [];
        this.blinkLogs = [];
        
        this.init();
    }
    
    init() {
        // Apply theme
        this.applyTheme();
        
        // Setup event listeners
        document.getElementById('themeToggle').addEventListener('click', () => this.toggleTheme());
        document.getElementById('refreshBtn').addEventListener('click', () => this.refresh());
        document.getElementById('runJobsBtn').addEventListener('click', () => this.runJobs());
        
        // Check setup and load data
        this.checkSetupStatus();
        
        // Register service worker
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js').catch((error) => {
                console.error('Service Worker registration failed:', error);
            });
        }
    }
    
    async checkSetupStatus() {
        try {
            const response = await fetch('/api/setup/status');
            if (!response.ok) throw new Error('Failed to check setup status');
            const status = await response.json();
            
            if (!status.configured) {
                this.showMessage('⚠️ Please configure credentials first. Check server logs for setup instructions.', 'error');
                return;
            }
            
            await this.loadData();
            this.renderTabs();
            this.showContent();
            
            // Auto-refresh every 30 seconds
            setInterval(() => this.loadData(), 30000);
            
        } catch (error) {
            this.showMessage('Failed to check setup status: ' + error.message, 'error');
        }
    }
    
    async loadData() {
        try {
            // Load state
            const stateResponse = await fetch('/api/state');
            if (!stateResponse.ok) throw new Error('Failed to load state');
            const newState = await stateResponse.json();
            
            // Check if syncs changed (need to re-render tabs)
            const syncsChanged = !this.state.syncs || 
                                 newState.syncs.length !== this.state.syncs.length ||
                                 JSON.stringify(newState.syncs.map(s => s.name)) !== 
                                 JSON.stringify(this.state.syncs.map(s => s.name));
            
            this.state = newState;
            
            // Load config
            const configResponse = await fetch('/api/config');
            if (!configResponse.ok) throw new Error('Failed to load config');
            this.config = await configResponse.json();
            
            // Update theme from config
            if (this.config.theme && this.config.theme !== this.theme) {
                this.theme = this.config.theme;
                this.applyTheme();
            }
            
            // Re-render tabs if syncs changed
            if (syncsChanged) {
                this.renderTabs();
            }
            // Otherwise just update active tab content
            else if (this.activeTab) {
                this.renderTabContent(this.activeTab);
            }
            
        } catch (error) {
            console.error('Failed to load data:', error);
            this.showMessage('Failed to load data: ' + error.message, 'error');
        }
    }
    
    renderTabs() {
        const tabsNav = document.getElementById('tabsNav');
        tabsNav.innerHTML = '';
        
        // Check if we have syncs
        if (!this.state.syncs || this.state.syncs.length === 0) {
            // No syncs yet - only show Settings and Logs tabs
            const settingsTab = document.createElement('button');
            settingsTab.className = 'tab active';
            settingsTab.textContent = '⚙️ Settings';
            settingsTab.dataset.tabId = 'settings';
            settingsTab.onclick = () => this.switchTab('settings');
            tabsNav.appendChild(settingsTab);
            
            const logsTab = document.createElement('button');
            logsTab.className = 'tab';
            logsTab.textContent = '📋 Logs';
            logsTab.dataset.tabId = 'logs';
            logsTab.onclick = () => this.switchTab('logs');
            tabsNav.appendChild(logsTab);
            
            // Default to settings tab
            this.activeTab = 'settings';
            this.renderTabContent(this.activeTab);
            return;
        }
        
        // Create tabs for each sync module
        this.state.syncs.forEach((sync, index) => {
            const tab = document.createElement('button');
            tab.className = 'tab' + (index === 0 ? ' active' : '');
            tab.textContent = sync.name;
            tab.dataset.tabId = `sync-${index}`;
            tab.onclick = () => this.switchTab(tab.dataset.tabId);
            tabsNav.appendChild(tab);
        });
        
        // Add Settings tab
        const settingsTab = document.createElement('button');
        settingsTab.className = 'tab';
        settingsTab.textContent = '⚙️ Settings';
        settingsTab.dataset.tabId = 'settings';
        settingsTab.onclick = () => this.switchTab('settings');
        tabsNav.appendChild(settingsTab);
        
        // Add Logs tab
        const logsTab = document.createElement('button');
        logsTab.className = 'tab';
        logsTab.textContent = '📋 Logs';
        logsTab.dataset.tabId = 'logs';
        logsTab.onclick = () => this.switchTab('logs');
        tabsNav.appendChild(logsTab);
        
        // Activate first tab
        this.activeTab = `sync-0`;
        this.renderTabContent(this.activeTab);
    }
    
    switchTab(tabId) {
        // Update tab buttons
        document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tabId === tabId);
        });
        
        this.activeTab = tabId;
        this.renderTabContent(tabId);
        
        // Start/stop log polling
        if (tabId === 'logs') {
            this.startLogPolling();
        } else {
            this.stopLogPolling();
        }
    }
    
    renderTabContent(tabId) {
        const contentArea = document.getElementById('tabsContent');
        
        // Guard against null tabId
        if (!tabId) {
            contentArea.innerHTML = '<div class="loading">No tab selected</div>';
            return;
        }
        
        if (tabId.startsWith('sync-')) {
            const index = parseInt(tabId.split('-')[1]);
            if (this.state.syncs && this.state.syncs[index]) {
                contentArea.innerHTML = this.renderSyncModule(this.state.syncs[index]);
            } else {
                contentArea.innerHTML = '<div class="loading">Sync module not found</div>';
            }
        } else if (tabId === 'settings') {
            contentArea.innerHTML = this.renderSettings();
            this.attachSettingsListeners();
        } else if (tabId === 'logs') {
            contentArea.innerHTML = this.renderLogs();
            this.attachLogListeners();
            this.loadLogs();
        }
    }
    
    renderSyncModule(sync) {
        return `
            <div class="tab-content active">
                <div class="sync-card">
                    <div class="sync-header">
                        <div class="sync-name">${sync.name}</div>
                        <div class="sync-toggles">
                            <div class="toggle-group">
                                <span class="toggle-label">Snooze</span>
                                <label class="toggle">
                                    <input type="checkbox" ${sync.snooze ? 'checked' : ''} 
                                           onchange="app.toggleSyncSnooze('${sync.name}', this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                            </div>
                            <div class="toggle-group">
                                <span class="toggle-label">Arm</span>
                                <label class="toggle">
                                    <input type="checkbox" ${sync.arm ? 'checked' : ''} 
                                           onchange="app.toggleSyncArm('${sync.name}', this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="cameras-grid">
                        ${sync.cameras.map(camera => this.renderCamera(camera)).join('')}
                    </div>
                </div>
            </div>
        `;
    }
    
    renderCamera(camera) {
        return `
            <div class="camera-card">
                <div class="camera-name">📷 ${camera.name}</div>
                <div class="camera-toggles">
                    <div class="toggle-group">
                        <span class="toggle-label">Snooze</span>
                        <label class="toggle">
                            <input type="checkbox" ${camera.snooze ? 'checked' : ''} 
                                   onchange="app.toggleCameraSnooze('${camera.name}', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="toggle-group">
                        <span class="toggle-label">Arm</span>
                        <label class="toggle">
                            <input type="checkbox" ${camera.arm ? 'checked' : ''} 
                                   onchange="app.toggleCameraArm('${camera.name}', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="toggle-group">
                        <span class="toggle-label">Thumbnail</span>
                        <label class="toggle">
                            <input type="checkbox" ${camera.thumbnail ? 'checked' : ''} 
                                   onchange="app.toggleCameraThumbnail('${camera.name}', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderSettings() {
        return `
            <div class="tab-content active">
                <div class="settings-section">
                    <div class="settings-title">⚙️ Application Settings</div>
                    <div class="settings-grid">
                        <div class="form-group">
                            <label class="form-label">Schedule Interval (hours)</label>
                            <input type="number" id="scheduleInterval" class="form-input" 
                                   value="${this.config.schedule_interval_hours || 1}" min="1" max="24">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Blink Retry Limit</label>
                            <input type="number" id="retryLimit" class="form-input" 
                                   value="${this.config.blink_retry_limit || 3}" min="1" max="10">
                        </div>
                        <div class="form-group">
                            <label class="form-label">SMS Wait Time (seconds)</label>
                            <input type="number" id="smsWait" class="form-input" 
                                   value="${this.config.voipms_sms_wait || 30}" min="10" max="120">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Theme</label>
                            <select id="themeSelect" class="form-select">
                                <option value="light" ${this.theme === 'light' ? 'selected' : ''}>Light</option>
                                <option value="dark" ${this.theme === 'dark' ? 'selected' : ''}>Dark</option>
                            </select>
                        </div>
                    </div>
                    <div style="margin-top: 1rem;">
                        <button class="btn" id="saveSettingsBtn">Save Settings</button>
                    </div>
                </div>
                
                <div class="settings-section">
                    <div class="settings-title">🔐 Credentials</div>
                    <div class="settings-grid">
                        <div class="form-group">
                            <label class="form-label">Blink Username</label>
                            <input type="email" id="blinkUsername" class="form-input" 
                                   value="${this.config.blink_username || ''}" placeholder="your@email.com">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Blink Password</label>
                            <input type="password" id="blinkPassword" class="form-input" 
                                   placeholder="Enter to change">
                        </div>
                        <div class="form-group">
                            <label class="form-label">VoIP.ms Username</label>
                            <input type="text" id="voipmsUsername" class="form-input" 
                                   value="${this.config.voipms_username || ''}" placeholder="api@email.com">
                        </div>
                        <div class="form-group">
                            <label class="form-label">VoIP.ms Password</label>
                            <input type="password" id="voipmsPassword" class="form-input" 
                                   placeholder="Enter to change">
                        </div>
                        <div class="form-group">
                            <label class="form-label">VoIP.ms DID</label>
                            <input type="text" id="voipmsDid" class="form-input" 
                                   value="${this.config.voipms_did || ''}" placeholder="5551234567">
                        </div>
                    </div>
                    <div style="margin-top: 1rem;">
                        <button class="btn" id="saveCredentialsBtn">Update Credentials</button>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderLogs() {
        return `
            <div class="tab-content active">
                <div class="log-controls">
                    <button class="btn btn-secondary" id="showWebLogs">Web Logs</button>
                    <button class="btn btn-secondary active" id="showBlinkLogs">Blink Logs</button>
                    <button class="btn btn-secondary" id="clearLogs">Clear</button>
                    <button class="btn btn-secondary" id="refreshLogs">Refresh</button>
                </div>
                <div class="log-container" id="logContainer">
                    <div class="loading">Loading logs...</div>
                </div>
            </div>
        `;
    }
    
    attachSettingsListeners() {
        document.getElementById('saveSettingsBtn')?.addEventListener('click', () => this.saveSettings());
        document.getElementById('saveCredentialsBtn')?.addEventListener('click', () => this.saveCredentials());
    }
    
    attachLogListeners() {
        document.getElementById('showWebLogs')?.addEventListener('click', (e) => {
            document.querySelectorAll('.log-controls .btn-secondary').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            this.displayLogs('web');
        });
        document.getElementById('showBlinkLogs')?.addEventListener('click', (e) => {
            document.querySelectorAll('.log-controls .btn-secondary').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            this.displayLogs('blink');
        });
        document.getElementById('clearLogs')?.addEventListener('click', () => this.clearLogs());
        document.getElementById('refreshLogs')?.addEventListener('click', () => this.loadLogs());
    }
    
    async loadLogs() {
        try {
            const response = await fetch('/api/logs');
            if (!response.ok) throw new Error('Failed to load logs');
            const logs = await response.json();
            
            this.webLogs = logs.web_logs || [];
            this.blinkLogs = logs.blink_logs || [];
            
            // Display currently active log type
            const activeBtn = document.querySelector('.log-controls .btn-secondary.active');
            if (activeBtn?.id === 'showWebLogs') {
                this.displayLogs('web');
            } else {
                this.displayLogs('blink');
            }
        } catch (error) {
            this.showMessage('Failed to load logs: ' + error.message, 'error');
        }
    }
    
    displayLogs(type) {
        const container = document.getElementById('logContainer');
        const logs = type === 'web' ? this.webLogs : this.blinkLogs;
        
        if (logs.length === 0) {
            container.innerHTML = '<div class="loading">No logs available</div>';
            return;
        }
        
        container.innerHTML = logs.map(log => {
            const level = log.level?.toLowerCase() || 'info';
            return `<div class="log-entry ${level}">${this.escapeHtml(log.message)}</div>`;
        }).join('');
        
        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    }
    
    async clearLogs() {
        try {
            const response = await fetch('/api/logs/clear', { method: 'POST' });
            if (!response.ok) throw new Error('Failed to clear logs');
            
            this.webLogs = [];
            this.blinkLogs = [];
            document.getElementById('logContainer').innerHTML = '<div class="loading">Logs cleared</div>';
            this.showMessage('Logs cleared successfully', 'success');
        } catch (error) {
            this.showMessage('Failed to clear logs: ' + error.message, 'error');
        }
    }
    
    startLogPolling() {
        if (this.logPollingInterval) return;
        this.loadLogs();
        this.logPollingInterval = setInterval(() => this.loadLogs(), 5000);
    }
    
    stopLogPolling() {
        if (this.logPollingInterval) {
            clearInterval(this.logPollingInterval);
            this.logPollingInterval = null;
        }
    }
    
    async saveSettings() {
        try {
            const settings = {
                schedule_interval_hours: parseInt(document.getElementById('scheduleInterval').value),
                blink_retry_limit: parseInt(document.getElementById('retryLimit').value),
                voipms_sms_wait: parseInt(document.getElementById('smsWait').value),
                theme: document.getElementById('themeSelect').value
            };
            
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            
            if (!response.ok) throw new Error('Failed to save settings');
            
            // Update theme if changed
            if (settings.theme !== this.theme) {
                this.theme = settings.theme;
                this.applyTheme();
            }
            
            this.showMessage('Settings saved successfully!', 'success');
            await this.loadData();
        } catch (error) {
            this.showMessage('Failed to save settings: ' + error.message, 'error');
        }
    }
    
    async saveCredentials() {
        try {
            const creds = {
                blink: {
                    username: document.getElementById('blinkUsername').value.trim(),
                    password: document.getElementById('blinkPassword').value || undefined
                },
                voipms: {
                    username: document.getElementById('voipmsUsername').value.trim(),
                    password: document.getElementById('voipmsPassword').value || undefined,
                    did: document.getElementById('voipmsDid').value.trim()
                }
            };
            
            // Remove undefined passwords (don't update if blank)
            if (!creds.blink.password) delete creds.blink.password;
            if (!creds.voipms.password) delete creds.voipms.password;
            
            const response = await fetch('/api/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(creds)
            });
            
            if (!response.ok) throw new Error('Failed to save credentials');
            
            this.showMessage('Credentials updated successfully!', 'success');
            // Clear password fields
            document.getElementById('blinkPassword').value = '';
            document.getElementById('voipmsPassword').value = '';
        } catch (error) {
            this.showMessage('Failed to save credentials: ' + error.message, 'error');
        }
    }
    
    // Camera/Sync toggle methods
    async toggleCameraSnooze(name, enabled) {
        await this.apiCall(`/api/camera/${encodeURIComponent(name)}/snooze`, { enabled });
    }
    
    async toggleCameraArm(name, enabled) {
        await this.apiCall(`/api/camera/${encodeURIComponent(name)}/arm`, { enabled });
    }
    
    async toggleCameraThumbnail(name, enabled) {
        await this.apiCall(`/api/camera/${encodeURIComponent(name)}/thumbnail`, { enabled });
    }
    
    async toggleSyncSnooze(name, enabled) {
        await this.apiCall(`/api/sync/${encodeURIComponent(name)}/snooze`, { enabled });
    }
    
    async toggleSyncArm(name, enabled) {
        await this.apiCall(`/api/sync/${encodeURIComponent(name)}/arm`, { enabled });
    }
    
    async apiCall(endpoint, data) {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error('API call failed');
            this.showMessage('Updated successfully', 'success');
        } catch (error) {
            this.showMessage('Update failed: ' + error.message, 'error');
        }
    }
    
    async refresh() {
        this.showMessage('Refreshing camera state...', 'info');
        try {
            const response = await fetch('/api/refresh', { method: 'POST' });
            if (!response.ok) throw new Error('Refresh failed');
            await this.loadData();
            this.renderTabContent(this.activeTab);
            this.showMessage('Refreshed successfully!', 'success');
        } catch (error) {
            this.showMessage('Refresh failed: ' + error.message, 'error');
        }
    }
    
    async runJobs() {
        this.showMessage('Running scheduled jobs...', 'info');
        try {
            const response = await fetch('/api/run-jobs', { method: 'POST' });
            if (!response.ok) throw new Error('Run jobs failed');
            this.showMessage('Jobs completed successfully!', 'success');
        } catch (error) {
            this.showMessage('Run jobs failed: ' + error.message, 'error');
        }
    }
    
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
        document.getElementById('themeIcon').textContent = this.theme === 'dark' ? '🌙' : '☀️';
    }
    
    toggleTheme() {
        this.theme = this.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme();
        // Save to server
        fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: this.theme })
        });
    }
    
    showContent() {
        document.getElementById('loadingArea').classList.add('hidden');
        document.getElementById('tabsContainer').classList.remove('hidden');
    }
    
    showMessage(message, type = 'info') {
        const area = document.getElementById('messageArea');
        area.innerHTML = `<div class="${type}">${message}</div>`;
        setTimeout(() => area.innerHTML = '', 5000);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize app
const app = new MyBlinkApp();
