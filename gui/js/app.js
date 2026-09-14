/**
 * Scanned Documents Renamer - Modern Desktop Web Interface
 * Communicates with Python backend via pywebview.api
 */

(function () {
  'use strict';

  // State
  let state = {
    isRunning: false,
    queuedCount: 0,
    processedCount: 0,
    activeClient: null,
    recentRecords: []
  };

  // Provider presets mapping
  const PROVIDER_PRESETS = {
    openrouter: {
      model: 'google/gemini-2.5-flash:free'
    },
    deepseek: {
      model: 'deepseek-chat'
    },
    openai: {
      model: 'gpt-4o-mini'
    },
    groq: {
      model: 'llama-3.1-8b-instant'
    },
    mock: {
      model: 'mock-offline-model'
    }
  };

  // DOM Elements
  const els = {
    statusPill: document.getElementById('status-pill'),
    statusText: document.getElementById('status-text'),
    btnToggleDaemon: document.getElementById('btn-toggle-daemon'),
    btnToggleText: document.getElementById('btn-toggle-text'),
    iconPlay: document.getElementById('icon-play'),
    btnWrapup: document.getElementById('btn-wrapup'),

    metricDaemonState: document.getElementById('metric-daemon-state'),
    metricQueueCount: document.getElementById('metric-queue-count'),
    metricProcessedCount: document.getElementById('metric-processed-count'),
    metricActiveClient: document.getElementById('metric-active-client'),
    btnClearClient: document.getElementById('btn-clear-client'),

    feedList: document.getElementById('activity-feed-list'),
    feedEmptyState: document.getElementById('feed-empty-state'),
    btnClearFeed: document.getElementById('btn-clear-feed'),

    settingWatchDir: document.getElementById('setting-watch-dir'),
    btnBrowseFolder: document.getElementById('btn-browse-folder'),
    settingProvider: document.getElementById('setting-provider'),
    settingModel: document.getElementById('setting-model'),
    settingApiKey: document.getElementById('setting-api-key'),
    btnToggleKeyVisibility: document.getElementById('btn-toggle-key-visibility'),
    settingWorkers: document.getElementById('setting-workers'),
    settingStability: document.getElementById('setting-stability'),
    settingWrapup: document.getElementById('setting-wrapup'),
    settingDocx: document.getElementById('setting-docx'),
    btnSaveSettings: document.getElementById('btn-save-settings'),

    terminalOutput: document.getElementById('terminal-output'),
    chkAutoscroll: document.getElementById('chk-autoscroll'),
    btnClearLogs: document.getElementById('btn-clear-logs'),

    toastContainer: document.getElementById('toast-container')
  };

  // Toast helper
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    els.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // Escape HTML helper
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Update UI Status Elements
  function updateUIState(status) {
    if (!status) return;

    state.isRunning = Boolean(status.is_running);
    state.queuedCount = status.queued_count || 0;
    state.processedCount = status.processed_count || 0;
    state.activeClient = status.active_client || null;

    // Status Pill
    if (state.isRunning) {
      els.statusPill.classList.add('running');
      els.statusText.textContent = 'Active & Watching';
      els.btnToggleDaemon.classList.add('danger-stop');
      els.btnToggleText.textContent = 'Stop Ingestion';
      els.metricDaemonState.textContent = 'Monitoring';
      els.metricDaemonState.style.color = 'var(--accent-emerald)';
    } else {
      els.statusPill.classList.remove('running');
      els.statusText.textContent = 'Stopped';
      els.btnToggleDaemon.classList.remove('danger-stop');
      els.btnToggleText.textContent = 'Start Ingestion';
      els.metricDaemonState.textContent = 'Standby';
      els.metricDaemonState.style.color = 'var(--text-primary)';
    }

    // Metric Cards
    els.metricQueueCount.textContent = state.queuedCount;
    els.metricProcessedCount.textContent = state.processedCount;

    if (state.activeClient) {
      els.metricActiveClient.textContent = state.activeClient;
      els.metricActiveClient.style.color = 'var(--accent-emerald)';
      els.btnClearClient.style.display = 'inline-flex';
    } else {
      els.metricActiveClient.textContent = 'None (Auto-detect)';
      els.metricActiveClient.style.color = 'var(--text-muted)';
      els.btnClearClient.style.display = 'none';
    }
  }

  // Append Document to Activity Feed
  function addDocumentToFeed(record) {
    if (els.feedEmptyState) {
      els.feedEmptyState.style.display = 'none';
    }

    const item = document.createElement('div');
    item.className = 'doc-item';
    item.innerHTML = `
      <div class="doc-main-info">
        <div class="doc-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
        </div>
        <div class="doc-details">
          <div class="doc-title-row">
            <span class="doc-target-name" title="${escapeHtml(record.dest_filename || record.filename)}">${escapeHtml(record.dest_filename || record.filename)}</span>
            <span class="doc-src-name">${escapeHtml(record.src_filename || record.filename)}</span>
          </div>
          <div class="doc-meta-row">
            <span class="doc-client-pill">${escapeHtml(record.client_name || 'General Clients')}</span>
            ${record.doc_date ? `<span>Date: ${escapeHtml(record.doc_date)}</span>` : ''}
            <span>${escapeHtml(record.timestamp || new Date().toLocaleTimeString())}</span>
          </div>
        </div>
      </div>
      <div class="doc-actions">
        ${record.dest_path ? `
          <button class="btn btn-secondary btn-sm btn-open-file" data-path="${escapeHtml(record.dest_path)}" title="Open containing client folder in Windows Explorer">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
            <span>Show in Folder</span>
          </button>
        ` : ''}
      </div>
    `;

    // Prepend item to top of list
    els.feedList.insertBefore(item, els.feedList.firstChild);

    // Bind reveal button
    const openBtn = item.querySelector('.btn-open-file');
    if (openBtn) {
      openBtn.addEventListener('click', () => {
        const path = openBtn.getAttribute('data-path');
        if (window.pywebview && window.pywebview.api) {
          window.pywebview.api.reveal_in_explorer(path);
        }
      });
    }
  }

  // Append Log Entry
  function appendLog(log) {
    if (!els.terminalOutput) return;

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const lvl = log.level || 'INFO';

    entry.innerHTML = `
      <span class="log-time">[${escapeHtml(log.timestamp || new Date().toLocaleTimeString())}]</span>
      <span class="log-badge ${lvl}">[${lvl}]</span>
      <span class="log-msg">${escapeHtml(log.message || '')}</span>
    `;

    els.terminalOutput.appendChild(entry);

    if (els.chkAutoscroll && els.chkAutoscroll.checked) {
      els.terminalOutput.scrollTop = els.terminalOutput.scrollHeight;
    }
  }

  // Global event receiver called by Python backend: window.onPipelineEvent(data)
  window.onPipelineEvent = function (event) {
    if (!event) return;

    if (event.category === 'status') {
      updateUIState(event);
    } else if (event.category === 'file') {
      if (event.type === 'completed') {
        addDocumentToFeed(event);
        showToast(`Filed: ${event.dest_filename} into ${event.client_name}`, 'success');
      } else if (event.type === 'error') {
        showToast(`Error processing ${event.filename}: ${event.error}`, 'error');
      }
    } else if (event.category === 'log') {
      appendLog(event);
    } else if (event.category === 'wrapup') {
      showToast(`Batch Wrap-Up Complete! Filed ${event.count || 0} client sets.`, 'success');
    }
  };

  // Tab Navigation Handling
  document.querySelectorAll('.tab-button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content-panel').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetId = `panel-${btn.getAttribute('data-tab')}`;
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.classList.add('active');
      }
    });
  });

  // Action: Toggle Daemon Start / Stop
  els.btnToggleDaemon.addEventListener('click', async () => {
    if (!window.pywebview || !window.pywebview.api) {
      showToast('Connecting to desktop backend...', 'info');
      return;
    }

    try {
      if (state.isRunning) {
        const res = await window.pywebview.api.stop_pipeline();
        showToast('Daemon stopped.', 'info');
      } else {
        const res = await window.pywebview.api.start_pipeline();
        showToast('Daemon started! Monitoring output folder.', 'success');
      }
    } catch (err) {
      showToast(`Action failed: ${err}`, 'error');
    }
  });

  // Action: Trigger Batch Wrap-Up
  els.btnWrapup.addEventListener('click', async () => {
    if (!window.pywebview || !window.pywebview.api) return;
    try {
      showToast('Executing Batch Wrap-Up...', 'info');
      const results = await window.pywebview.api.trigger_wrapup();
      showToast(`Wrap-Up completed! ${results ? results.length : 0} client folders processed.`, 'success');
    } catch (err) {
      showToast(`Wrap-Up error: ${err}`, 'error');
    }
  });

  // Action: Clear Active Client
  els.btnClearClient.addEventListener('click', async () => {
    if (!window.pywebview || !window.pywebview.api) return;
    await window.pywebview.api.reset_active_client();
    showToast('Active client context cleared.', 'info');
  });

  // Action: Clear Feed View
  els.btnClearFeed.addEventListener('click', () => {
    els.feedList.innerHTML = '';
    if (els.feedEmptyState) {
      els.feedList.appendChild(els.feedEmptyState);
      els.feedEmptyState.style.display = 'flex';
    }
  });

  // Action: Clear Logs
  els.btnClearLogs.addEventListener('click', () => {
    els.terminalOutput.innerHTML = '';
  });

  // Action: Toggle API Key Visibility
  els.btnToggleKeyVisibility.addEventListener('click', () => {
    if (els.settingApiKey.type === 'password') {
      els.settingApiKey.type = 'text';
      els.btnToggleKeyVisibility.textContent = 'Hide';
    } else {
      els.settingApiKey.type = 'password';
      els.btnToggleKeyVisibility.textContent = 'Show';
    }
  });

  // Action: Provider change handler
  els.settingProvider.addEventListener('change', () => {
    const selected = els.settingProvider.value;
    if (PROVIDER_PRESETS[selected]) {
      els.settingModel.value = PROVIDER_PRESETS[selected].model;
    }
  });

  // Action: Browse Watched Directory (Native Windows Folder Picker)
  els.btnBrowseFolder.addEventListener('click', async () => {
    if (!window.pywebview || !window.pywebview.api) return;
    try {
      const selectedPath = await window.pywebview.api.browse_folder();
      if (selectedPath) {
        els.settingWatchDir.value = selectedPath;
        showToast(`Selected: ${selectedPath}`, 'info');
      }
    } catch (err) {
      showToast(`Folder selection error: ${err}`, 'error');
    }
  });

  // Action: Save Settings
  els.btnSaveSettings.addEventListener('click', async () => {
    if (!window.pywebview || !window.pywebview.api) return;

    const watchDir = els.settingWatchDir.value.trim();
    if (!watchDir) {
      showToast('Please specify a scanner output folder.', 'error');
      return;
    }

    const payload = {
      watch_directories: [watchDir],
      provider: els.settingProvider.value,
      model_name: els.settingModel.value.trim(),
      api_key: els.settingApiKey.value.trim(),
      num_workers: parseInt(els.settingWorkers.value, 10) || 2,
      stability_timeout: parseInt(els.settingStability.value, 10) || 30,
      enable_wrapup: els.settingWrapup.checked,
      update_clients_docx: els.settingDocx.checked
    };

    try {
      const res = await window.pywebview.api.save_settings(payload);
      if (res && res.success) {
        showToast('Settings saved successfully!', 'success');
      } else {
        showToast('Settings saved.', 'info');
      }
    } catch (err) {
      showToast(`Error saving settings: ${err}`, 'error');
    }
  });

  // Load Initial Settings & Data from Backend
  async function loadInitialData() {
    if (!window.pywebview || !window.pywebview.api) return;

    try {
      const data = await window.pywebview.api.get_initial_data();
      if (data) {
        if (data.status) {
          updateUIState(data.status);
        }

        if (data.settings) {
          const s = data.settings;
          els.settingWatchDir.value = (s.watch_directories && s.watch_directories[0]) || '';
          els.settingProvider.value = s.provider || 'openrouter';
          els.settingModel.value = s.model_name || 'google/gemini-2.5-flash:free';
          els.settingApiKey.value = s.api_key || '';
          els.settingWorkers.value = s.num_workers || 2;
          els.settingStability.value = s.stability_timeout || 30;
          els.settingWrapup.checked = Boolean(s.enable_wrapup);
          els.settingDocx.checked = Boolean(s.update_clients_docx);
        }

        if (data.recent_records && Array.isArray(data.recent_records)) {
          data.recent_records.forEach(rec => addDocumentToFeed(rec));
        }
      }
    } catch (err) {
      console.error('Error loading initial data:', err);
    }
  }

  // Wait for pywebview bridge initialization
  window.addEventListener('pywebviewready', () => {
    appendLog({
      timestamp: new Date().toLocaleTimeString(),
      level: 'INFO',
      message: 'PyWebView bridge connected. Initializing workspace...'
    });
    loadInitialData();
  });

  // Fallback check if pywebviewready already fired
  setTimeout(() => {
    if (window.pywebview && window.pywebview.api) {
      loadInitialData();
    }
  }, 500);

})();
