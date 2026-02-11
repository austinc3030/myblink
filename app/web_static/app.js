// MyBlink Web Interface JavaScript

class MyBlinkApp {
    constructor() {
        this.state = { syncs: [], configured: false };
        this.config = {};
        this.theme = 'dark'; // Will be loaded from server config
        this.configured = false;
        
        this.init();
    }
    
    init() {
        // Apply saved theme
        this.applyTheme();
        
        // Setup event listeners
        document.getElementById('themeToggle').addEventListener('click', () => this.toggleTheme());
        document.getElementById('refreshBtn').addEventListener('click', () => this.refresh());
        document.getElementById('runJobsBtn').addEventListener('click', () => this.runJobs());
        document.getElementById('saveConfigBtn').addEventListener('click', () => this.saveConfig());
        document.getElementById('saveCredsBtn')?.addEventListener('click', () => this.saveCredentials());
        
        // Check setup status first
        this.checkSetupStatus();
        
        // Register service worker for PWA
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
            
            this.configured = status.configured;
            
            if (!this.configured) {
                this.showSetupWizard();
            } else {
                this.showMainInterface();
                this.loadData();
                // Auto-refresh every 30 seconds
                setInterval(() => this.loadData(), 30000);
            }
        } catch (error) {
            this.showError('Failed to check setup status: ' + error.message);
        }
    }
    
    showSetupWizard() {
        document.getElementById('setupWizard').classList.remove('hidden');
        document.getElementById('mainInterface').classList.add('hidden');
    }
    
    showMainInterface() {
        document.getElementById('setupWizard').classList.add('hidden');
        document.getElementById('mainInterface').classList.remove('hidden');
    }
    
    async saveCredentials() {
        const saveBtn = document.getElementById('saveCredsBtn');
        const status = document.getElementById('setupStatus');
        
        try {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            status.style.display = 'block';
            status.textContent = 'Saving credentials...';
            status.className = 'setup-status';
            
            // Get form values
            const credentials = {
                blink: {
                    username: document.getElementById('blinkUsername').value.trim(),
                    password: document.getElementById('blinkPassword').value,
                    cached_token: {}
                },
                voipms: {
                    username: document.getElementById('voipmsUsername').value.trim(),
                    password: document.getElementById('voipmsPassword').value,
                    did: document.getElementById('voipmsDid').value.trim()
                }
            };
            
            // Validate
            if (!credentials.blink.username || !credentials.blink.password) {
                throw new Error('Blink username and password are required');
            }
            if (!credentials.voipms.username || !credentials.voipms.password || !credentials.voipms.did) {
                throw new Error('All VoIP.ms fields are required');
            }
            
            // Save credentials
            const response = await fetch('/api/setup/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(credentials)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to save credentials');
            }
            
            status.textContent = 'Credentials saved! Starting Blink system...';
            
            // Start the system
            const startResponse = await fetch('/api/setup/start', {
                method: 'POST'
            });
            
            if (!startResponse.ok) {
                const error = await startResponse.json();
                throw new Error(error.error || 'Failed to start system');
            }
            
            status.textContent = 'Setup complete! Loading interface...';
            status.className = 'setup-status success';
            
            // Switch to main interface
            setTimeout(() => {
                this.configured = true;
                this.showMainInterface();
                this.loadData();
                // Auto-refresh every 30 seconds
                setInterval(() => this.loadData(), 30000);
            }, 1500);
            
        } catch (error) {
            status.textContent = 'Error: ' + error.message;
            status.className = 'setup-status error';
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save & Start';
        }
    }
    
    async loadData() {
        try {
            await Promise.all([
                this.loadState(),
                this.loadConfig()
            ]);
            this.render();
        } catch (error) {
            this.showError('Failed to load data: ' + error.message);
        }
    }
    
    async loadState() {
        const response = await fetch('/api/state');
        if (!response.ok) throw new Error('Failed to fetch state');
        this.state = await response.json();
    }
    
    async loadConfig() {
        const response = await fetch('/api/config');
        if (!response.ok) throw new Error('Failed to fetch config');
        this.config = await response.json();
        this.populateConfigForm();
    }
    
    populateConfigForm() {
        document.getElementById('scheduleInterval').value = this.config.schedule_interval_hours || 1;
        document.getElementById('retryLimit').value = this.config.blink_retry_limit || 3;
        document.getElementById('smsWait').value = this.config.voipms_sms_wait || 30;
        document.getElementById('themeSelect').value = this.config.theme || 'dark';
        
        // Apply theme from server config
        if (this.config.theme) {
            this.theme = this.config.theme;
            this.applyTheme();
        }
    }
    
    render() {
        const contentArea = document.getElementById('contentArea');
        const loadingArea = document.getElementById('loadingArea');
        
        if (!this.state.syncs || this.state.syncs.length === 0) {
            contentArea.innerHTML = '<div class="loading">No sync modules found. Click Refresh to load devices.</div>';
            contentArea.classList.remove('hidden');
            loadingArea.classList.add('hidden');
            return;
        }
        
        contentArea.innerHTML = this.state.syncs.map(sync => this.renderSync(sync)).join('');
        contentArea.classList.remove('hidden');
        loadingArea.classList.add('hidden');
    }
    
    renderSync(sync) {
        return `
            <div class="sync-module">
                <div class="sync-header">
                    <div class="sync-name">${this.escapeHtml(sync.name)}</div>
                    <div class="sync-toggles">
                        <div class="toggle-group">
                            <span class="toggle-label">Snooze</span>
                            <label class="toggle">
                                <input type="checkbox" 
                                       ${sync.snooze_enabled ? 'checked' : ''}
                                       onchange="app.toggleSync('${this.escapeHtml(sync.name)}', 'snooze', this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="toggle-group">
                            <span class="toggle-label">Arm</span>
                            <label class="toggle">
                                <input type="checkbox" 
                                       ${sync.arm_enabled ? 'checked' : ''}
                                       onchange="app.toggleSync('${this.escapeHtml(sync.name)}', 'arm', this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                    </div>
                </div>
                <div class="cameras-grid">
                    ${sync.cameras.map(camera => this.renderCamera(camera, sync.name)).join('')}
                </div>
            </div>
        `;
    }
    
    renderCamera(camera, syncName) {
        return `
            <div class="camera-card">
                <div class="camera-name">${this.escapeHtml(camera.name)}</div>
                <div class="camera-toggles">
                    <div class="toggle-group">
                        <span class="toggle-label">Snooze</span>
                        <label class="toggle">
                            <input type="checkbox" 
                                   ${camera.snooze_enabled ? 'checked' : ''}
                                   onchange="app.toggleCamera('${this.escapeHtml(camera.name)}', 'snooze', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="toggle-group">
                        <span class="toggle-label">Arm</span>
                        <label class="toggle">
                            <input type="checkbox" 
                                   ${camera.arm_enabled ? 'checked' : ''}
                                   onchange="app.toggleCamera('${this.escapeHtml(camera.name)}', 'arm', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div class="toggle-group">
                        <span class="toggle-label">Thumbnail</span>
                        <label class="toggle">
                            <input type="checkbox" 
                                   ${camera.thumbnail_enabled ? 'checked' : ''}
                                   onchange="app.toggleCamera('${this.escapeHtml(camera.name)}', 'thumbnail', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                </div>
            </div>
        `;
    }
    
    async toggleCamera(cameraName, setting, enabled) {
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/${setting}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            
            if (!response.ok) throw new Error('Failed to update camera setting');
            
            this.showSuccess(`Camera ${cameraName} ${setting} ${enabled ? 'enabled' : 'disabled'}`);
            await this.loadState();
            this.render();
        } catch (error) {
            this.showError('Failed to update camera: ' + error.message);
            // Reload to reset UI
            await this.loadData();
        }
    }
    
    async toggleSync(syncName, setting, enabled) {
        try {
            const response = await fetch(`/api/sync/${encodeURIComponent(syncName)}/${setting}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            
            if (!response.ok) throw new Error('Failed to update sync setting');
            
            this.showSuccess(`Sync ${syncName} ${setting} ${enabled ? 'enabled' : 'disabled'}`);
            await this.loadState();
            this.render();
        } catch (error) {
            this.showError('Failed to update sync: ' + error.message);
            // Reload to reset UI
            await this.loadData();
        }
    }
    
    async refresh() {
        const btn = document.getElementById('refreshBtn');
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
        
        try {
            const response = await fetch('/api/refresh', { method: 'POST' });
            if (!response.ok) throw new Error('Failed to refresh');
            
            this.showSuccess('Refreshed camera list');
            await this.loadData();
        } catch (error) {
            this.showError('Failed to refresh: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }
    }
    
    async runJobs() {
        const btn = document.getElementById('runJobsBtn');
        btn.disabled = true;
        btn.textContent = 'Running...';
        
        try {
            const response = await fetch('/api/run-jobs', { method: 'POST' });
            if (!response.ok) throw new Error('Failed to run jobs');
            
            this.showSuccess('Jobs completed successfully');
        } catch (error) {
            this.showError('Failed to run jobs: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Run Jobs';
        }
    }
    
    async saveConfig() {
        const btn = document.getElementById('saveConfigBtn');
        btn.disabled = true;
        btn.textContent = 'Saving...';
        
        try {
            const config = {
                schedule_interval_hours: parseInt(document.getElementById('scheduleInterval').value),
                blink_retry_limit: parseInt(document.getElementById('retryLimit').value),
                voipms_sms_wait: parseInt(document.getElementById('smsWait').value),
                theme: document.getElementById('themeSelect').value
            };
            
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            
            if (!response.ok) throw new Error('Failed to save config');
            
            this.showSuccess('Configuration saved successfully');
            await this.loadConfig();
            
            // Apply theme if changed
            this.theme = config.theme;
            this.applyTheme();
        } catch (error) {
            this.showError('Failed to save config: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Save Configuration';
        }
    }
    
    async toggleTheme() {
        this.theme = this.theme === 'light' ? 'dark' : 'light';
        
        // Save to server config
        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme: this.theme })
            });
        } catch (error) {
            console.error('Failed to save theme:', error);
        }
        
        // Update UI immediately
        this.applyTheme();
        document.getElementById('themeSelect').value = this.theme;
    }
    
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
        document.getElementById('themeIcon').textContent = this.theme === 'light' ? '🌙' : '☀️';
        
        // Update theme-color for mobile browsers
        const metaTheme = document.querySelector('meta[name="theme-color"]');
        if (metaTheme) {
            metaTheme.setAttribute('content', this.theme === 'light' ? '#2563eb' : '#1f2937');
        }
    }
    
    showError(message) {
        this.showMessage(message, 'error');
    }
    
    showSuccess(message) {
        this.showMessage(message, 'success');
    }
    
    showMessage(message, type) {
        const messageArea = document.getElementById('messageArea');
        const div = document.createElement('div');
        div.className = type;
        div.textContent = message;
        messageArea.appendChild(div);
        
        setTimeout(() => {
            div.remove();
        }, 5000);
    }
    
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
}

// Initialize app
const app = new MyBlinkApp();
