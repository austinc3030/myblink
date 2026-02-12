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
        
        // Load night vision status for all cameras
        this.state.syncs.forEach(sync => {
            if (sync.cameras) {
                sync.cameras.forEach(camera => {
                    this.loadNightVisionStatus(camera.name);
                });
            }
        });
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
                <div class="camera-header">
                    <div class="camera-name">${this.escapeHtml(camera.name)}</div>
                    <button class="btn-icon" onclick="app.showCameraInfo('${this.escapeHtml(camera.name)}', '${this.escapeHtml(syncName)}')" title="Camera Info">
                        ℹ️
                    </button>
                </div>
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
                    <div class="camera-select-group">
                        <span class="toggle-label">Night Vision</span>
                        <select class="camera-select" id="nv_${this.escapeHtml(camera.name).replace(/[^a-zA-Z0-9]/g, '_')}" 
                                onchange="app.setNightVision('${this.escapeHtml(camera.name)}', this.value)">
                            <option value="">Loading...</option>
                        </select>
                    </div>
                </div>
                <div class="camera-actions">
                    <button class="btn-action" onclick="app.capturePhoto('${this.escapeHtml(camera.name)}')" title="Capture a new photo">
                        📸 Capture
                    </button>
                    <button class="btn-action" onclick="app.startRecording('${this.escapeHtml(camera.name)}')" title="Start video recording">
                        🎥 Record
                    </button>
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
    
    async loadNightVisionStatus(cameraName) {
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/night_vision`);
            if (!response.ok) return;
            
            const data = await response.json();
            const nv = data.night_vision;
            
            // Find the current mode
            let currentMode = 'auto';
            if (nv) {
                if (nv.illuminator_enable) currentMode = nv.illuminator_enable;
                else if (nv.night_vision_control) currentMode = nv.night_vision_control;
                else if (nv.illuminator_enable_v2) currentMode = nv.illuminator_enable_v2;
            }
            
            // Update the select element
            const selectId = `nv_${cameraName.replace(/[^a-zA-Z0-9]/g, '_')}`;
            const select = document.getElementById(selectId);
            if (select) {
                select.innerHTML = `
                    <option value="off" ${currentMode === 'off' ? 'selected' : ''}>Off</option>
                    <option value="on" ${currentMode === 'on' ? 'selected' : ''}>On</option>
                    <option value="auto" ${currentMode === 'auto' ? 'selected' : ''}>Auto</option>
                `;
            }
        } catch (error) {
            console.error(`Failed to load night vision status for ${cameraName}:`, error);
        }
    }
    
    async loadNightVisionStatusForModal(cameraName) {
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/night_vision`);
            if (!response.ok) return;
            
            const data = await response.json();
            const nv = data.night_vision;
            
            // Find the current mode
            let currentMode = 'auto';
            if (nv) {
                if (nv.illuminator_enable) currentMode = nv.illuminator_enable;
                else if (nv.night_vision_control) currentMode = nv.night_vision_control;
                else if (nv.illuminator_enable_v2) currentMode = nv.illuminator_enable_v2;
            }
            
            // Update the modal select element
            const selectId = `modal_nv_${cameraName.replace(/[^a-zA-Z0-9]/g, '_')}`;
            const select = document.getElementById(selectId);
            if (select) {
                select.innerHTML = `
                    <option value="off" ${currentMode === 'off' ? 'selected' : ''}>Off</option>
                    <option value="on" ${currentMode === 'on' ? 'selected' : ''}>On</option>
                    <option value="auto" ${currentMode === 'auto' ? 'selected' : ''}>Auto</option>
                `;
            }
        } catch (error) {
            console.error(`Failed to load night vision status for ${cameraName}:`, error);
        }
    }
    
    async setNightVision(cameraName, mode) {
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/night_vision`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode })
            });
            
            if (!response.ok) throw new Error('Failed to set night vision');
            
            this.showSuccess(`Night vision set to ${mode} for ${cameraName}`);
        } catch (error) {
            this.showError('Failed to set night vision: ' + error.message);
        }
    }
    
    async capturePhoto(cameraName) {
        try {
            const btn = event.target;
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '⏳ Capturing...';
            
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/media/thumbnail/new`, {
                method: 'POST'
            });
            
            if (!response.ok) throw new Error('Failed to capture photo');
            
            // Download the blob
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${cameraName}_${Date.now()}.jpg`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
            
            this.showSuccess(`Photo captured from ${cameraName}!`);
            
            btn.disabled = false;
            btn.innerHTML = originalText;
        } catch (error) {
            this.showError('Failed to capture photo: ' + error.message);
            if (event.target) {
                event.target.disabled = false;
                event.target.innerHTML = '📸 Capture';
            }
        }
    }
    
    async startRecording(cameraName) {
        try {
            const btn = event.target;
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '⏳ Recording...';
            
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/record`, {
                method: 'POST'
            });
            
            if (!response.ok) throw new Error('Failed to start recording');
            
            this.showSuccess(`Recording started on ${cameraName}! Video will be available in recent clips once complete.`);
            
            btn.disabled = false;
            btn.innerHTML = originalText;
        } catch (error) {
            this.showError('Failed to start recording: ' + error.message);
            if (event.target) {
                event.target.disabled = false;
                event.target.innerHTML = '🎥 Record';
            }
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
    
    async showCameraInfo(cameraName, syncName) {
        try {
            const modal = document.getElementById('cameraInfoModal');
            const modalTitle = document.getElementById('modalCameraName');
            const modalBody = document.getElementById('modalCameraInfo');
            
            // Show modal with loading state
            modalTitle.textContent = cameraName;
            modalBody.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">Loading camera information...</div>';
            modal.classList.add('active');
            
            // Fetch camera details
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/info`);
            if (!response.ok) throw new Error('Failed to fetch camera info');
            
            const info = await response.json();
            
            // Render camera information
            modalBody.innerHTML = this.renderCameraInfo(info, cameraName);
            
            // Load night vision status for modal selector
            await this.loadNightVisionStatusForModal(cameraName);
            
        } catch (error) {
            this.showError('Failed to load camera info: ' + error.message);
            this.closeCameraInfo();
        }
    }
    
    closeCameraInfo() {
        const modal = document.getElementById('cameraInfoModal');
        modal.classList.remove('active');
    }
    
    renderCameraInfo(info, cameraName) {
        const formatValue = (value) => {
            if (value === null || value === undefined || value === "N/A") return "N/A";
            if (typeof value === 'boolean') return value ? 'Yes' : 'No';
            if (Array.isArray(value)) return value.length > 0 ? `${value.length} items` : 'None';
            return value;
        };
        
        return `
            <div class="info-group">
                <div class="info-group-title">📸 Camera Details</div>
                <div class="info-item">
                    <span class="info-label">Camera ID</span>
                    <span class="info-value">${formatValue(info.camera_id)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Serial Number</span>
                    <span class="info-value">${formatValue(info.serial)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Type</span>
                    <span class="info-value">${formatValue(info.type)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Firmware Version</span>
                    <span class="info-value">${formatValue(info.version)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Network ID</span>
                    <span class="info-value">${formatValue(info.network_id)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Sync Module</span>
                    <span class="info-value">${formatValue(info.sync_module)}</span>
                </div>
            </div>
            
            <div class="info-group">
                <div class="info-group-title">📊 Status</div>
                <div class="info-item">
                    <span class="info-label">Motion Enabled</span>
                    <span class="info-value">${formatValue(info.motion_enabled)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Motion Detected</span>
                    <span class="info-value">${formatValue(info.motion_detected)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Battery Level</span>
                    <span class="info-value">${formatValue(info.battery_level)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Battery State</span>
                    <span class="info-value">${formatValue(info.battery)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Battery Voltage</span>
                    <span class="info-value">${info.battery_voltage !== "N/A" ? (info.battery_voltage / 100).toFixed(2) + 'V' : 'N/A'}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Temperature</span>
                    <span class="info-value">${info.temperature !== "N/A" ? info.temperature + '°F (' + info.temperature_c + '°C)' : 'N/A'}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">WiFi Strength</span>
                    <span class="info-value">${formatValue(info.wifi_strength)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Sync Signal Strength</span>
                    <span class="info-value">${formatValue(info.sync_signal_strength)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Last Record</span>
                    <span class="info-value">${formatValue(info.last_record)}</span>
                </div>
            </div>
            
            <div class="info-group">
                <div class="info-group-title">⚙️ Settings</div>
                <div class="info-item">
                    <span class="info-label">Night Vision</span>
                    <span class="info-value media-value">
                        <select class="camera-select" id="modal_nv_${this.escapeHtml(cameraName).replace(/[^a-zA-Z0-9]/g, '_')}" 
                                onchange="app.setNightVision('${this.escapeHtml(cameraName)}', this.value)">
                            <option value="">Loading...</option>
                        </select>
                    </span>
                </div>
            </div>
            
            <div class="info-group">
                <div class="info-group-title">📷 Media</div>
                <div class="info-item">
                    <span class="info-label">Cached Thumbnail</span>
                    <span class="info-value media-value">
                        ${info.has_cached_thumbnail ? 
                            `<button class="btn-small" onclick="app.downloadMedia('${this.escapeHtml(cameraName)}', 'thumbnail')">Download</button>` : 
                            'Not available'}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">New Thumbnail</span>
                    <span class="info-value media-value">
                        <button class="btn-small" onclick="app.captureAndDownloadThumbnail('${this.escapeHtml(cameraName)}')">Capture & Download</button>
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">Latest Video Clip</span>
                    <span class="info-value media-value">
                        ${info.has_cached_video ? 
                            `<button class="btn-small" onclick="app.downloadMedia('${this.escapeHtml(cameraName)}', 'clip')">Download</button>` : 
                            'Not available'}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">Recent Clips</span>
                    <span class="info-value media-value">
                        ${info.has_recent_clips ? 
                            `<button class="btn-small" onclick="app.viewRecentClips('${this.escapeHtml(cameraName)}')">View List</button>` : 
                            'None'}
                    </span>
                </div>
            </div>
        `;
    }
    
    async downloadMedia(cameraName, mediaType) {
        try {
            const url = `/api/camera/${encodeURIComponent(cameraName)}/media/${mediaType}`;
            
            // Create a temporary link and trigger download
            const link = document.createElement('a');
            link.href = url;
            link.download = `${cameraName}_${mediaType}_${Date.now()}.${mediaType === 'clip' ? 'mp4' : 'jpg'}`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            this.showSuccess(`Downloading ${mediaType}...`);
        } catch (error) {
            this.showError(`Failed to download ${mediaType}: ` + error.message);
        }
    }
    
    async captureAndDownloadThumbnail(cameraName) {
        try {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = 'Capturing...';
            
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/media/thumbnail/new`, {
                method: 'POST'
            });
            
            if (!response.ok) throw new Error('Failed to capture thumbnail');
            
            // Download the blob
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${cameraName}_thumbnail_${Date.now()}.jpg`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
            
            this.showSuccess('Thumbnail captured and downloaded!');
            
            btn.disabled = false;
            btn.textContent = 'Capture & Download';
        } catch (error) {
            this.showError('Failed to capture thumbnail: ' + error.message);
            event.target.disabled = false;
            event.target.textContent = 'Capture & Download';
        }
    }
    
    async viewRecentClips(cameraName) {
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/media/clips`);
            if (!response.ok) throw new Error('Failed to fetch recent clips');
            
            const data = await response.json();
            const clips = data.clips || [];
            
            if (clips.length === 0) {
                this.showError('No recent clips available');
                return;
            }
            
            // Display clips in modal
            const modalBody = document.getElementById('modalCameraInfo');
            modalBody.innerHTML = `
                <div class="info-group">
                    <div class="info-group-title">📹 Recent Clips (${clips.length})</div>
                    ${clips.map((clip, index) => {
                        const clipTime = new Date(clip.time);
                        const formattedTime = clipTime.toLocaleString();
                        const relativeTime = this.getRelativeTime(clipTime);
                        
                        return `
                            <div class="info-item">
                                <div style="display: flex; flex-direction: column; gap: 0.25rem;">
                                    <span class="info-label" style="font-weight: 600;">Clip ${index + 1}</span>
                                    <span style="font-size: 0.75rem; color: var(--text-secondary);">${formattedTime}</span>
                                    <span style="font-size: 0.75rem; color: var(--text-secondary);">${relativeTime}</span>
                                </div>
                                <button class="btn-small" onclick="app.downloadSpecificClip('${this.escapeHtml(cameraName)}', '${this.escapeHtml(clip.clip)}', ${index + 1})">Download</button>
                            </div>
                        `;
                    }).join('')}
                </div>
                <div style="margin-top: 1rem; text-align: center;">
                    <button class="btn-small" onclick="app.showCameraInfo('${this.escapeHtml(cameraName)}', '')">Back to Info</button>
                </div>
            `;
        } catch (error) {
            this.showError('Failed to load recent clips: ' + error.message);
        }
    }
    
    getRelativeTime(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
        return date.toLocaleDateString();
    }
    
    async downloadSpecificClip(cameraName, clipUrl, clipNumber) {
        try {
            const btn = event.target;
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Downloading...';
            
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/media/clip/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clip_url: clipUrl })
            });
            
            if (!response.ok) throw new Error('Failed to download clip');
            
            // Download the blob
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${cameraName}_clip_${clipNumber}_${Date.now()}.mp4`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
            
            this.showSuccess(`Clip ${clipNumber} downloaded!`);
            
            btn.disabled = false;
            btn.textContent = originalText;
        } catch (error) {
            this.showError('Failed to download clip: ' + error.message);
            if (event.target) {
                event.target.disabled = false;
                event.target.textContent = 'Download';
            }
        }
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
