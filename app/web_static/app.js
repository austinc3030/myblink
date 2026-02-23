// MyBlink Web Interface

class MyBlinkApp {
    constructor() {
        this.state = { syncs: [], configured: false };
        this.config = {};
        this.theme = 'dark';
        this.currentPage = 'main';
        this.logPollingInterval = null;
        this.webLogs = [];
        this.blinkLogs = [];
        this.thumbnailCache = new Map(); // In-memory cache
        
        // Tutorial mode
        this.tutorialMode = this.loadTutorialMode();
        
        // UI state will be loaded async in init
        this.uiState = {
            collapsedSyncs: {},
            syncOrder: [],
            cameraOrder: {}
        };
        
        this.init();
    }
    
    loadTutorialMode() {
        try {
            const saved = localStorage.getItem('myblink_tutorial_mode');
            return saved === null ? true : saved === 'true'; // Default to true for first-time users
        } catch (e) {
            return true;
        }
    }
    
    saveTutorialMode(enabled) {
        try {
            localStorage.setItem('myblink_tutorial_mode', enabled.toString());
            this.tutorialMode = enabled;
        } catch (e) {
            console.warn('Failed to save tutorial mode:', e);
        }
    }
    
    toggleTutorialMode() {
        this.saveTutorialMode(!this.tutorialMode);
        this.showMessage(`Tutorial mode ${this.tutorialMode ? 'enabled' : 'disabled'}`, 'success');
        // Re-render current page to show/hide tutorial tooltips
        if (this.currentPage === 'main') {
            this.renderMainPage();
        } else if (this.currentPage === 'settings') {
            this.renderSettingsPage();
        } else if (this.currentPage === 'schedules') {
            this.renderSchedulesPage();
        }
    }
    
    async loadUIState() {
        try {
            const response = await fetch('/api/ui_state');
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.error('Failed to load UI state:', error);
        }
        return {
            collapsedSyncs: {},
            syncOrder: [],
            cameraOrder: {}
        };
    }
    
    async saveUIState() {
        try {
            await fetch('/api/ui_state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.uiState)
            });
        } catch (error) {
            console.error('Failed to save UI state:', error);
        }
    }
    
    async init() {
        // Apply theme
        this.applyTheme();
        
        // Load UI state from server
        this.uiState = await this.loadUIState();
        
        // Check setup and load data
        this.checkSetupStatus();
        
        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.header-menu')) {
                this.closeMenu();
            }
        });
        
        // Handle browser back/forward buttons
        window.addEventListener('popstate', (e) => {
            const page = e.state?.page || 'main';
            this.showPage(page, false); // Don't push state again
        });
        
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
                this.showMessage('Please configure credentials first. Check server logs for setup instructions.', 'error');
                return;
            }
            
            await this.loadData();
            
            // Check if there's a hash in the URL for initial page
            const hash = window.location.hash.substring(1);
            const initialPage = hash || 'main';
            
            // Set initial history state
            window.history.replaceState({ page: initialPage }, '', window.location.href);
            
            this.renderMainPage();
            this.showPage(initialPage, false); // Don't push state on initial load
            
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
            
            // Check if not configured
            if (newState.configured === false) {
                // App not configured yet, show message and redirect
                this.showMessage('System not configured. Redirecting to configuration...', 'info');
                setTimeout(() => window.location.href = '/configure', 1500);
                return;
            }
            
            // Ensure syncs array exists
            if (!newState.syncs) {
                newState.syncs = [];
            }
            
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
            
            // Re-render current page
            if (this.currentPage === 'main') {
                this.renderMainPage();
            } else if (this.currentPage === 'settings') {
                this.renderSettingsPage();
            } else if (this.currentPage === 'logs') {
                this.renderLogsPage();
            }
            
        } catch (error) {
            console.error('Failed to load data:', error);
            this.showMessage('Failed to load data: ' + error.message, 'error');
        }
    }
    
    async refreshData() {
        const refreshBtn = document.getElementById('refreshBtn');
        if (!refreshBtn) return;
        
        // Disable button and add spinning animation
        refreshBtn.disabled = true;
        refreshBtn.classList.add('refreshing');
        
        try {
            this.showMessage('Refreshing data from Blink servers...', 'info');
            
            // Call the refresh endpoint
            const response = await fetch('/api/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Refresh failed');
            }
            
            const result = await response.json();
            this.showMessage(result.message || 'Refresh completed successfully', 'success');
            
            // Reload data after refresh
            await this.loadData();
            
        } catch (error) {
            console.error('Failed to refresh:', error);
            this.showMessage('Failed to refresh: ' + error.message, 'error');
        } finally {
            // Re-enable button and remove spinning animation
            refreshBtn.disabled = false;
            refreshBtn.classList.remove('refreshing');
        }
    }
    
    // Page navigation
    toggleMenu() {
        const menu = document.getElementById('dropdownMenu');
        menu.classList.toggle('show');
    }
    
    closeMenu() {
        const menu = document.getElementById('dropdownMenu');
        menu.classList.remove('show');
    }
    
    showPage(pageName, pushState = true) {
        this.closeMenu();
        
        // Stop log polling if leaving logs page
        if (this.currentPage === 'logs') {
            this.stopLogPolling();
        }
        
        this.currentPage = pageName;
        
        // Update browser history
        if (pushState) {
            const url = pageName === 'main' ? '/' : `/#${pageName}`;
            window.history.pushState({ page: pageName }, '', url);
        }
        
        // Hide loading area
        document.getElementById('loadingArea').classList.add('hidden');
        
        // Hide all pages
        document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
        
        // Show requested page
        const pageElement = document.getElementById(`${pageName}Page`);
        if (pageElement) {
            pageElement.classList.add('active');
        }
        
        // Render page content
        if (pageName === 'main') {
            this.renderMainPage();
        } else if (pageName === 'settings') {
            this.renderSettingsPage();
        } else if (pageName === 'logs') {
            this.renderLogsPage();
            this.startLogPolling();
        } else if (pageName === 'schedules') {
            this.renderSchedulesPage();
        }
    }
    
    toggleSyncCollapse(syncName) {
        const card = document.querySelector(`.sync-card[data-sync-name="${this.escapeHtml(syncName)}"]`);
        if (card) {
            const isCollapsed = card.classList.toggle('collapsed');
            
            // Save collapsed state
            this.uiState.collapsedSyncs[syncName] = isCollapsed;
            this.saveUIState();
        }
    }
    
    renderMainPage() {
        const container = document.getElementById('syncModules');
        
        if (!this.state.syncs || this.state.syncs.length === 0) {
            container.innerHTML = `
                <div class="sync-card" style="text-align: center; padding: 3rem;">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">📷</div>
                    <h2 style="margin-bottom: 1rem;">No cameras detected</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">
                        If you just configured your credentials, it may take a moment to connect to Blink.
                    </p>
                </div>
            `;
            return;
        }
        
        // Apply custom order if exists, otherwise use server order
        const orderedSyncs = this.applyCustomOrder(this.state.syncs);
        
        container.innerHTML = orderedSyncs.map(sync => this.renderSyncModule(sync)).join('');
        
        // Apply collapsed states after rendering
        this.applyCollapsedStates();
        
        // Fetch thumbnails for all cameras
        this.fetchAllThumbnails();
        
        // Setup drag-and-drop for sync cards
        this.setupSyncDragDrop();
    }
    
    applyCustomOrder(syncs) {
        // If we have saved order, use it
        if (this.uiState.syncOrder.length > 0) {
            const ordered = [];
            const syncMap = new Map(syncs.map(s => [s.name, s]));
            
            // Add syncs in saved order
            for (const syncName of this.uiState.syncOrder) {
                if (syncMap.has(syncName)) {
                    const sync = syncMap.get(syncName);
                    
                    // Apply camera order if exists
                    if (this.uiState.cameraOrder[syncName]) {
                        sync.cameras = this.applyCustomCameraOrder(sync.cameras, syncName);
                    }
                    
                    ordered.push(sync);
                    syncMap.delete(syncName);
                }
            }
            
            // Add any new syncs that weren't in saved order
            for (const sync of syncMap.values()) {
                ordered.push(sync);
            }
            
            return ordered;
        }
        
        // No saved order, use as-is but still apply camera orders
        return syncs.map(sync => {
            if (this.uiState.cameraOrder[sync.name]) {
                sync.cameras = this.applyCustomCameraOrder(sync.cameras, sync.name);
            }
            return sync;
        });
    }
    
    applyCustomCameraOrder(cameras, syncName) {
        const order = this.uiState.cameraOrder[syncName];
        if (!order || order.length === 0) return cameras;
        
        const ordered = [];
        const cameraMap = new Map(cameras.map(c => [c.name, c]));
        
        // Add cameras in saved order
        for (const cameraName of order) {
            if (cameraMap.has(cameraName)) {
                ordered.push(cameraMap.get(cameraName));
                cameraMap.delete(cameraName);
            }
        }
        
        // Add any new cameras
        for (const camera of cameraMap.values()) {
            ordered.push(camera);
        }
        
        return ordered;
    }
    
    applyCollapsedStates() {
        for (const [syncName, isCollapsed] of Object.entries(this.uiState.collapsedSyncs)) {
            if (isCollapsed) {
                const card = document.querySelector(`.sync-card[data-sync-name="${this.escapeHtml(syncName)}"]`);
                if (card) {
                    card.classList.add('collapsed');
                }
            }
        }
    }
    
    renderSyncModule(sync) {        
        return `
            <div class="sync-card" data-sync-name="${this.escapeHtml(sync.name)}" draggable="true" title="Sync Module: ${this.escapeHtml(sync.name)}">
                <div class="sync-header" onclick="app.toggleSyncCollapse('${this.escapeHtml(sync.name)}')" style="cursor: pointer;" title="Click to expand/collapse cameras">
                    <div class="sync-header-left">
                        <span class="drag-handle" onclick="event.stopPropagation();" title="Drag to reorder sync modules">⋮⋮</span>
                        <span class="sync-chevron" title="Expand/Collapse">▼</span>
                        <div class="sync-name">
                            ${sync.name}
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.75rem; align-items: center;">
                        <button class="btn-icon btn-secondary" onclick="event.stopPropagation(); app.showSyncModal('${this.escapeHtml(sync.name)}');" title="Sync module settings and controls">
                            <svg class="icon"><use href="#icon-settings"/></svg>
                        </button>
                    </div>
                </div>
                
                <div class="cameras-container">
                    <div class="cameras-grid" data-sync-name="${this.escapeHtml(sync.name)}">
                        ${sync.cameras.map(camera => this.renderCamera(camera, sync.name)).join('')}
                    </div>
                </div>
            </div>
        `;
    }
    
    renderCamera(camera, syncName) {
        const cameraNameEscaped = this.escapeHtml(camera.name);
        const syncNameEscaped = this.escapeHtml(syncName);
        
        // Get cached thumbnail or show loading state
        const cachedThumbnail = this.getThumbnailFromCache(camera.name);
        let thumbnailHtml = '';
        
        if (cachedThumbnail) {
            thumbnailHtml = `<img src="${cachedThumbnail}" alt="${cameraNameEscaped}">`;
        } else {
            thumbnailHtml = '<div class="no-thumbnail"><svg class="icon-xl"><use href="#icon-camera"/></svg></div>';
        }
        
        return `
            <div class="camera-card" data-camera-name="${cameraNameEscaped}" draggable="true" onclick="app.showCameraModal('${cameraNameEscaped}', '${syncNameEscaped}')" title="Camera: ${this.escapeHtml(camera.name)} - Click for details and controls">
                <div class="camera-header">
                    <span class="drag-handle-small" title="Drag to reorder cameras within this sync module" onclick="event.stopPropagation()">⋮⋮</span>
                    <div class="camera-name" style="flex: 1;">
                        <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
                            <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${camera.name}</span>
                        </div>
                    </div>
                </div>
                <div class="camera-thumbnail" data-camera="${cameraNameEscaped}" title="Last captured thumbnail">
                    ${thumbnailHtml}
                </div>
            </div>
        `;
    }
    
    setupSyncDragDrop() {
        const syncCards = document.querySelectorAll('.sync-card[draggable="true"]');
        
        syncCards.forEach(card => {
            card.addEventListener('dragstart', (e) => {
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', card.dataset.syncName);
                card.classList.add('dragging');
            });
            
            card.addEventListener('dragend', (e) => {
                card.classList.remove('dragging');
            });
            
            card.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                
                const dragging = document.querySelector('.sync-card.dragging');
                if (!dragging || dragging === card) return;
                
                const container = card.parentNode;
                const allCards = [...container.querySelectorAll('.sync-card[draggable="true"]')];
                const draggingIndex = allCards.indexOf(dragging);
                const currentIndex = allCards.indexOf(card);
                
                if (draggingIndex < currentIndex) {
                    card.parentNode.insertBefore(dragging, card.nextSibling);
                } else {
                    card.parentNode.insertBefore(dragging, card);
                }
            });
            
            card.addEventListener('drop', (e) => {
                e.preventDefault();
                this.saveSyncOrder();
            });
            
            // Setup drag-and-drop for cameras within this sync
            this.setupCameraDragDrop(card);
        });
    }
    
    setupCameraDragDrop(syncCard) {
        const syncName = syncCard.dataset.syncName;
        const cameraCards = syncCard.querySelectorAll('.camera-card[draggable="true"]');
        
        cameraCards.forEach(card => {
            card.addEventListener('dragstart', (e) => {
                e.stopPropagation(); // Don't trigger sync card drag
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', card.dataset.cameraName);
                card.classList.add('dragging');
            });
            
            card.addEventListener('dragend', (e) => {
                card.classList.remove('dragging');
            });
            
            card.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.stopPropagation();
                e.dataTransfer.dropEffect = 'move';
                
                const dragging = document.querySelector('.camera-card.dragging');
                if (!dragging || dragging === card) return;
                
                // Only allow reordering within same sync module
                if (dragging.parentNode !== card.parentNode) return;
                
                const container = card.parentNode;
                const allCards = [...container.querySelectorAll('.camera-card[draggable="true"]')];
                const draggingIndex = allCards.indexOf(dragging);
                const currentIndex = allCards.indexOf(card);
                
                if (draggingIndex < currentIndex) {
                    card.parentNode.insertBefore(dragging, card.nextSibling);
                } else {
                    card.parentNode.insertBefore(dragging, card);
                }
            });
            
            card.addEventListener('drop', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.saveCameraOrder(syncName);
            });
        });
    }
    
    saveSyncOrder() {
        const syncCards = document.querySelectorAll('.sync-card[draggable="true"]');
        this.uiState.syncOrder = Array.from(syncCards).map(card => card.dataset.syncName);
        this.saveUIState();
        this.showMessage('Sync order saved', 'success');
    }
    
    saveCameraOrder(syncName) {
        const grid = document.querySelector(`.cameras-grid[data-sync-name="${this.escapeHtml(syncName)}"]`);
        if (grid) {
            const cameraCards = grid.querySelectorAll('.camera-card[draggable="true"]');
            this.uiState.cameraOrder[syncName] = Array.from(cameraCards).map(card => card.dataset.cameraName);
            this.saveUIState();
            this.showMessage('Camera order saved', 'success');
        }
    }
    
    renderSettingsPage() {
        const container = document.getElementById('settingsPage');
        
        const noCamerasNotice = (!this.state.syncs || this.state.syncs.length === 0) ? `
            <div class="settings-section" style="background: rgba(37, 99, 235, 0.1); border-left: 4px solid var(--primary);">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-camera"/></svg>Cameras</div>
                <p style="color: var(--text-secondary); margin-bottom: 1rem;">
                    No cameras detected yet. If you just configured your credentials, it may take a moment to connect to Blink.
                </p>
            </div>
        ` : '';
        
        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <h2 style="font-size: 1.5rem; font-weight: 600;"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-settings"/></svg>Settings</h2>
                <button class="btn btn-secondary" onclick="app.showPage('main')">← Back to Home</button>
            </div>
            
            ${noCamerasNotice}
            
            <div class="settings-section">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-theme"/></svg>Appearance</div>
                <div class="settings-grid">
                    <div class="form-group">
                        <label class="form-label">Theme</label>
                        <select id="themeSelect" class="form-select">
                            <option value="light" ${this.theme === 'light' ? 'selected' : ''}>Light</option>
                            <option value="dark" ${this.theme === 'dark' ? 'selected' : ''}>Dark</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Time Format</label>
                        <select id="timeFormatSelect" class="form-select">
                            <option value="12h" ${(this.config.web_time_format || '12h') === '12h' ? 'selected' : ''}>12 Hour (AM/PM)</option>
                            <option value="24h" ${this.config.web_time_format === '24h' ? 'selected' : ''}>24 Hour</option>
                        </select>
                    </div>
                </div>
                <div style="margin-top: 1rem;">
                    <button class="btn" id="saveAppearanceBtn" title="Save theme and time format preferences">Save Appearance</button>
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-lock"/></svg>Credentials</div>
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
                    <button class="btn" id="saveCredentialsBtn" title="Update Blink and VoIP.ms credentials">Update Credentials</button>
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-settings"/></svg>System Parameters</div>
                <div class="settings-grid">
                    <div class="form-group">
                        <label class="form-label" title="How often the system refreshes data from Blink servers">Refresh Interval (Minutes)</label>
                        <input type="number" id="refreshInterval" class="form-input" 
                               value="${Math.floor((this.config.refresh_interval || 300) / 60)}" min="1" max="60" 
                               title="Minutes between automatic data refreshes (1-60)">
                        <small style="color: var(--text-secondary);">How often to fetch updates from Blink (default: 5 minutes)</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label" title="Default duration for temporary arm/snooze actions">Default Action Duration (Hours)</label>
                        <input type="number" id="defaultDuration" class="form-input" 
                               value="${this.config.default_duration_hours || 2}" min="0.5" max="24" step="0.5" 
                               title="Default hours for arm/snooze duration (0.5-24)">
                        <small style="color: var(--text-secondary);">Default hours for temporary arm/snooze (default: 2 hours)</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label" title="Maximum number of retries for failed API calls">API Retry Limit</label>
                        <input type="number" id="retryLimit" class="form-input" 
                               value="${this.config.blink_retry_limit || 3}" min="1" max="10" 
                               title="Maximum API retry attempts (1-10)">
                        <small style="color: var(--text-secondary);">How many times to retry failed operations (default: 3)</small>
                    </div>
                </div>
                <div style="margin-top: 1rem;">
                    <button class="btn" id="saveSystemParamsBtn" title="Save system parameters">Save Parameters</button>
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title">� Media Download & Archival</div>
                <div id="mediaDownloadSettings">
                    <p style="color: var(--text-secondary); margin-bottom: 1rem;">Loading media settings...</p>
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title">📡 BlinkBridge RTSP Streaming</div>
                <div id="blinkBridgeSettings">
                    <p style="color: var(--text-secondary); margin-bottom: 1rem;">Loading BlinkBridge settings...</p>
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-tools"/></svg>Actions</div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button class="btn" onclick="app.refresh()" title="Reload camera state from server"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-refresh"/></svg>Refresh State</button>
                    <button class="btn btn-secondary" onclick="app.runJobs()" title="Manually trigger scheduled jobs (thumbnails, arm/snooze, etc)">Run Jobs</button>
                    <button class="btn btn-secondary" onclick="app.showPage('logs')" title="View system logs"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-clipboard"/></svg>View Logs</button>
                </div>
            </div>
            
            <div class="settings-section" style="border-left: 4px solid #ef4444;">
                <div class="settings-title" style="color: #ef4444;"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-warning"/></svg>Danger Zone</div>
                <p style="color: var(--text-secondary); margin-bottom: 1rem; font-size: 0.9rem;">
                    Resetting the system will delete all data including saved clips, thumbnails, credentials, and configuration. This action cannot be undone.
                </p>
                <button class="btn" style="background: #ef4444;" onclick="app.confirmReset()"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-trash"/></svg>Reset System</button>
            </div>
        `;
        
        // Attach event listeners
        document.getElementById('saveAppearanceBtn')?.addEventListener('click', () => this.saveAppearance());
        document.getElementById('saveCredentialsBtn')?.addEventListener('click', () => this.saveCredentials());
        document.getElementById('saveSystemParamsBtn')?.addEventListener('click', () => this.saveSystemParams());
        
        // Load media download settings
        this.loadMediaSettings();
        
        // Load BlinkBridge settings
        this.loadBlinkBridgeSettings();
    }
    
    async saveSystemParams() {
        try {
            const refreshInterval = parseInt(document.getElementById('refreshInterval').value) * 60; // Convert to seconds
            const defaultDuration = parseFloat(document.getElementById('defaultDuration').value);
            const retryLimit = parseInt(document.getElementById('retryLimit').value);
            
            const response = await fetch('/api/system/params', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    refresh_interval: refreshInterval,
                    default_duration_hours: defaultDuration,
                    retry_limit: retryLimit
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to save parameters');
            }
            
            this.showMessage('System parameters saved successfully', 'success');
            await this.loadData(); // Reload config
        } catch (error) {
            this.showMessage('Failed to save parameters: ' + error.message, 'error');
        }
    }
    
    renderLogsPage() {
        const container = document.getElementById('logsPage');
        
        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <h2 style="font-size: 1.5rem; font-weight: 600;"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-clipboard"/></svg>Logs</h2>
                <button class="btn btn-secondary" onclick="app.showPage('settings')">← Back to Settings</button>
            </div>
            
            <div class="log-controls">
                <button class="btn btn-secondary" id="showWebLogs">Web Logs</button>
                <button class="btn btn-secondary active" id="showBlinkLogs">Blink Logs</button>
                <button class="btn btn-secondary" id="clearLogs">Clear</button>
                <button class="btn btn-secondary" id="refreshLogs">Refresh</button>
            </div>
            <div class="log-container" id="logContainer">
                <div class="loading">Loading logs...</div>
            </div>
        `;
        
        // Attach event listeners
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
        
        // Load logs
        this.loadLogs();
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
    
    renderSchedulesPage() {
        const container = document.getElementById('schedulesPage');
        
        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <h2 style="font-size: 1.5rem; font-weight: 600;"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-calendar"/></svg>Schedules</h2>
                <button class="btn btn-secondary" onclick="app.showPage('main')">← Back to Home</button>
            </div>
            
            <div class="settings-section">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-plus"/></svg>Create Schedule</div>
                <form id="scheduleForm">
                    <div class="settings-grid">
                        <div class="form-group">
                            <label class="form-label">Schedule Name</label>
                            <input type="text" id="scheduleName" class="form-input" 
                                   placeholder="e.g., Barn Driveway Motion" required>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">What to Control</label>
                            <select id="scheduleTarget" class="form-select" required>
                                <option value="">Select a target...</option>
                                <optgroup label="Cameras">
                                    ${this.getCameraOptions()}
                                </optgroup>
                                <optgroup label="Sync Modules">
                                    ${this.getSyncOptions()}
                                </optgroup>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Action</label>
                            <select id="scheduleAction" class="form-select" required>
                                <option value="">Select an action...</option>
                                <option value="camera_motion_enable">Unsnooze Camera (Enable Motion)</option>
                                <option value="camera_motion_disable">Snooze Camera (Disable Motion)</option>
                                <option value="camera_thumbnail">Capture Thumbnail</option>
                                <option value="sync_arm">Arm Sync Module</option>
                                <option value="sync_disarm">Disarm Sync Module</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Run Every</label>
                            <div style="display: flex; gap: 0.5rem;">
                                <input type="number" id="scheduleIntervalHours" class="form-input" 
                                       placeholder="Hours" min="0" max="24" value="0" style="width: 50%;">
                                <input type="number" id="scheduleIntervalMinutes" class="form-input" 
                                       placeholder="Minutes" min="0" max="59" value="60" style="width: 50%;">
                            </div>
                            <small style="color: var(--text-secondary);">e.g., "4 hours 0 minutes" or "0 hours 30 minutes"</small>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Start At Minute (Optional)</label>
                            <input type="number" id="scheduleStartMinute" class="form-input" 
                                   placeholder="0-59" min="0" max="59">
                            <small style="color: var(--text-secondary);">Run at specific minute (e.g., 27 for ":27 past each hour")</small>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Duration (Hours, Optional)</label>
                            <input type="number" id="scheduleDuration" class="form-input" 
                                   placeholder="How long to keep active" min="0" max="24" step="0.5">
                            <small style="color: var(--text-secondary);">For enable/arm actions, how long before auto-disable</small>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Active Time Window (Optional)</label>
                            <div style="display: flex; gap: 0.5rem;">
                                <input type="time" id="scheduleStartTime" class="form-input" style="width: 50%;">
                                <input type="time" id="scheduleEndTime" class="form-input" style="width: 50%;">
                            </div>
                            <small style="color: var(--text-secondary);">Only run between these times</small>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Active Days (Optional)</label>
                            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem;">
                                <label style="display: flex; align-items: center; gap: 0.25rem; cursor: pointer;">
                                    <input type="checkbox" value="mon"> Mon
                                </label>
                                <label style="display: flex; align-items: center; gap: 0.25rem; cursor: pointer;">
                                    <input type="checkbox" value="tue"> Tue
                                </label>
                                <label style="display: flex; align-items: center; gap: 0.25rem; cursor: pointer;">
                                    <input type="checkbox" value="wed"> Wed
                                </label>
                                <label style="display: flex; align-items: center; gap: 0.25rem; cursor: pointer;">
                                    <input type="checkbox" value="thu"> Thu
                                </label>
                                <label style="display: flex; align-items: center; gap: 0.25rem; cursor: pointer;">
                                    <input type="checkbox" value="fri"> Fri
                                </label>
                                <label style="display: flex; align-items: center; gap: 0.25rem; cursor: pointer;">
                                    <input type="checkbox" value="sat"> Sat
                                </label>
                                <label style="display: flex; align-items: center; gap: 0.25rem; cursor: pointer;">
                                    <input type="checkbox" value="sun"> Sun
                                </label>
                            </div>
                            <small style="color: var(--text-secondary);">Leave unchecked to run every day</small>
                        </div>
                    </div>
                    
                    <div style="margin-top: 1rem; display: flex; gap: 0.5rem;">
                        <button type="submit" class="btn">Create Schedule</button>
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('scheduleForm').reset()">Clear</button>
                    </div>
                </form>
            </div>
            
            <div class="settings-section">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-clipboard"/></svg>Active Schedules</div>
                <div id="schedulesList">
                    <div class="loading">Loading schedules...</div>
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-edit"/></svg>Execution Log</div>
                <div style="margin-bottom: 1rem;">
                    <label class="form-label">Time Range</label>
                    <select id="executionLogTimeRange" class="form-select" onchange="app.loadExecutionLog()" style="max-width: 300px;">
                        <option value="24">Last 24 Hours</option>
                        <option value="168" selected>Last 7 Days</option>
                        <option value="720">Last 30 Days</option>
                    </select>
                </div>
                <div id="executionLogList">
                    <div class="loading">Loading execution log...</div>
                </div>
            </div>
        `;
        
        // Attach form submit handler
        document.getElementById('scheduleForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.createSchedule();
        });
        
        // Load existing schedules and execution log
        this.loadSchedules();
        this.loadExecutionLog();
    }
    
    getCameraOptions() {
        if (!this.state.syncs || this.state.syncs.length === 0) {
            return '<option disabled>No cameras available</option>';
        }
        
        let options = [];
        this.state.syncs.forEach(sync => {
            if (sync.cameras) {
                sync.cameras.forEach(camera => {
                    options.push(`<option value="camera:${camera.name}">${camera.name}</option>`);
                });
            }
        });
        
        return options.length > 0 ? options.join('') : '<option disabled>No cameras available</option>';
    }
    
    getSyncOptions() {
        if (!this.state.syncs || this.state.syncs.length === 0) {
            return '<option disabled>No sync modules available</option>';
        }
        
        return this.state.syncs.map(sync => 
            `<option value="sync:${sync.name}">${sync.name}</option>`
        ).join('');
    }
    
    async loadSchedules() {
        try {
            const response = await fetch('/api/schedules');
            if (!response.ok) throw new Error('Failed to load schedules');
            
            const data = await response.json();
            const schedules = data.rules || [];
            this.displaySchedules(schedules);
        } catch (error) {
            document.getElementById('schedulesList').innerHTML = 
                `<div class="loading" style="color: #ef4444;">Failed to load schedules: ${this.escapeHtml(error.message)}</div>`;
        }
    }
    
    displaySchedules(schedules) {
        const container = document.getElementById('schedulesList');
        
        if (!schedules || schedules.length === 0) {
            container.innerHTML = '<div class="loading">No schedules configured yet</div>';
            return;
        }
        
        container.innerHTML = schedules.map(schedule => {
            const statusColor = schedule.enabled ? 'var(--success)' : 'var(--text-secondary)';
            const statusIcon = schedule.enabled 
                ? '<svg class="icon-sm"><use href="#icon-check"/></svg>' 
                : '<svg class="icon-sm"><use href="#icon-circle"/></svg>';
            
            // Format interval
            let intervalText = '';
            if (schedule.interval_hours > 0 && schedule.interval_minutes > 0) {
                intervalText = `Every ${schedule.interval_hours}h ${schedule.interval_minutes}m`;
            } else if (schedule.interval_hours > 0) {
                intervalText = `Every ${schedule.interval_hours} hour${schedule.interval_hours > 1 ? 's' : ''}`;
            } else if (schedule.interval_minutes > 0) {
                intervalText = `Every ${schedule.interval_minutes} minutes`;
            }
            
            if (schedule.start_minute !== null) {
                intervalText += ` at :${String(schedule.start_minute).padStart(2, '0')}`;
            }
            
            // Format time window
            let timeWindow = '';
            if (schedule.start_time && schedule.end_time) {
                timeWindow = `<div style="font-size: 0.85rem; color: var(--text-secondary);">
                    ${schedule.start_time} - ${schedule.end_time}
                </div>`;
            }
            
            // Format days
            let daysText = '';
            if (schedule.days_of_week) {
                daysText = `<div style="font-size: 0.85rem; color: var(--text-secondary);">
                    ${schedule.days_of_week}
                </div>`;
            }
            
            // Format duration
            let durationText = '';
            if (schedule.duration_hours) {
                durationText = `<div style="font-size: 0.85rem; color: var(--text-secondary);">
                    Duration: ${schedule.duration_hours}h
                </div>`;
            }
            
            // Next run time
            let nextRunText = '';
            if (schedule.next_run) {
                const nextRun = new Date(schedule.next_run);
                nextRunText = `<div style="font-size: 0.85rem; color: var(--text-secondary);">
                    Next: ${this.formatDateTime(nextRun)}
                </div>`;
            }
            
            return `
                <div class="schedule-item" style="background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                        <div>
                            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
                                <span style="color: ${statusColor}; font-weight: bold;">${statusIcon}</span>
                                <span style="font-weight: 600; font-size: 1.05rem;">${this.escapeHtml(schedule.rule_name)}</span>
                            </div>
                            <div style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 0.5rem;">
                                ${this.escapeHtml(schedule.target_id)} → ${this.formatScheduleAction(schedule)}
                            </div>
                            <div style="font-size: 0.95rem; color: var(--primary); font-weight: 500;">
                                ${intervalText}
                            </div>
                            ${timeWindow}
                            ${daysText}
                            ${durationText}
                            ${nextRunText}
                        </div>
                        <div style="display: flex; gap: 0.5rem;">
                            <button class="btn btn-secondary" style="padding: 0.4rem 0.8rem; font-size: 0.85rem;" 
                                    onclick="app.toggleSchedule(${schedule.id}, ${!schedule.enabled})">
                                ${schedule.enabled ? 'Pause' : 'Resume'}
                            </button>
                            <button class="btn btn-secondary" style="padding: 0.4rem 0.8rem; font-size: 0.85rem; background: #ef4444;" 
                                    onclick="app.deleteSchedule(${schedule.id}, '${this.escapeHtml(schedule.rule_name)}')">
                                <svg class="icon-sm"><use href="#icon-trash"/></svg>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    formatScheduleAction(schedule) {
        const actions = {
            'CAMERA_MOTION': schedule.action === 'enable' ? 'Unsnooze (Enable Motion)' : 'Snooze (Disable Motion)',
            'CAMERA_THUMBNAIL': 'Capture Thumbnail',
            'SYNC_ARM': 'Arm System',
            'SYNC_DISARM': 'Disarm System'
        };
        return actions[schedule.rule_type] || schedule.rule_type;
    }
    
    async createSchedule() {
        try {
            const form = document.getElementById('scheduleForm');
            const target = document.getElementById('scheduleTarget').value;
            const action = document.getElementById('scheduleAction').value;
            
            if (!target || !action) {
                this.showMessage('Please select a target and action', 'error');
                return;
            }
            
            // Parse target type and name
            const [targetType, targetName] = target.split(':');
            
            // Determine rule type based on action
            let ruleType, ruleAction;
            if (action.startsWith('camera_motion')) {
                ruleType = 'CAMERA_MOTION';
                ruleAction = action === 'camera_motion_enable' ? 'enable' : 'disable';
            } else if (action === 'camera_thumbnail') {
                ruleType = 'CAMERA_THUMBNAIL';
                ruleAction = 'capture';
            } else if (action === 'sync_arm') {
                ruleType = 'SYNC_ARM';
                ruleAction = 'arm';
            } else if (action === 'sync_disarm') {
                ruleType = 'SYNC_DISARM';
                ruleAction = 'disarm';
            }
            
            // Get days of week
            const daysChecked = Array.from(document.querySelectorAll('#scheduleForm input[type="checkbox"]:checked'))
                .map(cb => cb.value);
            
            const scheduleData = {
                rule_name: document.getElementById('scheduleName').value,
                rule_type: ruleType,
                target_id: targetName,
                action: ruleAction,
                enabled: true,
                interval_hours: parseInt(document.getElementById('scheduleIntervalHours').value) || 0,
                interval_minutes: parseInt(document.getElementById('scheduleIntervalMinutes').value) || 0,
                start_minute: document.getElementById('scheduleStartMinute').value ? 
                    parseInt(document.getElementById('scheduleStartMinute').value) : null,
                duration_hours: document.getElementById('scheduleDuration').value ? 
                    parseFloat(document.getElementById('scheduleDuration').value) : null,
                start_time: document.getElementById('scheduleStartTime').value || null,
                end_time: document.getElementById('scheduleEndTime').value || null,
                days_of_week: daysChecked.length > 0 ? daysChecked.join(',') : null
            };
            
            // Validate interval
            if (scheduleData.interval_hours === 0 && scheduleData.interval_minutes === 0) {
                this.showMessage('Please specify an interval (hours and/or minutes)', 'error');
                return;
            }
            
            const response = await fetch('/api/schedules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(scheduleData)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to create schedule');
            }
            
            this.showMessage('Schedule created successfully', 'success');
            form.reset();
            this.loadSchedules();
        } catch (error) {
            this.showMessage('Failed to create schedule: ' + error.message, 'error');
        }
    }
    
    async toggleSchedule(id, enabled) {
        try {
            const response = await fetch(`/api/schedules/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to update schedule');
            }
            
            this.showMessage(`Schedule ${enabled ? 'resumed' : 'paused'}`, 'success');
            this.loadSchedules();
        } catch (error) {
            this.showMessage('Failed to update schedule: ' + error.message, 'error');
        }
    }
    
    async deleteSchedule(id, name) {
        if (!confirm(`Are you sure you want to delete the schedule "${name}"?`)) {
            return;
        }
        
        try {
            const response = await fetch(`/api/schedules/${id}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to delete schedule');
            }
            
            this.showMessage('Schedule deleted successfully', 'success');
            this.loadSchedules();
        } catch (error) {
            this.showMessage('Failed to delete schedule: ' + error.message, 'error');
        }
    }
    
    async loadExecutionLog() {
        try {
            const hours = document.getElementById('executionLogTimeRange')?.value || 168;
            const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
            
            const response = await fetch(`/api/schedules/execution-log?since=${encodeURIComponent(since)}&limit=100`);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to load execution log');
            }
            
            const data = await response.json();
            const logs = data.logs || [];
            this.displayExecutionLog(logs);
        } catch (error) {
            document.getElementById('executionLogList').innerHTML = 
                `<div class="loading" style="color: #ef4444;">Failed to load execution log: ${this.escapeHtml(error.message)}</div>`;
        }
    }
    
    displayExecutionLog(logs) {
        const container = document.getElementById('executionLogList');
        
        if (!logs || logs.length === 0) {
            container.innerHTML = '<div class="loading">No execution log entries yet</div>';
            return;
        }
        
        const logHtml = logs.map(log => {
            const timestamp = new Date(log.executed_at);
            const statusColor = log.success ? '#10b981' : '#ef4444';
            const statusIcon = log.success 
                ? '<svg class="icon-sm" style="color: #10b981;"><use href="#icon-check"/></svg>' 
                : '<svg class="icon-sm" style="color: #ef4444;"><use href="#icon-circle"/></svg>';
            const durationText = log.duration_ms ? `${log.duration_ms}ms` : '-';
            
            return `
                <div style="padding: 1rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
                            <span style="color: ${statusColor}; font-weight: 600; font-size: 1.2rem;">${statusIcon}</span>
                            <strong>${this.escapeHtml(log.action)}</strong>
                            <span style="color: var(--text-secondary);">${this.escapeHtml(log.target_type)} • ${this.escapeHtml(log.target_name)}</span>
                        </div>
                        <div style="font-size: 0.875rem; color: var(--text-secondary);">
                            ${this.formatDateTime(timestamp)} • ${durationText}
                            ${log.error_message ? `<br><span style="color: #ef4444;">Error: ${this.escapeHtml(log.error_message)}</span>` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = logHtml;
    }
    
    formatDuration(minutes) {
        // Handle invalid values
        if (minutes == null || isNaN(minutes) || minutes === 0) {
            return '0 min';
        }
        
        if (minutes < 60) {
            return Math.round(minutes) + ' min';
        } else if (minutes < 1440) {
            const hours = Math.floor(minutes / 60);
            const mins = Math.round(minutes % 60);
            return `${hours}h ${mins}m`;
        } else {
            const days = Math.floor(minutes / 1440);
            const hours = Math.floor((minutes % 1440) / 60);
            return `${days}d ${hours}h`;
        }
    }
    
    formatRelativeTime(date, hoursRange) {
        const now = new Date();
        const diffMs = now - date;
        const diffHours = diffMs / (1000 * 60 * 60);
        const diffDays = diffHours / 24;
        
        // For ranges less than 48 hours, show hourly labels
        if (hoursRange <= 48) {
            if (diffHours < 1) {
                return Math.round(diffMs / (1000 * 60)) + 'm ago';
            } else if (diffHours < 24) {
                return Math.round(diffHours) + 'h ago';
            } else {
                const days = Math.floor(diffHours / 24);
                const hours = Math.round(diffHours % 24);
                return `${days}d ${hours}h ago`;
            }
        }
        // For longer ranges, show daily labels  
        else {
            if (diffDays < 1) {
                return Math.round(diffHours) + 'h ago';
            } else if (diffDays < 7) {
                return Math.round(diffDays) + 'd ago';
            } else {
                const weeks = Math.floor(diffDays / 7);
                return weeks + 'w ago';
            }
        }
    }
    
    updateTimeScale(elementId, history, hoursRange) {
        if (!history || history.length === 0) {
            document.getElementById(elementId).textContent = '';
            return;
        }
        
        const oldest = new Date(history[history.length - 1].timestamp);
        const newest = new Date(history[0].timestamp);
        const spanMs = newest - oldest;
        const spanHours = spanMs / (1000 * 60 * 60);
        const spanDays = spanHours / 24;
        
        let timeSpanText;
        if (spanHours < 24) {
            timeSpanText = `${Math.round(spanHours)} hours`;
        } else if (spanDays < 7) {
            timeSpanText = `${Math.round(spanDays)} days`;
        } else {
            timeSpanText = `${Math.round(spanDays / 7)} weeks`;
        }
        
        document.getElementById(elementId).textContent = 
            `Showing ${history.length} data points spanning ${timeSpanText}`;
    }
    
    downloadBatteryCSV() {
        if (!this.currentBatteryData || this.currentBatteryData.length === 0) {
            this.showMessage('No battery data to download', 'info');
            return;
        }
        
        const camera = document.getElementById('batteryCameraSelect').value;
        const csv = this.generateBatteryCSV(this.currentBatteryData);
        this.downloadCSV(csv, `battery-history-${camera}-${new Date().toISOString().split('T')[0]}.csv`);
        this.showMessage('Battery CSV downloaded', 'success');
    }
    
    downloadStatusCSV() {
        if (!this.currentStatusData || this.currentStatusData.length === 0) {
            this.showMessage('No status data to download', 'info');
            return;
        }
        
        const camera = document.getElementById('statusCameraSelect').value;
        const csv = this.generateStatusCSV(this.currentStatusData);
        this.downloadCSV(csv, `status-history-${camera}-${new Date().toISOString().split('T')[0]}.csv`);
        this.showMessage('Status CSV downloaded', 'success');
    }
    
    generateBatteryCSV(data) {
        const header = 'Timestamp,Camera,Battery Voltage (V),Battery Level (%)\n';
        const rows = data.map(record => {
            const timestamp = new Date(record.timestamp).toISOString();
            const voltage = (record.battery_voltage / 100).toFixed(2);
            const level = record.battery_level || '-';
            return `${timestamp},${record.camera_name},${voltage},${level}`;
        }).join('\n');
        return header + rows;
    }
    
    generateStatusCSV(data) {
        const header = 'Timestamp,Camera,Status,Signal Strength\n';
        const rows = data.map(record => {
            const timestamp = new Date(record.timestamp).toISOString();
            const status = record.is_online ? 'Online' : 'Offline';
            const signal = record.signal_strength || '-';
            return `${timestamp},${record.camera_name},${status},${signal}`;
        }).join('\n');
        return header + rows;
    }
    
    downloadCSV(csvContent, filename) {
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    
    // Camera Modal Chart Functions
    
    initializeCameraModalCharts() {
        // Initialize battery chart for modal
        const batteryCtx = document.getElementById('modalBatteryChart');
        if (batteryCtx) {
            if (this.cameraModalBatteryChart) {
                this.cameraModalBatteryChart.destroy();
            }
            this.cameraModalBatteryChart = new Chart(batteryCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Battery Voltage',
                        data: [],
                        borderColor: 'rgb(16, 185, 129)',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text')
                            }
                        },
                        tooltip: {
                            callbacks: {
                                title: function(context) {
                                    return context[0].label;
                                },
                                label: function(context) {
                                    return 'Battery: ' + context.parsed.y.toFixed(2) + 'V';
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45,
                                autoSkip: true,
                                maxTicksLimit: 6,
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                            },
                            grid: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Voltage (V)',
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text')
                            },
                            ticks: {
                                callback: function(value) {
                                    return value.toFixed(2) + 'V';
                                },
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                            },
                            grid: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                            }
                        }
                    }
                }
            });
        }
        
        // Initialize status chart for modal
        const statusCtx = document.getElementById('modalStatusChart');
        if (statusCtx) {
            if (this.cameraModalStatusChart) {
                this.cameraModalStatusChart.destroy();
            }
            this.cameraModalStatusChart = new Chart(statusCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Online',
                        data: [],
                        borderColor: 'rgb(16, 185, 129)',
                        backgroundColor: 'rgba(16, 185, 129, 0.3)',
                        stepped: true,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text')
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return context.parsed.y === 1 ? 'Online' : 'Offline';
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45,
                                autoSkip: true,
                                maxTicksLimit: 6,
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                            },
                            grid: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                            }
                        },
                        y: {
                            min: 0,
                            max: 1,
                            title: {
                                display: true,
                                text: 'Status',
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text')
                            },
                            ticks: {
                                stepSize: 1,
                                callback: function(value) {
                                    return value === 1 ? 'Online' : 'Offline';
                                },
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                            },
                            grid: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                            }
                        }
                    }
                }
            });
        }
    }
    
    initializeSyncModalCharts() {
        // Initialize status chart for sync module modal (uptime only, no battery)
        const statusCtx = document.getElementById('modalSyncStatusChart');
        if (statusCtx) {
            if (this.syncModalStatusChart) {
                this.syncModalStatusChart.destroy();
            }
            this.syncModalStatusChart = new Chart(statusCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Online',
                        data: [],
                        borderColor: 'rgb(16, 185, 129)',
                        backgroundColor: 'rgba(16, 185, 129, 0.3)',
                        stepped: true,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text')
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return context.parsed.y === 1 ? 'Online' : 'Offline';
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45,
                                autoSkip: true,
                                maxTicksLimit: 6,
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                            },
                            grid: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                            }
                        },
                        y: {
                            min: 0,
                            max: 1,
                            title: {
                                display: true,
                                text: 'Status',
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text')
                            },
                            ticks: {
                                stepSize: 1,
                                callback: function(value) {
                                    return value === 1 ? 'Online' : 'Offline';
                                },
                                color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary')
                            },
                            grid: {
                                color: getComputedStyle(document.documentElement).getPropertyValue('--border')
                            }
                        }
                    }
                }
            });
        }
    }
    
    async loadCameraModalBatteryHistory(camera) {
        const hours = document.getElementById('modalBatteryTimeRange').value;
        
        if (!camera) {
            return;
        }
        
        try {
            const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
            const response = await fetch(`/api/history/battery/${encodeURIComponent(camera)}?since=${encodeURIComponent(since)}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load battery history');
            }
            
            const data = await response.json();
            const history = data.history || [];
            
            // Store for CSV export
            this.currentModalBatteryData = history;
            
            if (history.length === 0) {
                document.getElementById('modalBatteryTimeScale').textContent = 'No data available';
                return;
            }
            
            // Update chart with relative time labels
            const labels = history.map(h => {
                const date = new Date(h.timestamp);
                return this.formatRelativeTime(date, parseInt(hours));
            });
            const voltages = history.map(h => h.battery_voltage / 100);
            
            this.cameraModalBatteryChart.data.labels = labels;
            this.cameraModalBatteryChart.data.datasets[0].data = voltages;
            this.cameraModalBatteryChart.update();
            
            // Update time scale indicator
            this.updateTimeScaleModal('modalBatteryTimeScale', history, parseInt(hours));
            
            // Load and display stats
            await this.loadCameraModalBatteryStats(camera, hours);
            
        } catch (error) {
            this.showMessage('Failed to load battery history: ' + error.message, 'error');
        }
    }
    
    async loadCameraModalBatteryStats(camera, hours) {
        try {
            const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
            const response = await fetch(`/api/history/battery/${encodeURIComponent(camera)}/stats?since=${encodeURIComponent(since)}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load battery stats');
            }
            
            const stats = await response.json();
            
            document.getElementById('modalAvgVoltage').textContent = (stats.average_voltage / 100).toFixed(2) + 'V';
            document.getElementById('modalMinVoltage').textContent = (stats.min_voltage / 100).toFixed(2) + 'V';
            document.getElementById('modalMaxVoltage').textContent = (stats.max_voltage / 100).toFixed(2) + 'V';
            document.getElementById('modalBatteryStats').style.display = 'block';
            
        } catch (error) {
            console.error('Failed to load battery stats:', error);
        }
    }
    
    async loadCameraModalStatusHistory(camera) {
        const hours = document.getElementById('modalStatusTimeRange').value;
        
        if (!camera) {
            return;
        }
        
        try {
            const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
            const response = await fetch(`/api/history/status/${encodeURIComponent(camera)}?since=${encodeURIComponent(since)}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load status history');
            }
            
            const data = await response.json();
            const history = data.history || [];
            
            // Store for CSV export
            this.currentModalStatusData = history;
            
            if (history.length === 0) {
                document.getElementById('modalStatusTimeScale').textContent = 'No data available';
                return;
            }
            
            // Update chart with relative time labels
            const labels = history.map(h => {
                const date = new Date(h.timestamp);
                return this.formatRelativeTime(date, parseInt(hours));
            });
            const statusValues = history.map(h => h.is_online ? 1 : 0);
            
            this.cameraModalStatusChart.data.labels = labels;
            this.cameraModalStatusChart.data.datasets[0].data = statusValues;
            this.cameraModalStatusChart.update();
            
            // Update time scale indicator
            this.updateTimeScaleModal('modalStatusTimeScale', history, parseInt(hours));
            
            // Load and display stats
            await this.loadCameraModalStatusStats(camera, hours);
            
        } catch (error) {
            this.showMessage('Failed to load status history: ' + error.message, 'error');
        }
    }
    
    async loadCameraModalStatusStats(camera, hours) {
        try {
            const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
            const response = await fetch(`/api/history/status/${encodeURIComponent(camera)}/stats?since=${encodeURIComponent(since)}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load status stats');
            }
            
            const stats = await response.json();
            
            document.getElementById('modalUptimePercent').textContent = stats.uptime_percentage.toFixed(1) + '%';
            document.getElementById('modalOnlineTime').textContent = this.formatDuration(stats.total_online_minutes);
            document.getElementById('modalOfflineTime').textContent = this.formatDuration(stats.total_offline_minutes);
            document.getElementById('modalStatusStats').style.display = 'block';
            
        } catch (error) {
            console.error('Failed to load status stats:', error);
        }
    }
    
    updateTimeScaleModal(elementId, history, hoursRange) {
        if (!history || history.length === 0) {
            document.getElementById(elementId).textContent = '';
            return;
        }
        
        const oldest = new Date(history[history.length - 1].timestamp);
        const newest = new Date(history[0].timestamp);
        const spanMs = newest - oldest;
        const spanHours = spanMs / (1000 * 60 * 60);
        const spanDays = spanHours / 24;
        
        let timeSpanText;
        if (spanHours < 24) {
            timeSpanText = `${Math.round(spanHours)} hours`;
        } else if (spanDays < 7) {
            timeSpanText = `${Math.round(spanDays)} days`;
        } else {
            timeSpanText = `${Math.round(spanDays / 7)} weeks`;
        }
        
        document.getElementById(elementId).textContent = 
            `${history.length} data points spanning ${timeSpanText}`;
    }
    
    downloadCameraModalBatteryCSV() {
        if (!this.currentModalBatteryData || this.currentModalBatteryData.length === 0) {
            this.showMessage('No battery data to download', 'info');
            return;
        }
        
        const camera = this.currentCameraName;
        const csv = this.generateBatteryCSV(this.currentModalBatteryData);
        this.downloadCSV(csv, `battery-history-${camera}-${new Date().toISOString().split('T')[0]}.csv`);
        this.showMessage('Battery CSV downloaded', 'success');
    }
    
    downloadCameraModalStatusCSV() {
        if (!this.currentModalStatusData || this.currentModalStatusData.length === 0) {
            this.showMessage('No status data to download', 'info');
            return;
        }
        
        const camera = this.currentCameraName;
        const csv = this.generateStatusCSV(this.currentModalStatusData);
        this.downloadCSV(csv, `status-history-${camera}-${new Date().toISOString().split('T')[0]}.csv`);
        this.showMessage('Status CSV downloaded', 'success');
    }
    
    async saveAppearance() {
        try {
            const settings = {
                theme: document.getElementById('themeSelect').value,
                web_time_format: document.getElementById('timeFormatSelect').value
            };
            
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            
            if (!response.ok) throw new Error('Failed to save appearance settings');
            
            // Update theme if changed
            if (settings.theme !== this.theme) {
                this.theme = settings.theme;
                this.applyTheme();
            }
            
            // Update time format if changed
            if (settings.web_time_format !== this.config.web_time_format) {
                this.config.web_time_format = settings.web_time_format;
            }
            
            this.showMessage('Appearance settings saved successfully!', 'success');
            await this.loadData();
        } catch (error) {
            this.showMessage('Failed to save appearance settings: ' + error.message, 'error');
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
    
    async confirmReset() {
        const message = `<strong>WARNING:</strong> This will permanently delete ALL data including:

• All saved video clips and thumbnails
• All credentials (Blink and VoIP.ms)
• All configuration settings
• Authentication settings
• System logs

<strong>This action CANNOT be undone!</strong>

Are you absolutely sure you want to reset the system?`;
        
        const confirmed = await this.showConfirm(
            'System Reset',
            message,
            { confirmText: 'Yes, Reset', cancelText: 'Cancel', confirmClass: 'btn-danger' }
        );
        
        if (confirmed) {
            const doubleConfirm = await this.showConfirm(
                'Final Confirmation',
                'This is your last chance!\n\nClick "Reset Now" to proceed with the system reset, or "Cancel" to abort.',
                { confirmText: 'Reset Now', cancelText: 'Cancel', confirmClass: 'btn-danger' }
            );
            
            if (doubleConfirm) {
                this.resetSystem();
            }
        }
    }
    
    async resetSystem() {
        try {
            this.showLoading('Resetting system...');
            
            const response = await fetch('/api/system/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to reset system');
            }
            
            this.hideLoading();
            
            await this.showAlert(
                'Reset Complete',
                'System has been reset successfully. You will now be redirected to the setup page.'
            );
            
            // Redirect to root - should trigger setup flow
            window.location.href = '/';
            
        } catch (error) {
            this.hideLoading();
            this.showMessage('Failed to reset system: ' + error.message, 'error');
        }
    }
    
    async loadMediaSettings() {
        try {
            const [configResp, statusResp] = await Promise.all([
                fetch('/api/media/config'),
                fetch('/api/media/status')
            ]);
            
            if (!configResp.ok || !statusResp.ok) {
                throw new Error('Failed to load media settings');
            }
            
            const config = await configResp.json();
            const status = await statusResp.json();
            
            const container = document.getElementById('mediaDownloadSettings');
            if (!container) return;
            
            const retentionTypeDesc = config.retention_type === 'count' 
                ? `Keep ${config.retention_count} newest clips per camera`
                : config.retention_type === 'days'
                ? `Keep clips from last ${config.retention_days} days`
                : `Keep last ${config.retention_size_gb} GB per camera`;
            
            container.innerHTML = `
                <div class="form-group" style="margin-bottom: 1rem;">
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                        <input type="checkbox" id="mediaEnabled" 
                               ${config.enabled ? 'checked' : ''}
                               style="width: 20px; height: 20px; cursor: pointer;">
                        <span class="form-label" style="margin: 0;">Enable automatic media downloads</span>
                    </label>
                    <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem; margin-left: 28px;">
                        Automatically download and archive clips and thumbnails
                    </small>
                </div>
                
                <div id="mediaDetailsSection" style="display: ${config.enabled ? 'block' : 'none'};">
                    ${status.enabled ? `
                        <div style="background: rgba(34, 197, 94, 0.1); border-left: 4px solid #22c55e; padding: 0.75rem; margin-bottom: 1rem; border-radius: 4px;">
                            <div style="font-weight: 500; margin-bottom: 0.25rem;">Status: ${status.running ? 'Running' : 'Enabled but not running'}</div>
                            <div style="font-size: 0.875rem; color: var(--text-secondary); font-family: monospace;">
                                ${status.total_clips || 0} clips • ${status.total_thumbnails || 0} thumbnails • ${status.total_size_mb || 0} MB
                            </div>
                            <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                ${status.base_path || config.base_path}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="settings-grid">
                        <div class="form-group">
                            <label class="form-label">Base Path</label>
                            <input type="text" id="mediaBasePath" class="form-input" 
                                   value="${config.base_path}" placeholder="/app/media">
                            <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem;">
                                Files saved to: path/clips|thumbnails/sync/camera/
                            </small>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Check Interval (minutes)</label>
                            <input type="number" id="mediaCheckInterval" class="form-input" 
                                   value="${config.check_interval_minutes}" min="5" max="1440">
                        </div>
                    </div>
                    
                    <div style="margin: 1rem 0;">
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; margin-bottom: 0.5rem;">
                            <input type="checkbox" id="mediaDownloadClips" 
                                   ${config.download_clips ? 'checked' : ''}
                                   style="width: 18px; height: 18px; cursor: pointer;">
                            <span style="font-size: 0.938rem;">Download clips</span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                            <input type="checkbox" id="mediaDownloadThumbnails" 
                                   ${config.download_thumbnails ? 'checked' : ''}
                                   style="width: 18px; height: 18px; cursor: pointer;">
                            <span style="font-size: 0.938rem;">Download thumbnails</span>
                        </label>
                    </div>
                    
                    <div class="form-group" style="margin-top: 1rem;">
                        <label class="form-label">Retention Policy</label>
                        <select id="mediaRetentionType" class="form-select">
                            <option value="count" ${config.retention_type === 'count' ? 'selected' : ''}>By Count</option>
                            <option value="days" ${config.retention_type === 'days' ? 'selected' : ''}>By Days</option>
                            <option value="size" ${config.retention_type === 'size' ? 'selected' : ''}>By Size</option>
                        </select>
                        <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem;">
                            Current: ${retentionTypeDesc}
                        </small>
                    </div>
                    
                    <div class="settings-grid" id="mediaRetentionValues">
                        <div class="form-group" id="retentionCountGroup" style="display: ${config.retention_type === 'count' ? 'block' : 'none'};">
                            <label class="form-label">Keep (clips per camera)</label>
                            <input type="number" id="mediaRetentionCount" class="form-input" 
                                   value="${config.retention_count}" min="1" max="10000">
                        </div>
                        
                        <div class="form-group" id="retentionDaysGroup" style="display: ${config.retention_type === 'days' ? 'block' : 'none'};">
                            <label class="form-label">Keep (days)</label>
                            <input type="number" id="mediaRetentionDays" class="form-input" 
                                   value="${config.retention_days}" min="1" max="365">
                        </div>
                        
                        <div class="form-group" id="retentionSizeGroup" style="display: ${config.retention_type === 'size' ? 'block' : 'none'};">
                            <label class="form-label">Keep (GB per camera)</label>
                            <input type="number" id="mediaRetentionSize" class="form-input" 
                                   value="${config.retention_size_gb}" min="0.1" max="1000" step="0.1">
                        </div>
                    </div>
                    
                    <div class="form-group" style="margin-top: 1rem;">
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                            <input type="checkbox" id="mediaUseNas" 
                                   ${config.use_nas ? 'checked' : ''}
                                   style="width: 20px; height: 20px; cursor: pointer;">
                            <span class="form-label" style="margin: 0;">Use NAS (Network Attached Storage)</span>
                        </label>
                    </div>
                    
                    <div id="nasSettings" style="display: ${config.use_nas ? 'block' : 'none'}; margin-top: 0.5rem; padding-left: 28px;">
                        <div class="settings-grid">
                            <div class="form-group">
                                <label class="form-label">NAS Type</label>
                                <select id="mediaNasType" class="form-select">
                                    <option value="smb" ${config.nas_type === 'smb' ? 'selected' : ''}>SMB/CIFS</option>
                                    <option value="nfs" ${config.nas_type === 'nfs' ? 'selected' : ''}>NFS</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label class="form-label">NAS Host</label>
                                <input type="text" id="mediaNasHost" class="form-input" 
                                       value="${config.nas_host}" placeholder="192.168.1.100">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Share Name</label>
                                <input type="text" id="mediaNasShare" class="form-input" 
                                       value="${config.nas_share}" placeholder="blink-media">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Username (SMB only)</label>
                                <input type="text" id="mediaNasUsername" class="form-input" 
                                       value="${config.nas_username}" placeholder="username">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Password (SMB only)</label>
                                <input type="password" id="mediaNasPassword" class="form-input" 
                                       placeholder="Leave blank to keep current">
                            </div>
                            <div class="form-group">
                                <label class="form-label">Mount Point</label>
                                <input type="text" id="mediaNasMountPoint" class="form-input" 
                                       value="${config.nas_mount_point}" placeholder="/mnt/nas">
                            </div>
                        </div>
                    </div>
                </div>
                
                <div style="margin-top: 1rem; display: flex; gap: 0.5rem;">
                    <button class="btn" id="saveMediaSettingsBtn">Save Media Settings</button>
                    ${config.enabled ? '<button class="btn btn-secondary" id="triggerDownloadBtn">Download Now</button>' : ''}
                </div>
            `;
            
            // Attach event listeners
            document.getElementById('mediaEnabled')?.addEventListener('change', (e) => {
                document.getElementById('mediaDetailsSection').style.display = e.target.checked ? 'block' : 'none';
            });
            
            document.getElementById('mediaRetentionType')?.addEventListener('change', (e) => {
                document.getElementById('retentionCountGroup').style.display = e.target.value === 'count' ? 'block' : 'none';
                document.getElementById('retentionDaysGroup').style.display = e.target.value === 'days' ? 'block' : 'none';
                document.getElementById('retentionSizeGroup').style.display = e.target.value === 'size' ? 'block' : 'none';
            });
            
            document.getElementById('mediaUseNas')?.addEventListener('change', (e) => {
                document.getElementById('nasSettings').style.display = e.target.checked ? 'block' : 'none';
            });
            
            document.getElementById('saveMediaSettingsBtn')?.addEventListener('click', () => this.saveMediaSettings());
            document.getElementById('triggerDownloadBtn')?.addEventListener('click', () => this.triggerMediaDownload());
            
        } catch (error) {
            console.error('Failed to load media settings:', error);
            const container = document.getElementById('mediaDownloadSettings');
            if (container) {
                container.innerHTML = `<p style="color: var(--error);">Failed to load media settings</p>`;
            }
        }
    }
    
    async saveMediaSettings() {
        try {
            const config = {
                enabled: document.getElementById('mediaEnabled')?.checked || false,
                download_clips: document.getElementById('mediaDownloadClips')?.checked || false,
                download_thumbnails: document.getElementById('mediaDownloadThumbnails')?.checked || false,
                base_path: document.getElementById('mediaBasePath')?.value || '/app/media',
                retention_type: document.getElementById('mediaRetentionType')?.value || 'count',
                retention_count: parseInt(document.getElementById('mediaRetentionCount')?.value) || 100,
                retention_days: parseInt(document.getElementById('mediaRetentionDays')?.value) || 30,
                retention_size_gb: parseFloat(document.getElementById('mediaRetentionSize')?.value) || 10.0,
                use_nas: document.getElementById('mediaUseNas')?.checked || false,
                nas_type: document.getElementById('mediaNasType')?.value || 'smb',
                nas_host: document.getElementById('mediaNasHost')?.value || '',
                nas_share: document.getElementById('mediaNasShare')?.value || '',
                nas_username: document.getElementById('mediaNasUsername')?.value || '',
                nas_password: document.getElementById('mediaNasPassword')?.value || '',
                nas_mount_point: document.getElementById('mediaNasMountPoint')?.value || '/mnt/nas',
                check_interval_minutes: parseInt(document.getElementById('mediaCheckInterval')?.value) || 15
            };
            
            // Remove password if blank (don't update)
            if (!config.nas_password) {
                delete config.nas_password;
            }
            
            const response = await fetch('/api/media/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            
            if (!response.ok) throw new Error('Failed to save media settings');
            
            this.showMessage('Media settings saved successfully!', 'success');
            // Reload to show updated status
            setTimeout(() => this.loadMediaSettings(), 1000);
            
        } catch (error) {
            this.showMessage('Failed to save media settings: ' + error.message, 'error');
        }
    }
    
    async triggerMediaDownload() {
        try {
            this.showLoading('Starting media download...');
            
            const response = await fetch('/api/media/download', {
                method: 'POST'
            });
            
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to trigger download');
            }
            
            this.hideLoading();
            this.showMessage('Media download started', 'success');
            
            // Reload status after a delay
            setTimeout(() => this.loadMediaSettings(), 3000);
            
        } catch (error) {
            this.hideLoading();
            this.showMessage('Failed to trigger download: ' + error.message, 'error');
        }
    }
    
    async loadBlinkBridgeSettings() {
        try {
            const [statusResp, streamsResp] = await Promise.all([
                fetch('/api/blinkbridge/status'),
                fetch('/api/blinkbridge/streams')
            ]);
            
            if (!statusResp.ok) {
                throw new Error('Failed to load BlinkBridge status');
            }
            
            const status = await statusResp.json();
            const streams = streamsResp.ok ? await streamsResp.json() : {};
            
            const container = document.getElementById('blinkBridgeSettings');
            if (!container) return;
            
            const streamCount = Object.keys(streams).length;
            const statusColor = status.running ? 'rgba(34, 197, 94, 0.1)' : 'rgba(156, 163, 175, 0.1)';
            const statusBorder = status.running ? '#22c55e' : '#9ca3af';
            const statusText = status.running ? 'Running' : status.enabled ? 'Enabled (Not Running)' : 'Disabled';
            
            container.innerHTML = `
                <div class="form-group" style="margin-bottom: 1rem;">
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                        <input type="checkbox" id="blinkbridgeEnabled" 
                               ${status.enabled ? 'checked' : ''}
                               style="width: 20px; height: 20px; cursor: pointer;">
                        <span class="form-label" style="margin: 0;">Enable BlinkBridge RTSP Streaming</span>
                    </label>
                    <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem; margin-left: 28px;">
                        Stream cameras to Frigate, Home Assistant, or any RTSP client
                    </small>
                </div>
                
                <div id="blinkbridgeDetailsSection" style="display: ${status.enabled ? 'block' : 'none'};">
                    ${status.running ? `
                        <div style="background: ${statusColor}; border-left: 4px solid ${statusBorder}; padding: 0.75rem; margin-bottom: 1rem; border-radius: 4px;">
                            <div style="font-weight: 500; margin-bottom: 0.25rem;">Status: ${statusText}</div>
                            <div style="font-size: 0.875rem; color: var(--text-secondary);">
                                ${streamCount} active stream${streamCount !== 1 ? 's' : ''} • RTSP Port: ${status.config.rtsp_port}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="settings-grid">
                        <div class="form-group">
                            <label class="form-label">RTSP Host</label>
                            <input type="text" id="blinkbridgeHost" class="form-input" 
                                   value="${status.config.rtsp_host}" placeholder="localhost">
                            <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem;">
                                Host for RTSP URLs (use container name for Docker)
                            </small>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">RTSP Port</label>
                            <input type="number" id="blinkbridgePort" class="form-input" 
                                   value="${status.config.rtsp_port}" min="1" max="65535">
                        </div>
                    </div>
                    
                    <div class="settings-grid">
                        <div class="form-group">
                            <label class="form-label">Poll Interval (seconds)</label>
                            <input type="number" id="blinkbridgePollInterval" class="form-input" 
                                   value="${status.config.poll_interval}" min="0.5" max="60" step="0.5">
                            <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem;">
                                How often to check for new clips
                            </small>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Max Failures</label>
                            <input type="number" id="blinkbridgeMaxFailures" class="form-input" 
                                   value="${status.config.max_failures}" min="1" max="20">
                            <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem;">
                                Restart stream after this many failures
                            </small>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Camera Selection</label>
                        <div id="blinkbridgeCameraList" style="max-height: 300px; overflow-y: auto; border: 1px solid var(--border); border-radius: 4px; padding: 0.5rem; background: var(--surface);">
                            ${this.renderBlinkBridgeCameraList(status.config.enabled_cameras || [])}
                        </div>
                        <small style="color: var(--text-secondary); display: block; margin-top: 0.25rem;">
                            Select cameras to stream via RTSP
                        </small>
                    </div>
                    
                    ${streamCount > 0 ? `
                        <div class="form-group" style="margin-top: 1rem;">
                            <label class="form-label">Active Streams</label>
                            <div style="background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 0.75rem; max-height: 200px; overflow-y: auto;">
                                ${this.renderBlinkBridgeStreams(streams)}
                            </div>
                        </div>
                    ` : ''}
                </div>
                
                <div style="margin-top: 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button class="btn" id="saveBlinkBridgeBtn">Save Settings</button>
                    ${status.enabled && !status.running ? '<button class="btn btn-primary" id="startBlinkBridgeBtn">Start Streaming</button>' : ''}
                    ${status.running ? '<button class="btn btn-secondary" id="stopBlinkBridgeBtn">Stop Streaming</button>' : ''}
                    ${status.enabled ? '<button class="btn btn-secondary" id="showFrigateConfigBtn">Show Frigate Config</button>' : ''}
                </div>
            `;
            
            // Attach event listeners
            document.getElementById('blinkbridgeEnabled')?.addEventListener('change', (e) => {
                document.getElementById('blinkbridgeDetailsSection').style.display = e.target.checked ? 'block' : 'none';
            });
            
            document.getElementById('saveBlinkBridgeBtn')?.addEventListener('click', () => this.saveBlinkBridgeSettings());
            document.getElementById('startBlinkBridgeBtn')?.addEventListener('click', () => this.startBlinkBridge());
            document.getElementById('stopBlinkBridgeBtn')?.addEventListener('click', () => this.stopBlinkBridge());
            document.getElementById('showFrigateConfigBtn')?.addEventListener('click', () => this.showFrigateConfig());
            
        } catch (error) {
            console.error('Failed to load BlinkBridge settings:', error);
            const container = document.getElementById('blinkBridgeSettings');
            if (container) {
                container.innerHTML = `<p style="color: var(--error);">Failed to load BlinkBridge settings</p>`;
            }
        }
    }
    
    renderBlinkBridgeCameraList(enabledCameras) {
        if (!this.state.cameras || this.state.cameras.length === 0) {
            return '<div style="color: var(--text-secondary); padding: 0.5rem;">No cameras available</div>';
        }
        
        return this.state.cameras.map(camera => {
            const isEnabled = enabledCameras.includes(camera.name);
            return `
                <label style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem; cursor: pointer; border-radius: 4px; transition: background 0.2s;" 
                       onmouseover="this.style.background='var(--hover-bg)'" 
                       onmouseout="this.style.background='transparent'">
                    <input type="checkbox" class="blinkbridge-camera-checkbox" 
                           data-camera="${this.escapeHtml(camera.name)}"
                           ${isEnabled ? 'checked' : ''}
                           style="width: 18px; height: 18px; cursor: pointer;">
                    <span style="flex: 1;">${this.escapeHtml(camera.name)}</span>
                    <span style="font-size: 0.75rem; color: var(--text-secondary); font-family: monospace;">
                        ${camera.sync || 'Unknown Sync'}
                    </span>
                </label>
            `;
        }).join('');
    }
    
    renderBlinkBridgeStreams(streams) {
        return Object.entries(streams).map(([cameraName, info]) => {
            const statusColor = info.running ? '#22c55e' : '#ef4444';
            const statusIcon = info.running ? '✓' : '✗';
            return `
                <div style="padding: 0.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
                    <div style="flex: 1;">
                        <div style="font-weight: 500; display: flex; align-items: center; gap: 0.5rem;">
                            <span style="color: ${statusColor}; font-size: 0.875rem;">${statusIcon}</span>
                            ${this.escapeHtml(cameraName)}
                        </div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary); font-family: monospace; margin-top: 0.25rem;">
                            ${this.escapeHtml(info.rtsp_url)}
                        </div>
                    </div>
                    ${info.failure_count > 0 ? `
                        <span style="font-size: 0.75rem; color: var(--error); padding: 0.25rem 0.5rem; background: rgba(239, 68, 68, 0.1); border-radius: 4px;">
                            ${info.failure_count} failures
                        </span>
                    ` : ''}
                </div>
            `;
        }).join('');
    }
    
    async saveBlinkBridgeSettings() {
        try {
            const enabled = document.getElementById('blinkbridgeEnabled')?.checked || false;
            const enabledCameras = Array.from(document.querySelectorAll('.blinkbridge-camera-checkbox:checked'))
                .map(cb => cb.getAttribute('data-camera'));
            
            const config = {
                enabled,
                rtsp_host: document.getElementById('blinkbridgeHost')?.value || 'localhost',
                rtsp_port: parseInt(document.getElementById('blinkbridgePort')?.value) || 8554,
                poll_interval: parseFloat(document.getElementById('blinkbridgePollInterval')?.value) || 1.0,
                max_failures: parseInt(document.getElementById('blinkbridgeMaxFailures')?.value) || 3,
                enabled_cameras: enabledCameras
            };
            
            const response = await fetch('/api/blinkbridge/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            
            if (!response.ok) throw new Error('Failed to save BlinkBridge settings');
            
            this.showMessage('BlinkBridge settings saved successfully!', 'success');
            setTimeout(() => this.loadBlinkBridgeSettings(), 1000);
            
        } catch (error) {
            this.showMessage('Failed to save BlinkBridge settings: ' + error.message, 'error');
        }
    }
    
    async startBlinkBridge() {
        try {
            const enabledCameras = Array.from(document.querySelectorAll('.blinkbridge-camera-checkbox:checked'))
                .map(cb => cb.getAttribute('data-camera'));
            
            if (enabledCameras.length === 0) {
                this.showMessage('Please select at least one camera to stream', 'warning');
                return;
            }
            
            this.showLoading('Starting BlinkBridge streaming...');
            
            const response = await fetch('/api/blinkbridge/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cameras: enabledCameras })
            });
            
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to start BlinkBridge');
            }
            
            this.hideLoading();
            this.showMessage('BlinkBridge streaming started!', 'success');
            setTimeout(() => this.loadBlinkBridgeSettings(), 2000);
            
        } catch (error) {
            this.hideLoading();
            this.showMessage('Failed to start BlinkBridge: ' + error.message, 'error');
        }
    }
    
    async stopBlinkBridge() {
        try {
            this.showLoading('Stopping BlinkBridge streaming...');
            
            const response = await fetch('/api/blinkbridge/stop', {
                method: 'POST'
            });
            
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to stop BlinkBridge');
            }
            
            this.hideLoading();
            this.showMessage('BlinkBridge streaming stopped', 'success');
            setTimeout(() => this.loadBlinkBridgeSettings(), 1000);
            
        } catch (error) {
            this.hideLoading();
            this.showMessage('Failed to stop BlinkBridge: ' + error.message, 'error');
        }
    }
    
    async showFrigateConfig() {
        try {
            const enabledCameras = Array.from(document.querySelectorAll('.blinkbridge-camera-checkbox:checked'))
                .map(cb => cb.getAttribute('data-camera'));
            
            const url = enabledCameras.length > 0 
                ? `/api/blinkbridge/frigate?cameras=${enabledCameras.join(',')}`
                : '/api/blinkbridge/frigate';
            
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error('Failed to generate Frigate config');
            }
            
            const data = await response.json();
            
            // Create modal
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content" style="max-width: 800px;">
                    <div class="modal-header">
                        <h3 style="margin: 0; display: flex; align-items: center; gap: 0.5rem;">
                            <svg class="icon" style="width: 24px; height: 24px;">
                                <use href="#icon-settings"/>
                            </svg>
                            Frigate Configuration
                        </h3>
                        <button class="close-modal">&times;</button>
                    </div>
                    <div class="modal-body">
                        <p style="color: var(--text-secondary); margin-bottom: 1rem;">
                            Copy and paste this configuration into your Frigate <code>config.yml</code> file:
                        </p>
                        <div style="position: relative;">
                            <pre style="background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 1rem; overflow-x: auto; max-height: 500px; font-size: 0.875rem;"><code id="frigateConfigCode">${this.escapeHtml(data.config)}</code></pre>
                            <button class="btn btn-sm" id="copyFrigateConfigBtn" 
                                    style="position: absolute; top: 0.5rem; right: 0.5rem;">
                                Copy
                            </button>
                        </div>
                        <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(59, 130, 246, 0.1); border-left: 4px solid #3b82f6; border-radius: 4px;">
                            <strong>Note:</strong> Make sure the RTSP host (<code>${data.rtsp_host}</code>) is accessible from your Frigate container.
                            If Frigate is in a different Docker network, use the container name or bridge IP.
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary close-modal">Close</button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            modal.style.display = 'flex';
            
            // Copy button functionality
            document.getElementById('copyFrigateConfigBtn')?.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(data.config);
                    const btn = document.getElementById('copyFrigateConfigBtn');
                    if (btn) {
                        btn.textContent = 'Copied!';
                        setTimeout(() => btn.textContent = 'Copy', 2000);
                    }
                } catch (error) {
                    this.showMessage('Failed to copy to clipboard', 'error');
                }
            });
            
            // Close modal handlers
            modal.querySelectorAll('.close-modal').forEach(btn => {
                btn.addEventListener('click', () => {
                    modal.remove();
                });
            });
            
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.remove();
                }
            });
            
        } catch (error) {
            this.showMessage('Failed to show Frigate config: ' + error.message, 'error');
        }
    }
    
    // Camera/Sync toggle methods
    async toggleCameraSnooze(name, enabled) {
        await this.apiCall(`/api/camera/${encodeURIComponent(name)}/snooze`, { enabled });
        this.showMessage(`Camera "${name}" ${enabled ? 'snoozed' : 'unsnoozed'}`, 'success');
    }
    
    async toggleCameraArm(name, enabled) {
        await this.apiCall(`/api/camera/${encodeURIComponent(name)}/arm`, { enabled });
        this.showMessage(`Camera "${name}" ${enabled ? 'armed' : 'disarmed'}`, 'success');
    }
    
    async toggleCameraThumbnail(name, enabled) {
        await this.apiCall(`/api/camera/${encodeURIComponent(name)}/thumbnail`, { enabled });
        this.showMessage(`Thumbnail updates for "${name}" ${enabled ? 'enabled' : 'disabled'}`, 'success');
    }
    
    async toggleSyncSnooze(name, enabled) {
        await this.apiCall(`/api/sync/${encodeURIComponent(name)}/snooze`, { enabled });
        this.showMessage(`Sync "${name}" ${enabled ? 'snoozed' : 'unsnoozed'}`, 'success');
    }
    
    async toggleSyncArm(name, enabled) {
        await this.apiCall(`/api/sync/${encodeURIComponent(name)}/arm`, { enabled });
        this.showMessage(`Sync "${name}" ${enabled ? 'armed' : 'disarmed'}`, 'success');
    }
    
    async apiCall(endpoint, data) {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            
            if (!response.ok) {
                // Try to get error message from response
                let errorMsg = 'API call failed';
                try {
                    const errorData = await response.json();
                    if (errorData.error) {
                        errorMsg = errorData.error;
                    }
                } catch (e) {
                    errorMsg = `API call failed with status ${response.status}`;
                }
                throw new Error(errorMsg);
            }
            
            // Note: Success messages are now handled by the calling function for specificity
            
            // Reload state to show updated values
            await this.loadData();
        } catch (error) {
            this.showMessage('Update failed: ' + error.message, 'error');
            console.error('API call error:', error);
            // Reload anyway to revert UI to actual state
            await this.loadData();
        }
    }
    
    // Modal methods
    showModal(title, content, footer = '') {
        const modal = `
            <div class="modal-overlay" onclick="app.closeModal(event)">
                <div class="modal" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <div class="modal-title">${title}</div>
                        <button class="modal-close" onclick="app.closeModal()">&times;</button>
                    </div>
                    <div class="modal-body">
                        ${content}
                    </div>
                    ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
                </div>
            </div>
        `;
        document.getElementById('modalContainer').innerHTML = modal;
    }
    
    showTabbedModal(title, tabs, footer = '') {
        const tabButtons = tabs.map((tab, index) => 
            `<button class="modal-tab ${index === 0 ? 'active' : ''}" onclick="app.switchModalTab(${index})">${tab.title}</button>`
        ).join('');
        
        const tabContents = tabs.map((tab, index) => 
            `<div class="modal-tab-content ${index === 0 ? 'active' : ''}" data-tab-index="${index}">${tab.content}</div>`
        ).join('');
        
        const modal = `
            <div class="modal-overlay" onclick="app.closeModal(event)">
                <div class="modal" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <div class="modal-title">${title}</div>
                        <button class="modal-close" onclick="app.closeModal()">&times;</button>
                    </div>
                    <div class="modal-tabs">
                        ${tabButtons}
                    </div>
                    <div class="modal-body">
                        ${tabContents}
                    </div>
                    ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
                </div>
            </div>
        `;
        document.getElementById('modalContainer').innerHTML = modal;
    }
    
    switchModalTab(tabIndex) {
        // Update tab buttons
        const tabs = document.querySelectorAll('.modal-tab');
        tabs.forEach((tab, index) => {
            if (index === tabIndex) {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });
        
        // Update tab contents
        const contents = document.querySelectorAll('.modal-tab-content');
        contents.forEach((content, index) => {
            if (index === tabIndex) {
                content.classList.add('active');
            } else {
                content.classList.remove('active');
            }
        });
        
        // Load media when Media tab (index 2) is selected
        if (tabIndex === 2 && this.currentCameraName) {
            this.loadCameraClips(this.currentCameraName);
        }
        
        // Load stats when Stats tab (index 3) is selected for camera
        if (tabIndex === 3 && this.currentCameraName) {
            this.initializeCameraModalCharts();
            this.loadCameraModalBatteryHistory(this.currentCameraName);
            this.loadCameraModalStatusHistory(this.currentCameraName);
        }
        
        // Load stats when Stats tab (index 2) is selected for sync module
        if (tabIndex === 2 && this.currentSyncName && !this.currentCameraName) {
            this.initializeSyncModalCharts();
            this.loadSyncModalStatusHistory(this.currentSyncName);
        }
    }
    
    closeModal(event) {
        if (!event || event.target.classList.contains('modal-overlay')) {
            document.getElementById('modalContainer').innerHTML = '';
        }
    }
    
    async showCameraInfo(cameraName) {
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/info`);
            if (!response.ok) throw new Error('Failed to load camera info');
            const info = await response.json();
            
            // Get current state
            const camera = this.findCamera(cameraName);
            
            const content = `
                <div class="info-grid">
                    <div class="info-row">
                        <div class="info-label">Status</div>
                        <div class="info-value">${info.status || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Armed</div>
                        <div class="info-value">${camera?.arm ? 'Yes' : 'No'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Snoozed</div>
                        <div class="info-value">${camera?.snooze ? 'Yes' : 'No'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Motion</div>
                        <div class="info-value">${info.enabled === true ? 'Enabled' : 'Disabled'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Battery</div>
                        <div class="info-value">${info.battery || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">WiFi</div>
                        <div class="info-value">${info.wifi_strength || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Temp</div>
                        <div class="info-value">${info.temperature || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Type</div>
                        <div class="info-value">${info.product_type || info.type || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Camera ID</div>
                        <div class="info-value">${info.camera_id || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Serial</div>
                        <div class="info-value">${info.serial || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Firmware</div>
                        <div class="info-value">${info.fw_version || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Network ID</div>
                        <div class="info-value">${info.network_id || 'N/A'}</div>
                    </div>
                </div>
            `;
            
            this.showModal(cameraName, content);
        } catch (error) {
            this.showMessage('Failed to load camera info: ' + error.message, 'error');
        }
    }
    
    async showCameraModal(cameraName, syncName) {
        try {
            // Fetch camera info
            const infoResponse = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/info`);
            if (!infoResponse.ok) throw new Error('Failed to load camera info');
            const info = await infoResponse.json();
            
            // Fetch night vision setting
            let nightVisionMode = 'auto';
            try {
                const nvResponse = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/night_vision`);
                if (nvResponse.ok) {
                    const nvData = await nvResponse.json();
                    nightVisionMode = nvData.night_vision || 'auto';
                }
            } catch (e) {
                console.warn('Failed to load night vision setting:', e);
            }
            
            // Fetch BlinkBridge stream info
            let blinkBridgeStream = null;
            try {
                const bbResponse = await fetch('/api/blinkbridge/streams');
                if (bbResponse.ok) {
                    const streams = await bbResponse.json();
                    blinkBridgeStream = streams[cameraName] || null;
                }
            } catch (e) {
                console.warn('Failed to load BlinkBridge stream info:', e);
            }
            
            // Get current state
            const camera = this.findCamera(cameraName);
            if (!camera) {
                this.showMessage('Camera not found', 'error');
                return;
            }
            
            // Info tab content
            const infoContent = `
                <div class="info-grid">
                    <div class="info-row">
                        <div class="info-label">Status</div>
                        <div class="info-value">${info.status || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Armed</div>
                        <div class="info-value">${camera.arm ? 'Yes' : 'No'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Snoozed</div>
                        <div class="info-value">${camera.snooze ? 'Yes' : 'No'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Motion</div>
                        <div class="info-value">${info.enabled === true ? 'Enabled' : 'Disabled'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Battery</div>
                        <div class="info-value">${info.battery || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">WiFi</div>
                        <div class="info-value">${info.wifi_strength || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Temp</div>
                        <div class="info-value">${info.temperature || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Type</div>
                        <div class="info-value">${info.product_type || info.type || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Camera ID</div>
                        <div class="info-value">${info.camera_id || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Serial</div>
                        <div class="info-value">${info.serial || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Firmware</div>
                        <div class="info-value">${info.fw_version || 'N/A'}</div>
                    </div>
                    <div class="info-row">
                        <div class="info-label">Network ID</div>
                        <div class="info-value">${info.network_id || 'N/A'}</div>
                    </div>
                    ${blinkBridgeStream ? `
                        <div class="info-row" style="background: rgba(59, 130, 246, 0.05); border-top: 2px solid var(--primary);">
                            <div class="info-label" style="display: flex; align-items: center; gap: 0.25rem;">
                                📡 RTSP Stream
                                <span style="font-size: 0.75rem; color: ${blinkBridgeStream.running ? '#22c55e' : '#ef4444'};">
                                    ${blinkBridgeStream.running ? '● Live' : '● Offline'}
                                </span>
                            </div>
                            <div class="info-value" style="font-family: monospace; font-size: 0.75rem; word-break: break-all;">
                                ${this.escapeHtml(blinkBridgeStream.rtsp_url)}
                                <button class="btn btn-sm" onclick="navigator.clipboard.writeText('${blinkBridgeStream.rtsp_url}'); app.showMessage('RTSP URL copied!', 'success');" 
                                        style="margin-left: 0.5rem; padding: 0.25rem 0.5rem; font-size: 0.75rem;" title="Copy RTSP URL">
                                    Copy
                                </button>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;
            
            // Settings tab content
            const settingsContent = `
                <div>
                    <div class="setting-row" onclick="app.toggleCheckbox('cameraSnooze', event)">
                        <div class="setting-info">
                            <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-bell-off"/></svg>Snooze Motion</div>
                            <div class="setting-description">Disable motion detection</div>
                        </div>
                        <label class="toggle" onclick="event.stopPropagation()">
                            <input type="checkbox" id="cameraSnooze" ${camera.snooze ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div style="padding: 0.5rem 1rem 1rem 1rem; border-bottom: 1px solid var(--border); background: var(--surface-secondary);">
                        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                            <label class="form-label" style="font-size: 0.875rem; margin-bottom: 0;">Duration</label>
                            <select id="cameraSnoozeDuration" class="form-select" style="font-size: 0.875rem;">
                                <option value="1">1 Hour</option>
                                <option value="2" selected>2 Hours</option>
                                <option value="4">4 Hours</option>
                                <option value="8">8 Hours</option>
                                <option value="24">24 Hours</option>
                            </select>
                            <small style="color: var(--text-secondary); font-size: 0.75rem;">Will auto-unsnooze after this time. Use schedules for indefinite changes.</small>
                        </div>
                    </div>
                    <div class="setting-row" onclick="app.toggleCheckbox('cameraArm', event)">
                        <div class="setting-info">
                            <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-armed"/></svg>Arm Camera</div>
                            <div class="setting-description">Enable motion detection</div>
                        </div>
                        <label class="toggle" onclick="event.stopPropagation()">
                            <input type="checkbox" id="cameraArm" ${camera.arm ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                    <div style="padding: 0.5rem 1rem 1rem 1rem; border-bottom: 1px solid var(--border); background: var(--surface-secondary);">
                        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                            <label class="form-label" style="font-size: 0.875rem; margin-bottom: 0;">Duration</label>
                            <select id="cameraArmDuration" class="form-select" style="font-size: 0.875rem;">
                                <option value="1">1 Hour</option>
                                <option value="2" selected>2 Hours</option>
                                <option value="4">4 Hours</option>
                                <option value="8">8 Hours</option>
                                <option value="24">24 Hours</option>
                            </select>
                            <small style="color: var(--text-secondary); font-size: 0.75rem;">Will auto-disarm after this time. Use schedules for indefinite changes.</small>
                        </div>
                    </div>
                    <div style="padding: 1rem 0.5rem; border-bottom: 1px solid var(--border);">
                        <div class="setting-label" style="margin-bottom: 0.5rem;"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-snoozed"/></svg>Night Vision</div>
                        <select id="cameraNightVision" class="form-input" style="width: 100%;">
                            <option value="auto" ${nightVisionMode === 'auto' ? 'selected' : ''}>Auto</option>
                            <option value="on" ${nightVisionMode === 'on' ? 'selected' : ''}>Always On</option>
                            <option value="off" ${nightVisionMode === 'off' ? 'selected' : ''}>Always Off</option>
                        </select>
                    </div>
                    <div style="padding: 1rem 0.5rem;">
                        <div class="setting-label" style="margin-bottom: 0.75rem;">Actions</div>
                        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                            <button class="btn btn-secondary" onclick="app.captureNewThumbnail('${this.escapeHtml(camera.name)}')" style="flex: 1; min-width: 140px;" title="Capture a new thumbnail image from the camera">
                                <svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-photo"/></svg>Take Snapshot
                            </button>
                            <button class="btn btn-secondary" onclick="app.startRecording('${this.escapeHtml(camera.name)}')" style="flex: 1; min-width: 140px;" title="Record a new video clip">
                                <svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-video"/></svg>Start Recording
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            // Media tab content with sub-tabs for clips and thumbnails
            const mediaContent = `
                <div class="media-content">
                    <div class="media-subtabs">
                        <button class="media-subtab active" onclick="app.switchMediaTab('${this.escapeHtml(cameraName)}', 'clips', event)"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-video"/></svg>Clips</button>
                        <button class="media-subtab" onclick="app.switchMediaTab('${this.escapeHtml(cameraName)}', 'thumbnails', event)"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-photo"/></svg>Thumbnails</button>
                    </div>
                    <div class="media-subtab-content">
                        <div id="mediaClipsTab" class="media-tab-panel active">
                            <div class="media-loading">Loading clips...</div>
                        </div>
                        <div id="mediaThumbnailsTab" class="media-tab-panel">
                            <div class="media-loading">Loading thumbnails...</div>
                        </div>
                    </div>
                </div>
            `;
            
            // Stats tab content
            const statsContent = `
                <div style="padding: 1rem;">
                    <div style="margin-bottom: 1.5rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                            <div style="font-weight: 600; font-size: 1.1rem;"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-battery"/></svg>Battery History</div>
                            <button class="btn btn-secondary" onclick="app.downloadCameraModalBatteryCSV()" style="padding: 0.5rem 1rem; font-size: 0.875rem;">
                                <svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-download"/></svg>CSV
                            </button>
                        </div>
                        <div style="margin-bottom: 0.75rem;">
                            <label class="form-label" style="font-size: 0.875rem;">Time Range</label>
                            <select id="modalBatteryTimeRange" class="form-select" onchange="app.loadCameraModalBatteryHistory('${this.escapeHtml(cameraName)}')">
                                <option value="24">Last 24 Hours</option>
                                <option value="168">Last 7 Days</option>
                                <option value="720" selected>Last 30 Days</option>
                                <option value="2160">Last 90 Days</option>
                            </select>
                        </div>
                        <div style="background: var(--surface); padding: 1rem; border-radius: 8px; height: 250px;">
                            <canvas id="modalBatteryChart"></canvas>
                        </div>
                        <div id="modalBatteryTimeScale" style="text-align: center; margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-secondary);"></div>
                        <div id="modalBatteryStats" style="margin-top: 1rem; display: none;">
                            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;">
                                <div style="text-align: center;">
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Average</div>
                                    <div id="modalAvgVoltage" style="font-size: 1.1rem; font-weight: 600; color: var(--primary);">-</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Min</div>
                                    <div id="modalMinVoltage" style="font-size: 1.1rem; font-weight: 600; color: var(--error);">-</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Max</div>
                                    <div id="modalMaxVoltage" style="font-size: 1.1rem; font-weight: 600; color: var(--success);">-</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div style="margin-bottom: 1.5rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                            <div style="font-weight: 600; font-size: 1.1rem;"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-signal"/></svg>Status History</div>
                            <button class="btn btn-secondary" onclick="app.downloadCameraModalStatusCSV()" style="padding: 0.5rem 1rem; font-size: 0.875rem;">
                                <svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-download"/></svg>CSV
                            </button>
                        </div>
                        <div style="margin-bottom: 0.75rem;">
                            <label class="form-label" style="font-size: 0.875rem;">Time Range</label>
                            <select id="modalStatusTimeRange" class="form-select" onchange="app.loadCameraModalStatusHistory('${this.escapeHtml(cameraName)}')">
                                <option value="24">Last 24 Hours</option>
                                <option value="168">Last 7 Days</option>
                                <option value="720" selected>Last 30 Days</option>
                                <option value="2160">Last 90 Days</option>
                            </select>
                        </div>
                        <div style="background: var(--surface); padding: 1rem; border-radius: 8px; height: 250px;">
                            <canvas id="modalStatusChart"></canvas>
                        </div>
                        <div id="modalStatusTimeScale" style="text-align: center; margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-secondary);"></div>
                        <div id="modalStatusStats" style="margin-top: 1rem; display: none;">
                            <div style="background: var(--surface-secondary); padding: 1rem; border-radius: 8px;">
                                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;">
                                    <div style="text-align: center;">
                                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Uptime</div>
                                        <div id="modalUptimePercent" style="font-size: 1.3rem; font-weight: 600; color: var(--success);">-</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Online</div>
                                        <div id="modalOnlineTime" style="font-size: 1.1rem; font-weight: 600; color: var(--primary);">-</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Offline</div>
                                        <div id="modalOfflineTime" style="font-size: 1.1rem; font-weight: 600; color: var(--error);">-</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            const tabs = [
                { title: 'Info', content: infoContent },
                { title: 'Settings', content: settingsContent },
                { title: 'Media', content: mediaContent },
                { title: 'Stats', content: statsContent }
            ];
            
            const footer = `
                <button class="btn btn-secondary" onclick="app.closeModal()">Cancel</button>
                <button class="btn" onclick="app.saveCameraSettings('${this.escapeHtml(cameraName)}')">Save Settings</button>
            `;
            
            this.showTabbedModal(cameraName, tabs, footer);
            
            // Store camera name for media tab loading
            this.currentCameraName = cameraName;
        } catch (error) {
            this.showMessage('Failed to load camera modal: ' + error.message, 'error');
        }
    }
    
    async showCameraSettings(cameraName, syncName) {
        const camera = this.findCamera(cameraName);
        if (!camera) {
            this.showMessage('Camera not found', 'error');
            return;
        }
        
        const content = `
            <div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-bell-off"/></svg>Snooze Motion</div>
                        <div class="setting-description">Disable detection for 5 minutes</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" id="cameraSnooze" ${camera.snooze ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-armed"/></svg>Arm Camera</div>
                        <div class="setting-description">Enable motion detection</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" id="cameraArm" ${camera.arm ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-photo"/></svg>Thumbnails</div>
                        <div class="setting-description">Capture periodic snapshots</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" id="cameraThumbnail" ${camera.thumbnail ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            </div>
        `;
        
        const footer = `
            <button class="btn btn-secondary" onclick="app.closeModal()">Cancel</button>
            <button class="btn" onclick="app.saveCameraSettings('${this.escapeHtml(cameraName)}')">Save Settings</button>
        `;
        
        this.showModal(`${cameraName} Settings`, content, footer);
    }
    
    async saveCameraSettings(cameraName) {
        const snooze = document.getElementById('cameraSnooze').checked;
        const arm = document.getElementById('cameraArm').checked;
        const nightVision = document.getElementById('cameraNightVision').value;
        const snoozeDuration = parseFloat(document.getElementById('cameraSnoozeDuration').value);
        const armDuration = parseFloat(document.getElementById('cameraArmDuration').value);
        
        this.closeModal();
        this.showMessage('Saving camera settings...', 'info');
        
        try {
            // Apply snooze with duration (always has a duration now)
            await fetch(`/api/camera/${encodeURIComponent(cameraName)}/snooze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    enabled: snooze,
                    duration_hours: snooze ? snoozeDuration : null
                })
            });
            
            // Apply arm with duration (always has a duration now)
            await fetch(`/api/camera/${encodeURIComponent(cameraName)}/arm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    enabled: arm,
                    duration_hours: arm ? armDuration : null
                })
            });
            
            await fetch(`/api/camera/${encodeURIComponent(cameraName)}/night_vision`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: nightVision })
            });
            
            await this.loadData();
            
            // Show message with duration info
            let message = 'Camera settings saved';
            if (snooze) {
                message += ` (snoozed for ${snoozeDuration}h)`;
            }
            if (arm) {
                message += ` (armed for ${armDuration}h)`;
            }
            this.showMessage(message, 'success');
        } catch (error) {
            this.showMessage('Failed to save camera settings: ' + error.message, 'error');
        }
    }
    
    async switchMediaTab(cameraName, tabType, event) {
        if (event) event.stopPropagation();
        
        // Update subtab buttons
        const subtabs = document.querySelectorAll('.media-subtab');
        subtabs.forEach(tab => tab.classList.remove('active'));
        event.target.classList.add('active');
        
        // Update subtab content
        const panels = document.querySelectorAll('.media-tab-panel');
        panels.forEach(panel => panel.classList.remove('active'));
        
        if (tabType === 'clips') {
            document.getElementById('mediaClipsTab').classList.add('active');
            await this.loadCameraClips(cameraName);
        } else {
            document.getElementById('mediaThumbnailsTab').classList.add('active');
            await this.loadCameraThumbnails(cameraName);
        }
    }
    
    async loadCameraClips(cameraName) {
        const container = document.getElementById('mediaClipsTab');
        container.innerHTML = '<div class="media-loading">Loading clips...</div>';
        
        try {
            const response = await fetch(`/api/media/camera/${encodeURIComponent(cameraName)}/clips`);
            if (!response.ok) throw new Error('Failed to load clips');
            
            const data = await response.json();
            
            // Check if media saving is disabled
            if (data.disabled || (data.message && data.clips.length === 0)) {
                const messageClass = data.disabled ? 'media-error' : 'media-empty';
                container.innerHTML = `<div class="${messageClass}">${this.escapeHtml(data.message)}</div>`;
                return;
            }
            
            const clips = data.clips || [];
            
            if (clips.length === 0) {
                const message = data.message || 'No clips saved yet';
                container.innerHTML = `<div class="media-empty">${this.escapeHtml(message)}</div>`;
                return;
            }
            
            const grid = clips.map(clip => {
                const date = this.formatDateTime(clip.modified);
                const size = this.formatFileSize(clip.size);
                const displayTitle = this.formatTimestampFromFilename(clip.filename);
                
                // Use actual video thumbnail if available, otherwise show play button
                const thumbnailContent = clip.thumbnail 
                    ? `<img src="${this.escapeHtml(clip.thumbnail)}" alt="${this.escapeHtml(clip.filename)}" loading="lazy">
                       <div class="video-play-icon">▶</div>`
                    : `<div class="video-play-icon">▶</div>
                       <div class="video-duration">Video</div>`;
                
                return `
                    <div class="media-item" onclick="app.showMediaViewer('${this.escapeHtml(clip.path)}', 'video', '${this.escapeHtml(clip.filename)}')">
                        <div class="media-thumbnail video-thumbnail">
                            ${thumbnailContent}
                        </div>
                        <div class="media-info">
                            <div class="media-filename" title="${this.escapeHtml(clip.filename)}">${this.escapeHtml(displayTitle)}</div>
                            <div class="media-meta">${date} • ${size}</div>
                        </div>
                    </div>
                `;
            }).join('');
            
            container.innerHTML = `<div class="media-grid">${grid}</div>`;
        } catch (error) {
            container.innerHTML = `<div class="media-error">Failed to load clips: ${this.escapeHtml(error.message)}</div>`;
        }
    }
    
    async loadCameraThumbnails(cameraName) {
        const container = document.getElementById('mediaThumbnailsTab');
        container.innerHTML = '<div class="media-loading">Loading thumbnails...</div>';
        
        try {
            const response = await fetch(`/api/media/camera/${encodeURIComponent(cameraName)}/thumbnails`);
            if (!response.ok) throw new Error('Failed to load thumbnails');
            
            const data = await response.json();
            
            // Check if media saving is disabled
            if (data.disabled || (data.message && data.thumbnails.length === 0)) {
                const messageClass = data.disabled ? 'media-error' : 'media-empty';
                container.innerHTML = `<div class="${messageClass}">${this.escapeHtml(data.message)}</div>`;
                return;
            }
            
            const thumbnails = data.thumbnails || [];
            
            if (thumbnails.length === 0) {
                const message = data.message || 'No thumbnails saved yet';
                container.innerHTML = `<div class="media-empty">${this.escapeHtml(message)}</div>`;
                return;
            }
            
            const grid = thumbnails.map(thumb => {
                const date = this.formatDateTime(thumb.modified);
                const size = this.formatFileSize(thumb.size);
                const displayTitle = this.formatTimestampFromFilename(thumb.filename);
                return `
                    <div class="media-item" onclick="app.showMediaViewer('${this.escapeHtml(thumb.path)}', 'image', '${this.escapeHtml(thumb.filename)}')">
                        <div class="media-thumbnail">
                            <img src="${this.escapeHtml(thumb.path)}" alt="${this.escapeHtml(thumb.filename)}" loading="lazy">
                        </div>
                        <div class="media-info">
                            <div class="media-filename" title="${this.escapeHtml(thumb.filename)}">${this.escapeHtml(displayTitle)}</div>
                            <div class="media-meta">${date} • ${size}</div>
                        </div>
                    </div>
                `;
            }).join('');
            
            container.innerHTML = `<div class="media-grid">${grid}</div>`;
        } catch (error) {
            container.innerHTML = `<div class="media-error">Failed to load thumbnails: ${this.escapeHtml(error.message)}</div>`;
        }
    }
    
    showMediaViewer(path, type, filename) {
        const displayTitle = this.formatTimestampFromFilename(filename);
        const mediaElement = type === 'video' 
            ? `<video controls autoplay style="max-width: 100%; max-height: 70vh;">
                   <source src="${this.escapeHtml(path)}" type="video/mp4">
                   Your browser does not support video playback.
               </video>`
            : `<img src="${this.escapeHtml(path)}" alt="${this.escapeHtml(filename)}" style="max-width: 100%; max-height: 70vh; object-fit: contain;">`;
        
        const content = `
            <div style="text-align: center;">
                ${mediaElement}
            </div>
        `;
        
        const footer = `
            <button class="btn btn-secondary" onclick="app.closeModal()">Close</button>
            <a href="${this.escapeHtml(path)}" download="${this.escapeHtml(filename)}" class="btn"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-download"/></svg>Download</a>
        `;
        
        this.showModal(displayTitle, content, footer);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }
    
    formatTimestampFromFilename(filename) {
        // Extract timestamp from filename format: YYYYMMDD_HHMMSS.ext
        const match = filename.match(/(\d{8})_(\d{6})/);
        if (!match) return filename; // Fallback to filename if format doesn't match
        
        const dateStr = match[1]; // YYYYMMDD
        const timeStr = match[2]; // HHMMSS
        
        const year = dateStr.substring(0, 4);
        const month = dateStr.substring(4, 6);
        const day = dateStr.substring(6, 8);
        const hour = timeStr.substring(0, 2);
        const minute = timeStr.substring(2, 4);
        const second = timeStr.substring(4, 6);
        
        // Create date object
        const date = new Date(`${year}-${month}-${day}T${hour}:${minute}:${second}`);
        
        // Get time format preference (default to 12h if not set)
        const use24Hour = this.config.web_time_format === '24h';
        
        // Format as readable string
        const options = {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            second: '2-digit',
            hour12: !use24Hour
        };
        
        return date.toLocaleString('en-US', options);
    }
    
    formatDateTime(timestamp) {
        // Format a timestamp according to user's time format preference
        const date = new Date(timestamp * 1000);
        const use24Hour = this.config.web_time_format === '24h';
        
        const options = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: 'numeric',
            minute: '2-digit',
            second: '2-digit',
            hour12: !use24Hour
        };
        
        return date.toLocaleString('en-US', options);
    }
    
    async showSyncInfo(syncName) {
        const sync = this.state.syncs.find(s => s.name === syncName);
        if (!sync) {
            this.showMessage('Sync module not found', 'error');
            return;
        }
        
        const content = `
            <div class="info-grid">
                <div class="info-row">
                    <div class="info-label">Armed</div>
                    <div class="info-value">${sync.arm ? 'Yes' : 'No'}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Snoozed</div>
                    <div class="info-value">${sync.snooze ? 'Yes' : 'No'}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Cameras</div>
                    <div class="info-value">${sync.cameras.length}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Camera List</div>
                    <div class="info-value">${sync.cameras.map(c => c.name).join(', ')}</div>
                </div>
            </div>
        `;
        
        this.showModal(`🔗 ${syncName}`, content);
    }
    
    async showSyncModal(syncName) {
        const sync = this.state.syncs.find(s => s.name === syncName);
        if (!sync) {
            this.showMessage('Sync module not found', 'error');
            return;
        }
        
        // Info tab content
        const infoContent = `
            <div class="info-grid">
                <div class="info-row">
                    <div class="info-label">Armed</div>
                    <div class="info-value">${sync.arm ? 'Yes' : 'No'}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Snoozed</div>
                    <div class="info-value">${sync.snooze ? 'Yes' : 'No'}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Cameras</div>
                    <div class="info-value">${sync.cameras.length}</div>
                </div>
                <div class="info-row">
                    <div class="info-label">Camera List</div>
                    <div class="info-value">${sync.cameras.map(c => c.name).join(', ')}</div>
                </div>
            </div>
        `;
        
        // Settings tab content
        const settingsContent = `
            <div>
                <div class="setting-row" onclick="app.toggleCheckbox('syncSnooze', event)">
                    <div class="setting-info">
                        <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-bell-off"/></svg>Snooze All</div>
                        <div class="setting-description">Disable all cameras</div>
                    </div>
                    <label class="toggle" onclick="event.stopPropagation()">
                        <input type="checkbox" id="syncSnooze" ${sync.snooze ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div style="padding: 0.5rem 1rem 1rem 1rem; border-bottom: 1px solid var(--border); background: var(--surface-secondary);">
                    <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                        <label class="form-label" style="font-size: 0.875rem; margin-bottom: 0;">Duration</label>
                        <select id="syncSnoozeDuration" class="form-select" style="font-size: 0.875rem;">
                            <option value="1">1 Hour</option>
                            <option value="2" selected>2 Hours</option>
                            <option value="4">4 Hours</option>
                            <option value="8">8 Hours</option>
                            <option value="24">24 Hours</option>
                        </select>
                        <small style="color: var(--text-secondary); font-size: 0.75rem;">Will auto-unsnooze all cameras after this time. Use schedules for indefinite changes.</small>
                    </div>
                </div>
                <div class="setting-row" onclick="app.toggleCheckbox('syncArm', event)">
                    <div class="setting-info">
                        <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-armed"/></svg>Arm All</div>
                        <div class="setting-description">Enable all cameras</div>
                    </div>
                    <label class="toggle" onclick="event.stopPropagation()">
                        <input type="checkbox" id="syncArm" ${sync.arm ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div style="padding: 0.5rem 1rem 1rem 1rem; border-bottom: 1px solid var(--border); background: var(--surface-secondary);">
                    <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                        <label class="form-label" style="font-size: 0.875rem; margin-bottom: 0;">Duration</label>
                        <select id="syncArmDuration" class="form-select" style="font-size: 0.875rem;">
                            <option value="1">1 Hour</option>
                            <option value="2" selected>2 Hours</option>
                            <option value="4">4 Hours</option>
                            <option value="8">8 Hours</option>
                            <option value="24">24 Hours</option>
                        </select>
                        <small style="color: var(--text-secondary); font-size: 0.75rem;">Will auto-disarm all cameras after this time. Use schedules for indefinite changes.</small>
                    </div>
                </div>
            </div>
        `;
        
        // Stats tab content (uptime only, no battery for sync modules)
        const statsContent = `
            <div style="padding: 1rem;">
                <div style="margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                        <div style="font-weight: 600; font-size: 1.1rem;"><svg class="icon" style="margin-right: 0.5rem;"><use href="#icon-signal"/></svg>Uptime History</div>
                        <button class="btn btn-secondary" onclick="app.downloadSyncModalStatusCSV()" style="padding: 0.5rem 1rem; font-size: 0.875rem;">
                            <svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-download"/></svg>CSV
                        </button>
                    </div>
                    <div style="margin-bottom: 0.75rem;">
                        <label class="form-label" style="font-size: 0.875rem;">Time Range</label>
                        <select id="modalSyncStatusTimeRange" class="form-select" onchange="app.loadSyncModalStatusHistory('${this.escapeHtml(syncName)}')">
                            <option value="24">Last 24 Hours</option>
                            <option value="168">Last 7 Days</option>
                            <option value="720" selected>Last 30 Days</option>
                            <option value="2160">Last 90 Days</option>
                        </select>
                    </div>
                    <div style="background: var(--surface); padding: 1rem; border-radius: 8px; height: 250px;">
                        <canvas id="modalSyncStatusChart"></canvas>
                    </div>
                    <div id="modalSyncStatusTimeScale" style="text-align: center; margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-secondary);"></div>
                    <div id="modalSyncStatusStats" style="margin-top: 1rem; display: none;">
                        <div style="background: var(--surface-secondary); padding: 1rem; border-radius: 8px;">
                            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;">
                                <div style="text-align: center;">
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Uptime</div>
                                    <div id="modalSyncUptimePercent" style="font-size: 1.3rem; font-weight: 600; color: var(--success);">-</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Online</div>
                                    <div id="modalSyncOnlineTime" style="font-size: 1.1rem; font-weight: 600; color: var(--primary);">-</div>
                                </div>
                                <div style="text-align: center;">
                                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Offline</div>
                                    <div id="modalSyncOfflineTime" style="font-size: 1.1rem; font-weight: 600; color: var(--error);">-</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        const tabs = [
            { title: 'Info', content: infoContent },
            { title: 'Settings', content: settingsContent },
            { title: 'Stats', content: statsContent }
        ];
        
        const footer = `
            <button class="btn btn-secondary" onclick="app.closeModal()">Cancel</button>
            <button class="btn" onclick="app.saveSyncSettings('${this.escapeHtml(syncName)}')">Save Settings</button>
        `;
        
        this.showTabbedModal(syncName, tabs, footer);
        
        // Store sync name for stats tab loading
        this.currentSyncName = syncName;
        this.currentCameraName = null; // Clear camera name to indicate this is a sync modal
    }
    
    async showSyncSettings(syncName) {
        const sync = this.state.syncs.find(s => s.name === syncName);
        if (!sync) {
            this.showMessage('Sync module not found', 'error');
            return;
        }
        
        const content = `
            <div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-bell-off"/></svg>Snooze All</div>
                        <div class="setting-description">Disable all cameras for 4 minutes</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" id="syncSnooze" ${sync.snooze ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-label"><svg class="icon-sm" style="margin-right: 0.5rem;"><use href="#icon-armed"/></svg>Arm All</div>
                        <div class="setting-description">Enable all cameras</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" id="syncArm" ${sync.arm ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            </div>
        `;
        
        const footer = `
            <button class="btn btn-secondary" onclick="app.closeModal()">Cancel</button>
            <button class="btn" onclick="app.saveSyncSettings('${this.escapeHtml(syncName)}')">Save Settings</button>
        `;
        
        this.showModal(`${syncName} Settings`, content, footer);
    }
    
    async saveSyncSettings(syncName) {
        const snooze = document.getElementById('syncSnooze').checked;
        const arm = document.getElementById('syncArm').checked;
        const snoozeDuration = parseFloat(document.getElementById('syncSnoozeDuration').value);
        const armDuration = parseFloat(document.getElementById('syncArmDuration').value);
        
        this.closeModal();
        this.showMessage('Saving sync module settings...', 'info');
        
        try {
            // Apply snooze with duration (always has a duration now)
            await fetch(`/api/sync/${encodeURIComponent(syncName)}/snooze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    enabled: snooze,
                    duration_hours: snooze ? snoozeDuration : null
                })
            });
            
            // Apply arm with duration (always has a duration now)
            await fetch(`/api/sync/${encodeURIComponent(syncName)}/arm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    enabled: arm,
                    duration_hours: arm ? armDuration : null
                })
            });
            
            await this.loadData();
            
            // Show message with duration info
            let message = 'Sync module settings saved';
            if (snooze) {
                message += ` (snoozed for ${snoozeDuration}h)`;
            }
            if (arm) {
                message += ` (armed for ${armDuration}h)`;
            }
            this.showMessage(message, 'success');
        } catch (error) {
            this.showMessage('Failed to save sync settings: ' + error.message, 'error');
        }
    }
    
    async loadSyncModalStatusHistory(syncName) {
        const hours = document.getElementById('modalSyncStatusTimeRange').value;
        
        if (!syncName) {
            return;
        }
        
        try {
            const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
            const response = await fetch(`/api/history/status/${encodeURIComponent(syncName)}?since=${encodeURIComponent(since)}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load status history');
            }
            
            const data = await response.json();
            const history = data.history || [];
            
            // Store for CSV export
            this.currentSyncModalStatusData = history;
            
            if (history.length === 0) {
                document.getElementById('modalSyncStatusTimeScale').textContent = 'No data available';
                return;
            }
            
            // Update chart with relative time labels
            const labels = history.map(h => {
                const date = new Date(h.timestamp);
                return this.formatRelativeTime(date, parseInt(hours));
            });
            const statusValues = history.map(h => h.is_online ? 1 : 0);
            
            this.syncModalStatusChart.data.labels = labels;
            this.syncModalStatusChart.data.datasets[0].data = statusValues;
            this.syncModalStatusChart.update();
            
            // Update time scale indicator
            this.updateTimeScaleModal('modalSyncStatusTimeScale', history, parseInt(hours));
            
            // Load and display stats
            await this.loadSyncModalStatusStats(syncName, hours);
            
        } catch (error) {
            this.showMessage('Failed to load status history: ' + error.message, 'error');
        }
    }
    
    async loadSyncModalStatusStats(syncName, hours) {
        try {
            const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
            const response = await fetch(`/api/history/status/${encodeURIComponent(syncName)}/stats?since=${encodeURIComponent(since)}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load status stats');
            }
            
            const stats = await response.json();
            
            document.getElementById('modalSyncUptimePercent').textContent = stats.uptime_percentage.toFixed(1) + '%';
            document.getElementById('modalSyncOnlineTime').textContent = this.formatDuration(stats.total_online_minutes);
            document.getElementById('modalSyncOfflineTime').textContent = this.formatDuration(stats.total_offline_minutes);
            document.getElementById('modalSyncStatusStats').style.display = 'block';
            
        } catch (error) {
            console.error('Failed to load status stats:', error);
        }
    }
    
    downloadSyncModalStatusCSV() {
        if (!this.currentSyncModalStatusData || this.currentSyncModalStatusData.length === 0) {
            this.showMessage('No data to download', 'error');
            return;
        }
        
        // Create CSV content
        let csv = 'Timestamp,Status,Signal Strength,Temperature\n';
        this.currentSyncModalStatusData.forEach(row => {
            const timestamp = new Date(row.timestamp).toISOString();
            const status = row.is_online ? 'Online' : 'Offline';
            const signal = row.signal_strength || 'N/A';
            const temp = row.temperature || 'N/A';
            csv += `${timestamp},${status},${signal},${temp}\n`;
        });
        
        // Create download link
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `sync-status-history-${Date.now()}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        this.showMessage('CSV downloaded successfully', 'success');
    }
    
    findCamera(cameraName) {
        for (const sync of this.state.syncs) {
            const camera = sync.cameras.find(c => c.name === cameraName);
            if (camera) return camera;
        }
        return null;
    }

    
    async refresh() {
        // Check if configured first
        if (this.state.configured === false) {
            this.showMessage('System not configured yet', 'error');
            return;
        }
        
        this.showLoading('Refreshing cameras...');
        this.showMessage('Refreshing camera state...', 'info');
        try {
            const response = await fetch('/api/refresh', { method: 'POST' });
            if (!response.ok) throw new Error('Refresh failed');
            await this.loadData();
            this.renderTabContent(this.activeTab);
            this.showMessage('Refreshed successfully!', 'success');
        } catch (error) {
            this.showMessage('Refresh failed: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async runJobs() {
        this.showLoading('Running scheduled jobs...');
        this.showMessage('Running scheduled jobs...', 'info');
        try {
            const response = await fetch('/api/run-jobs', { method: 'POST' });
            if (!response.ok) throw new Error('Run jobs failed');
            this.showMessage('Jobs completed successfully!', 'success');
        } catch (error) {
            this.showMessage('Run jobs failed: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
    }
    
    async logout() {
        this.closeMenu();
        try {
            const response = await fetch('/auth/logout', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (response.ok) {
                window.location.href = '/auth/login';
            } else {
                this.showMessage('Logout failed', 'error');
            }
        } catch (error) {
            this.showMessage('Logout failed: ' + error.message, 'error');
        }
    }
    
    showMessage(message, type = 'info') {
        const area = document.getElementById('messageArea');
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        
        // Add to message area
        area.appendChild(toast);
        
        // Auto-remove after 5 seconds with animation
        setTimeout(() => {
            toast.classList.add('hiding');
            setTimeout(() => {
                if (toast.parentNode === area) {
                    area.removeChild(toast);
                }
            }, 300); // Match animation duration
        }, 5000);
    }

    /**
     * Show a custom confirmation dialog
     * @param {string} title - Dialog title
     * @param {string} message - Dialog message (can include HTML)
     * @param {Object} options - Options for the dialog
     * @param {string} options.confirmText - Text for confirm button (default: 'Confirm')
     * @param {string} options.cancelText - Text for cancel button (default: 'Cancel')
     * @param {string} options.confirmClass - CSS class for confirm button (default: 'btn-danger')
     * @returns {Promise<boolean>} - Resolves to true if confirmed, false if cancelled
     */
    showConfirm(title, message, options = {}) {
        return new Promise((resolve) => {
            const {
                confirmText = 'Confirm',
                cancelText = 'Cancel',
                confirmClass = 'btn-danger'
            } = options;

            const modalHTML = `
                <div class="modal-overlay" id="confirmModal" style="display: flex;">
                    <div class="modal" style="max-width: 500px;">
                        <div class="modal-header">
                            <h2 class="modal-title">${this.escapeHtml(title)}</h2>
                        </div>
                        <div class="modal-body" style="padding: 20px;">
                            <div style="white-space: pre-wrap; line-height: 1.6;">${message}</div>
                        </div>
                        <div class="modal-footer" style="display: flex; gap: 10px; justify-content: flex-end; padding: 15px 20px;">
                            <button class="btn" id="confirmCancel">${this.escapeHtml(cancelText)}</button>
                            <button class="btn ${confirmClass}" id="confirmOk">${this.escapeHtml(confirmText)}</button>
                        </div>
                    </div>
                </div>
            `;

            const container = document.getElementById('modalContainer');
            container.innerHTML = modalHTML;

            const modal = document.getElementById('confirmModal');
            const confirmBtn = document.getElementById('confirmOk');
            const cancelBtn = document.getElementById('confirmCancel');

            const cleanup = (result) => {
                modal.style.display = 'none';
                container.innerHTML = '';
                resolve(result);
            };

            confirmBtn.addEventListener('click', () => cleanup(true));
            cancelBtn.addEventListener('click', () => cleanup(false));
            modal.addEventListener('click', (e) => {
                if (e.target === modal) cleanup(false);
            });
        });
    }

    /**
     * Show a custom alert dialog
     * @param {string} title - Dialog title
     * @param {string} message - Dialog message
     * @returns {Promise<void>}
     */
    showAlert(title, message) {
        return new Promise((resolve) => {
            const modalHTML = `
                <div class="modal-overlay" id="alertModal" style="display: flex;">
                    <div class="modal" style="max-width: 500px;">
                        <div class="modal-header">
                            <h2 class="modal-title">${this.escapeHtml(title)}</h2>
                        </div>
                        <div class="modal-body" style="padding: 20px;">
                            <div style="white-space: pre-wrap; line-height: 1.6;">${this.escapeHtml(message)}</div>
                        </div>
                        <div class="modal-footer" style="display: flex; justify-content: flex-end; padding: 15px 20px;">
                            <button class="btn" id="alertOk">OK</button>
                        </div>
                    </div>
                </div>
            `;

            const container = document.getElementById('modalContainer');
            container.innerHTML = modalHTML;

            const modal = document.getElementById('alertModal');
            const okBtn = document.getElementById('alertOk');

            const cleanup = () => {
                modal.style.display = 'none';
                container.innerHTML = '';
                resolve();
            };

            okBtn.addEventListener('click', cleanup);
            modal.addEventListener('click', (e) => {
                if (e.target === modal) cleanup();
            });
        });
    }
    
    
    toggleCheckbox(checkboxId, event) {
        if (event) {
            event.stopPropagation();
        }
        const checkbox = document.getElementById(checkboxId);
        if (checkbox) {
            checkbox.checked = !checkbox.checked;
        }
    }
    
    async captureNewThumbnail(cameraName) {
        this.closeModal();
        this.showLoading('Capturing new thumbnail...');
        
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/media/thumbnail/new`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showMessage('Thumbnail captured! Fetching new image...', 'success');
                
                // Wait a moment for the thumbnail to be ready
                await new Promise(resolve => setTimeout(resolve, 2000));
                
                // Fetch the new thumbnail
                const thumbResponse = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/media/thumbnail`);
                if (thumbResponse.ok) {
                    const blob = await thumbResponse.blob();
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        const dataUrl = reader.result;
                        this.saveThumbnailToCache(cameraName, dataUrl);
                        this.updateThumbnailDisplay(cameraName, dataUrl);
                        this.showMessage('Thumbnail updated successfully!', 'success');
                    };
                    reader.readAsDataURL(blob);
                }
                
                // Refresh state
                await this.loadData();
            } else {
                const error = await response.json();
                this.showMessage('Failed to capture thumbnail: ' + (error.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            this.showMessage('Failed to capture thumbnail: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async startRecording(cameraName) {
        this.closeModal();
        this.showLoading('Starting video recording...');
        
        try {
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/record`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.showMessage('Recording started! Video will be available in clips shortly.', 'success');
                // Refresh state to show updated data
                await this.loadData();
            } else {
                const error = await response.json();
                this.showMessage('Failed to start recording: ' + (error.error || 'Unknown error'), 'error');
            }
        } catch (error) {
            this.showMessage('Failed to start recording: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    // Loading Overlay
    showLoading(message = 'Processing...') {
        const overlay = document.getElementById('loadingOverlay');
        const text = document.getElementById('loadingText');
        text.textContent = message;
        overlay.classList.add('active');
    }
    
    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        overlay.classList.remove('active');
    }
    
    // Thumbnail Caching - use localStorage for persistence
    getThumbnailFromCache(cameraName) {
        // First check memory cache
        if (this.thumbnailCache.has(cameraName)) {
            return this.thumbnailCache.get(cameraName);
        }
        
        // Then check localStorage
        try {
            const cached = localStorage.getItem(`myblink_thumb_${cameraName}`);
            if (cached) {
                this.thumbnailCache.set(cameraName, cached);
                return cached;
            }
        } catch (error) {
            console.warn('Failed to read thumbnail from cache:', error);
        }
        
        return null;
    }
    
    saveThumbnailToCache(cameraName, dataUrl) {
        // Save to memory cache
        this.thumbnailCache.set(cameraName, dataUrl);
        
        // Save to localStorage
        try {
            localStorage.setItem(`myblink_thumb_${cameraName}`, dataUrl);
        } catch (error) {
            console.warn('Failed to save thumbnail to cache:', error);
            // If localStorage is full, try to clear old thumbnails
            this.cleanupThumbnailCache();
            try {
                localStorage.setItem(`myblink_thumb_${cameraName}`, dataUrl);
            } catch (e) {
                console.error('Failed to save thumbnail even after cleanup:', e);
            }
        }
    }
    
    cleanupThumbnailCache() {
        // Remove thumbnails for cameras that no longer exist
        const currentCameras = new Set();
        for (const sync of this.state.syncs) {
            for (const camera of sync.cameras) {
                currentCameras.add(camera.name);
            }
        }
        
        // Clear localStorage entries for non-existent cameras
        try {
            const keys = Object.keys(localStorage);
            for (const key of keys) {
                if (key.startsWith('myblink_thumb_')) {
                    const cameraName = key.substring('myblink_thumb_'.length);
                    if (!currentCameras.has(cameraName)) {
                        localStorage.removeItem(key);
                        this.thumbnailCache.delete(cameraName);
                    }
                }
            }
        } catch (error) {
            console.warn('Failed to cleanup thumbnail cache:', error);
        }
    }
    
    async fetchAllThumbnails() {
        // Fetch thumbnails for all cameras in parallel
        const promises = [];
        
        for (const sync of this.state.syncs) {
            for (const camera of sync.cameras) {
                promises.push(this.fetchThumbnail(camera.name));
            }
        }
        
        // Wait for all thumbnails (but don't block on errors)
        await Promise.allSettled(promises);
    }
    
    async fetchThumbnail(cameraName) {
        try {
            // Check if we already have it cached
            if (this.getThumbnailFromCache(cameraName)) {
                return;
            }
            
            const response = await fetch(`/api/camera/${encodeURIComponent(cameraName)}/media/thumbnail`);
            
            if (response.ok) {
                const blob = await response.blob();
                
                // Convert blob to data URL for storage
                const reader = new FileReader();
                reader.onloadend = () => {
                    const dataUrl = reader.result;
                    this.saveThumbnailToCache(cameraName, dataUrl);
                    this.updateThumbnailDisplay(cameraName, dataUrl);
                };
                reader.readAsDataURL(blob);
            }
        } catch (error) {
            console.warn(`Failed to fetch thumbnail for ${cameraName}:`, error);
        }
    }
    
    updateThumbnailDisplay(cameraName, dataUrl) {
        const thumbnailEl = document.querySelector(`.camera-thumbnail[data-camera="${this.escapeHtml(cameraName)}"]`);
        if (thumbnailEl) {
            thumbnailEl.innerHTML = `<img src="${dataUrl}" alt="${this.escapeHtml(cameraName)}">`;
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize app
const app = new MyBlinkApp();
