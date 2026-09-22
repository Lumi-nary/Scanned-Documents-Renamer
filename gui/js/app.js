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
    isClientLocked: false,
    activeClientEnabled: true,
    clientList: [],
    recentRecords: [],
    isDirtySettings: false,
    originalSettings: null,
    instructions: {
      global_instructions: {
        system_role: '',
        client_rules: '',
        formatting_rules: ''
      },
      file_types: []
    },
    promptPreview: '',
    instructionsFilter: 'all',
    instructionsSearch: '',
    isDirtyInstructions: false
  };

  // Provider presets mapping
  const PROVIDER_PRESETS = {
    native: {
      model: 'Built-in Rules + Local PP-OCR',
      type: 'native',
      title: '100% Offline & Zero Setup (Accuracy May Vary)',
      desc: 'Runs completely offline on your PC using built-in deterministic rules and local PP-OCR. Zero API key needed. Note: Local OCR can be inaccurate on degraded scans or handwriting; an AI API is recommended for highest precision.',
      keyPlaceholder: 'Not required for Native mode',
      keyHint: 'Native processing runs 100% locally. No API key needed.'
    },
    ollama: {
      model: 'llama3.2',
      type: 'local',
      title: 'Local LLM (Ollama)',
      desc: 'Connects to your local Ollama server at http://localhost:11434/v1. Runs 1B–4B LLMs locally on your hardware. No cloud API key required.',
      keyPlaceholder: 'Optional for Ollama (default: ollama)',
      keyHint: 'Ollama runs locally on port 11434. Standard API key is optional.'
    },
    lmstudio: {
      model: 'local-model',
      type: 'local',
      title: 'Local LLM (LM Studio)',
      desc: 'Connects to your local LM Studio server at http://localhost:1234/v1. Runs local open-source models completely private on your PC.',
      keyPlaceholder: 'Optional for LM Studio',
      keyHint: 'LM Studio runs locally on port 1234.'
    },
    openrouter: {
      model: 'qwen/qwen3-vl-32b-instruct',
      type: 'cloud',
      title: 'OpenRouter (Recommended — 2026 Multimodal Vision & OCR)',
      desc: 'Connect to top multimodal models: Qwen 3 VL 32B (SOTA document OCR at $0.10/M tokens), DeepSeek Flash Vision, GPT Luna, GPT-5 Nano, or Gemini 3.x Flash.',
      keyPlaceholder: 'sk-or-v1-... (Paste your OpenRouter API key)',
      keyHint: 'Get your key at <a href="https://openrouter.ai/keys" target="_blank" style="color: var(--accent-indigo); text-decoration: underline;">openrouter.ai/keys</a>. Stored safely in local settings.json.'
    },
    openai: {
      model: 'gpt-4o-mini',
      type: 'cloud',
      title: 'OpenAI Direct (Cloud API)',
      desc: 'Dispatches document text directly to OpenAI official endpoints (GPT-4o, GPT-4o-mini).',
      keyPlaceholder: 'sk-proj-... (Paste your OpenAI key)',
      keyHint: 'Requires standard paid OpenAI platform account.'
    },
    deepseek: {
      model: 'deepseek-chat',
      type: 'cloud',
      title: 'DeepSeek Direct (Cloud API)',
      desc: 'Ultra cost-effective DeepSeek-V3 direct API endpoint for rapid intelligent document classification.',
      keyPlaceholder: 'sk-... (Paste your DeepSeek key)',
      keyHint: 'Obtain from platform.deepseek.com.'
    },
    groq: {
      model: 'llama-3.1-8b-instant',
      type: 'cloud',
      title: 'Groq Cloud (Ultra-Fast LPU)',
      desc: 'Sub-second inference using Groq specialized LPUs.',
      keyPlaceholder: 'gsk_... (Paste your Groq key)',
      keyHint: 'Obtain from console.groq.com.'
    },
    custom: {
      model: 'default',
      type: 'cloud',
      title: 'Custom OpenAI-Compatible Endpoint',
      desc: 'Connect to any standard OpenAI-compatible API endpoint.',
      keyPlaceholder: 'Enter API key if required',
      keyHint: 'Stored safely in local settings.json.'
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

    cardActiveClient: document.getElementById('card-active-client'),
    iconClientWrapper: document.getElementById('icon-client-wrapper'),
    clientLockBadge: document.getElementById('client-lock-badge'),
    btnSelectClient: document.getElementById('btn-select-client'),
    activeClientDropdown: document.getElementById('active-client-dropdown'),
    activeClientSearch: document.getElementById('active-client-search'),
    chkLockClient: document.getElementById('chk-lock-client'),
    activeClientList: document.getElementById('active-client-list'),
    actionHeaderNewClient: document.getElementById('action-header-new-client'),
    actionHeaderClearClient: document.getElementById('action-header-clear-client'),
    actionHeaderDisableClient: document.getElementById('action-header-disable-client'),
    btnToggleLockClient: document.getElementById('btn-toggle-lock-client'),
    iconLockState: document.getElementById('icon-lock-state'),
    btnCardScanFolders: document.getElementById('btn-card-scan-folders'),
    btnDropdownRescanFolders: document.getElementById('btn-dropdown-rescan-folders'),
    btnDropdownBrowseFolder: document.getElementById('btn-dropdown-browse-folder'),

    settingClientLockBadge: document.getElementById('setting-client-lock-badge'),
    settingActiveClientInput: document.getElementById('setting-active-client-input'),
    settingEnableActiveClient: document.getElementById('setting-enable-active-client'),
    btnSettingsBrowseClient: document.getElementById('btn-settings-browse-client'),
    btnSettingsToggleLock: document.getElementById('btn-settings-toggle-lock'),
    labelSettingsLock: document.getElementById('label-settings-lock'),
    btnSettingsClearClient: document.getElementById('btn-settings-clear-client'),

    feedList: document.getElementById('activity-feed-list'),
    feedEmptyState: document.getElementById('feed-empty-state'),
    btnClearFeed: document.getElementById('btn-clear-feed'),

    settingWatchDir: document.getElementById('setting-watch-dir'),
    btnBrowseFolder: document.getElementById('btn-browse-folder'),
    settingClientsDir: document.getElementById('setting-clients-dir'),
    btnBrowseClientsFolder: document.getElementById('btn-browse-clients-folder'),
    settingProvider: document.getElementById('setting-provider'),
    settingModel: document.getElementById('setting-model'),
    hintModel: document.getElementById('hint-model'),
    modelQuickPresets: document.getElementById('model-quick-presets'),
    chipsOpenrouter: document.getElementById('chips-openrouter'),
    chipsOllama: document.getElementById('chips-ollama'),
    providerBadgeCard: document.getElementById('provider-badge-card'),
    providerBadgeTitle: document.getElementById('provider-badge-title'),
    providerBadgeDesc: document.getElementById('provider-badge-desc'),
    nativeCautionBanner: document.getElementById('native-caution-banner'),
    btnSwitchToAi: document.getElementById('btn-switch-to-ai'),
    settingApiKey: document.getElementById('setting-api-key'),
    hintApiKey: document.getElementById('hint-api-key'),
    btnToggleKeyVisibility: document.getElementById('btn-toggle-key-visibility'),
    settingWorkers: document.getElementById('setting-workers'),
    settingStability: document.getElementById('setting-stability'),
    settingWrapup: document.getElementById('setting-wrapup'),
    settingDocx: document.getElementById('setting-docx'),
    btnSaveSettings: document.getElementById('btn-save-settings'),
    settingsForm: document.getElementById('settings-form'),
    floatingSettingsSave: document.getElementById('floating-settings-save'),
    btnFloatingSaveSettings: document.getElementById('btn-floating-save-settings'),
    btnFloatingDiscardSettings: document.getElementById('btn-floating-discard-settings'),

    terminalOutput: document.getElementById('terminal-output'),
    chkAutoscroll: document.getElementById('chk-autoscroll'),
    btnClearLogs: document.getElementById('btn-clear-logs'),

    toastContainer: document.getElementById('toast-container'),

    // Instructions Tab Elements
    badgeTotalRules: document.getElementById('badge-total-rules'),
    btnAddFileType: document.getElementById('btn-add-file-type'),
    btnPreviewPrompt: document.getElementById('btn-preview-prompt'),
    btnResetInstructions: document.getElementById('btn-reset-instructions'),
    btnSaveInstructions: document.getElementById('btn-save-instructions'),
    txtSaveInstructions: document.getElementById('txt-save-instructions'),
    instructionsSearch: document.getElementById('instructions-search'),
    instructionsCardsList: document.getElementById('instructions-cards-list'),
    instructionsEmptyState: document.getElementById('instructions-empty-state'),
    btnToggleGlobalRules: document.getElementById('btn-toggle-global-rules'),
    globalInstructionsBody: document.getElementById('global-instructions-body'),
    iconChevronGlobal: document.getElementById('icon-chevron-global'),
    txtSystemRole: document.getElementById('txt-system-role'),
    txtClientRules: document.getElementById('txt-client-rules'),
    txtFormattingRules: document.getElementById('txt-formatting-rules'),

    // Modal Edit Instruction
    modalEditInstruction: document.getElementById('modal-edit-instruction'),
    modalRuleTitle: document.getElementById('modal-rule-title'),
    modalRuleSubtitle: document.getElementById('modal-rule-subtitle'),
    btnCloseRuleModal: document.getElementById('btn-close-rule-modal'),
    btnCancelRuleModal: document.getElementById('btn-cancel-rule-modal'),
    btnSaveRuleModal: document.getElementById('btn-save-rule-modal'),
    editRuleId: document.getElementById('edit-rule-id'),
    editRuleName: document.getElementById('edit-rule-name'),
    editRulePriority: document.getElementById('edit-rule-priority'),
    editRuleKeywords: document.getElementById('edit-rule-keywords'),
    editRuleFormat: document.getElementById('edit-rule-format'),
    editRuleInstructions: document.getElementById('edit-rule-instructions'),
    editRuleEnabled: document.getElementById('edit-rule-enabled'),

    // Modal Prompt Preview
    modalPromptPreview: document.getElementById('modal-prompt-preview'),
    btnClosePromptModal: document.getElementById('btn-close-prompt-modal'),
    btnDismissPromptModal: document.getElementById('btn-dismiss-prompt-modal'),
    btnCopyPrompt: document.getElementById('btn-copy-prompt'),
    txtCopyPrompt: document.getElementById('txt-copy-prompt'),
    promptPreviewText: document.getElementById('prompt-preview-text')
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
    state.isClientLocked = Boolean(status.is_client_locked);
    if (status.active_client_enabled !== undefined) {
      state.activeClientEnabled = Boolean(status.active_client_enabled);
    } else if (status.enable_active_client !== undefined) {
      state.activeClientEnabled = Boolean(status.enable_active_client);
    }

    if (els.settingEnableActiveClient) {
      els.settingEnableActiveClient.checked = state.activeClientEnabled;
    }

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

    // Active Client Label & Lock State UI Sync
    if (!state.activeClientEnabled) {
      els.metricActiveClient.textContent = 'Disabled (Temporary)';
      els.metricActiveClient.style.color = 'var(--text-muted)';
      if (els.btnClearClient) els.btnClearClient.style.display = 'none';
      if (els.cardActiveClient) els.cardActiveClient.classList.remove('locked-state');
      if (els.clientLockBadge) {
        els.clientLockBadge.className = 'client-lock-pill disabled';
        els.clientLockBadge.textContent = 'Disabled';
        els.clientLockBadge.title = 'Active Client Context is disabled. Unassigned scans will default to Temporary.';
      }
      if (els.btnToggleLockClient) {
        els.btnToggleLockClient.classList.remove('locked');
        els.btnToggleLockClient.title = 'Active Client Context is disabled. Click to re-enable or choose client.';
      }
      if (els.settingClientLockBadge) {
        els.settingClientLockBadge.className = 'client-lock-pill disabled';
        els.settingClientLockBadge.textContent = 'Disabled';
      }
      if (els.labelSettingsLock) els.labelSettingsLock.textContent = '🔒 Lock';
    } else if (state.activeClient) {
      els.metricActiveClient.textContent = state.activeClient;
      els.metricActiveClient.style.color = state.isClientLocked ? '#fbbf24' : 'var(--accent-emerald)';
      if (els.btnClearClient) els.btnClearClient.style.display = 'inline-flex';
    } else {
      els.metricActiveClient.textContent = 'None (Auto-detect)';
      els.metricActiveClient.style.color = 'var(--text-muted)';
      if (els.btnClearClient) els.btnClearClient.style.display = 'none';
    }

    if (state.activeClientEnabled) {
      if (state.isClientLocked) {
        if (els.cardActiveClient) els.cardActiveClient.classList.add('locked-state');
        if (els.clientLockBadge) {
          els.clientLockBadge.className = 'client-lock-pill locked';
          els.clientLockBadge.textContent = '🔒 Locked';
          els.clientLockBadge.title = `Locked to: ${state.activeClient || 'None'}. All incoming scans will be routed here.`;
        }
        if (els.btnToggleLockClient) {
          els.btnToggleLockClient.classList.add('locked');
          els.btnToggleLockClient.title = 'Click to unlock client context (Resume auto-detect)';
          els.btnToggleLockClient.innerHTML = `
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
            </svg>
          `;
        }
        if (els.chkLockClient) els.chkLockClient.checked = true;
        if (els.settingClientLockBadge) {
          els.settingClientLockBadge.className = 'client-lock-pill locked';
          els.settingClientLockBadge.textContent = '🔒 Locked';
        }
        if (els.labelSettingsLock) els.labelSettingsLock.textContent = '🔓 Unlock';
      } else {
        if (els.cardActiveClient) els.cardActiveClient.classList.remove('locked-state');
        if (els.clientLockBadge) {
          els.clientLockBadge.className = 'client-lock-pill unlocked';
          els.clientLockBadge.textContent = 'Auto';
          els.clientLockBadge.title = 'Unlocked: Automatically detected from documents. Click lock button to lock.';
        }
        if (els.btnToggleLockClient) {
          els.btnToggleLockClient.classList.remove('locked');
          els.btnToggleLockClient.title = 'Click to lock active client (Force all scans to this client)';
          els.btnToggleLockClient.innerHTML = `
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
              <path d="M7 11V7a5 5 0 0 1 9.9-1"></path>
            </svg>
          `;
        }
        if (els.chkLockClient) els.chkLockClient.checked = false;
        if (els.settingClientLockBadge) {
          els.settingClientLockBadge.className = 'client-lock-pill unlocked';
          els.settingClientLockBadge.textContent = 'Auto';
        }
        if (els.labelSettingsLock) els.labelSettingsLock.textContent = '🔒 Lock';
      }
    }

    if (els.settingActiveClientInput) {
      els.settingActiveClientInput.value = state.activeClient || '';
    }
  }

  // Append Document to Activity Feed
  function addDocumentToFeed(record) {
    if (els.feedEmptyState) {
      els.feedEmptyState.style.display = 'none';
    }

    const targetPath = record.dest_path || record.file_path || '';
    const initialTitle = record.dest_filename || record.filename || '';
    const initialClient = record.client_name || 'General Clients';

    const item = document.createElement('div');
    item.className = 'doc-item';
    item.setAttribute('data-current-path', targetPath);

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
            <div class="doc-title-edit-wrap">
              <input type="text" class="doc-title-input" value="${escapeHtml(initialTitle)}" data-original="${escapeHtml(initialTitle)}" title="Click to rename document (Enter to save, Esc to cancel)" />
              <div class="doc-title-actions" style="display: none;">
                <button class="btn-inline-action btn-save-name" title="Save new name">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </button>
                <button class="btn-inline-action btn-cancel-name" title="Cancel">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              </div>
            </div>
          </div>
          <div class="doc-meta-row">
            <div class="doc-client-dropdown-wrap">
              <button class="doc-client-pill-btn" title="Click to move to another client folder">
                <span class="client-pill-label">${escapeHtml(initialClient)}</span>
                <svg class="chevron-down" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </button>
              <div class="client-dropdown-menu">
                <div class="client-dropdown-search-wrap">
                  <input type="text" class="client-dropdown-search" placeholder="Filter client folders..." />
                </div>
                <div class="client-dropdown-list">
                  <!-- Dynamic items -->
                </div>
                <div class="client-dropdown-footer">
                  <div class="client-dropdown-item new-client-action">
                    <span>➕ New Client Folder...</span>
                  </div>
                </div>
              </div>
            </div>
            ${record.doc_date ? `<span>Date: ${escapeHtml(record.doc_date)}</span>` : ''}
            <span>${escapeHtml(record.timestamp || new Date().toLocaleTimeString())}</span>
          </div>
        </div>
      </div>
      <div class="doc-actions">
        ${targetPath ? `
          <button class="btn btn-secondary btn-sm btn-open-file" data-path="${escapeHtml(targetPath)}" title="Open containing client folder in Windows Explorer">
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

    // --- Feature 1: Inline Title Rename ---
    const titleInput = item.querySelector('.doc-title-input');
    const titleActions = item.querySelector('.doc-title-actions');
    const btnSave = item.querySelector('.btn-save-name');
    const btnCancel = item.querySelector('.btn-cancel-name');

    function checkDirty() {
      const orig = titleInput.getAttribute('data-original') || '';
      const cur = titleInput.value.trim();
      if (cur !== orig && cur.length > 0) {
        titleActions.style.display = 'inline-flex';
      } else {
        titleActions.style.display = 'none';
      }
    }

    titleInput.addEventListener('input', checkDirty);

    async function doSave() {
      const orig = titleInput.getAttribute('data-original') || '';
      const cur = titleInput.value.trim();
      if (!cur || cur === orig) {
        titleInput.value = orig;
        titleActions.style.display = 'none';
        return;
      }

      const currentPath = item.getAttribute('data-current-path') || '';
      if (!currentPath || !window.pywebview || !window.pywebview.api) return;

      btnSave.disabled = true;
      btnCancel.disabled = true;

      try {
        const res = await window.pywebview.api.rename_document(currentPath, cur);
        if (res && res.success) {
          titleInput.value = res.new_filename;
          titleInput.setAttribute('data-original', res.new_filename);
          item.setAttribute('data-current-path', res.new_path);
          if (openBtn) {
            openBtn.setAttribute('data-path', res.new_path);
          }
          titleActions.style.display = 'none';
          showToast(`Renamed to: ${res.new_filename}`, 'success');
        } else {
          showToast(`Rename failed: ${res ? res.error : 'Unknown error'}`, 'error');
        }
      } catch (err) {
        showToast(`Rename error: ${err}`, 'error');
      } finally {
        btnSave.disabled = false;
        btnCancel.disabled = false;
      }
    }

    function doCancel() {
      const orig = titleInput.getAttribute('data-original') || '';
      titleInput.value = orig;
      titleActions.style.display = 'none';
    }

    btnSave.addEventListener('click', (e) => {
      e.stopPropagation();
      doSave();
    });

    btnCancel.addEventListener('click', (e) => {
      e.stopPropagation();
      doCancel();
    });

    titleInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        doSave();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        doCancel();
      }
    });

    // --- Feature 2: Client Dropdown Mover ---
    const clientWrap = item.querySelector('.doc-client-dropdown-wrap');
    const clientBtn = item.querySelector('.doc-client-pill-btn');
    const clientLabel = item.querySelector('.client-pill-label');
    const dropdownMenu = item.querySelector('.client-dropdown-menu');
    const searchInput = item.querySelector('.client-dropdown-search');
    const listContainer = item.querySelector('.client-dropdown-list');
    const newClientBtn = item.querySelector('.new-client-action');

    let availableClients = [];

    async function openDropdown() {
      document.querySelectorAll('.doc-client-dropdown-wrap.open').forEach(w => {
        if (w !== clientWrap) {
          w.classList.remove('open');
          const m = w.querySelector('.client-dropdown-menu');
          if (m) m.style.display = 'none';
        }
      });

      clientWrap.classList.add('open');
      dropdownMenu.style.display = 'flex';
      searchInput.value = '';
      setTimeout(() => searchInput.focus(), 50);

      try {
        if (window.pywebview && window.pywebview.api) {
          availableClients = await window.pywebview.api.get_client_list();
        }
      } catch (e) {
        console.error(e);
      }
      if (!availableClients || !availableClients.length) {
        availableClients = ['General Clients'];
      }
      renderClientList('');
    }

    function closeDropdown() {
      clientWrap.classList.remove('open');
      dropdownMenu.style.display = 'none';
    }

    function renderClientList(filterText) {
      listContainer.innerHTML = '';
      const currentClient = clientLabel.textContent.trim().toLowerCase();
      const query = filterText.trim().toLowerCase();

      const filtered = availableClients.filter(c => !query || c.toLowerCase().includes(query));

      if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'client-dropdown-item';
        empty.style.color = 'var(--text-muted)';
        empty.style.cursor = 'default';
        empty.textContent = 'No matching folders';
        listContainer.appendChild(empty);
        return;
      }

      filtered.forEach(cName => {
        const dItem = document.createElement('div');
        const isActive = cName.toLowerCase() === currentClient;
        dItem.className = 'client-dropdown-item' + (isActive ? ' active' : '');
        dItem.innerHTML = `
          <span>${escapeHtml(cName)}</span>
          ${isActive ? `
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          ` : ''}
        `;

        dItem.addEventListener('click', async (e) => {
          e.stopPropagation();
          closeDropdown();
          if (isActive) return;

          const currentPath = item.getAttribute('data-current-path') || '';
          if (!currentPath || !window.pywebview || !window.pywebview.api) return;

          showToast(`Moving to "${cName}"...`, 'info');
          try {
            const res = await window.pywebview.api.move_document_to_client(currentPath, cName);
            if (res && res.success) {
              clientLabel.textContent = res.client_name;
              item.setAttribute('data-current-path', res.new_path);
              if (openBtn) {
                openBtn.setAttribute('data-path', res.new_path);
              }
              showToast(`Moved to "${res.client_name}"`, 'success');
            } else {
              showToast(`Move failed: ${res ? res.error : 'Unknown error'}`, 'error');
            }
          } catch (err) {
            showToast(`Move error: ${err}`, 'error');
          }
        });

        listContainer.appendChild(dItem);
      });
    }

    searchInput.addEventListener('input', () => {
      renderClientList(searchInput.value);
    });

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeDropdown();
      }
    });

    clientBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (clientWrap.classList.contains('open')) {
        closeDropdown();
      } else {
        openDropdown();
      }
    });

    newClientBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      closeDropdown();
      const newName = prompt('Enter new Client Folder name:');
      if (!newName || !newName.trim()) return;

      const cleanNew = newName.trim();
      const currentPath = item.getAttribute('data-current-path') || '';
      if (!currentPath || !window.pywebview || !window.pywebview.api) return;

      showToast(`Creating "${cleanNew}" & moving file...`, 'info');
      try {
        const res = await window.pywebview.api.move_document_to_client(currentPath, cleanNew);
        if (res && res.success) {
          clientLabel.textContent = res.client_name;
          item.setAttribute('data-current-path', res.new_path);
          if (openBtn) {
            openBtn.setAttribute('data-path', res.new_path);
          }
          showToast(`Moved to "${res.client_name}"`, 'success');
        } else {
          showToast(`Move failed: ${res ? res.error : 'Unknown error'}`, 'error');
        }
      } catch (err) {
        showToast(`Move error: ${err}`, 'error');
      }
    });
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

  // ============================================================
  // Active Client Selector & Locking Handlers
  // ============================================================
  async function refreshClientDropdownList(filterText = '') {
    if (!els.activeClientList) return;
    try {
      if (window.pywebview && window.pywebview.api) {
        state.clientList = await window.pywebview.api.get_client_list();
      }
    } catch (e) {
      console.warn('Could not fetch client list:', e);
    }

    const list = state.clientList && state.clientList.length ? state.clientList : ['General Clients'];
    const query = filterText.toLowerCase().trim();
    const filtered = list.filter(c => !query || c.toLowerCase().includes(query));

    els.activeClientList.innerHTML = '';
    if (filtered.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'client-dropdown-empty';
      empty.style.padding = '8px 10px';
      empty.style.fontSize = '12px';
      empty.style.color = 'var(--text-muted)';
      empty.textContent = 'No matching clients found';
      els.activeClientList.appendChild(empty);
      return;
    }

    filtered.forEach(clientName => {
      const item = document.createElement('div');
      item.className = 'client-dropdown-item';
      const isCurrent = state.activeClient && state.activeClient.toLowerCase() === clientName.toLowerCase();
      if (isCurrent) {
        item.classList.add('selected');
        item.style.fontWeight = '700';
        item.style.color = state.isClientLocked ? '#fbbf24' : 'var(--accent-emerald)';
      }

      item.innerHTML = `
        <div style="display: flex; align-items: center; gap: 7px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0; opacity: 0.7;">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
          </svg>
          <span class="client-name-text">${escapeHtml(clientName)}</span>
        </div>
        ${isCurrent ? '<span style="margin-left: auto; font-size: 13px; font-weight: 700; color: #fbbf24;">🔒 ✓</span>' : ''}
      `;

      item.addEventListener('click', async (e) => {
        e.stopPropagation();
        closeActiveClientDropdown();
        // Clicking a client folder automatically sets and locks context to that client
        await selectActiveClient(clientName, true);
      });

      els.activeClientList.appendChild(item);
    });
  }

  async function selectActiveClient(clientName, lock = true) {
    if (!clientName || !clientName.trim()) return;
    const clean = clientName.trim();

    // 1. Instant optimistic UI update so the user is never stuck on 'None'
    state.activeClientEnabled = true;
    state.activeClient = clean;
    state.isClientLocked = Boolean(lock);
    updateUIState({ active_client_enabled: true, active_client: clean, is_client_locked: Boolean(lock), is_running: state.isRunning });
    if (els.chkLockClient) {
      els.chkLockClient.checked = Boolean(lock);
    }

    // 2. Communicate with backend
    if (window.pywebview && window.pywebview.api) {
      try {
        let res = null;
        if (lock && typeof window.pywebview.api.set_and_lock_client === 'function') {
          res = await window.pywebview.api.set_and_lock_client(clean, true);
        } else if (typeof window.pywebview.api.set_active_client === 'function') {
          res = await window.pywebview.api.set_active_client(clean);
          if (lock && typeof window.pywebview.api.set_client_locked === 'function') {
            await window.pywebview.api.set_client_locked(true);
          }
        }
        if (res && res.status) {
          updateUIState(res.status);
        }
        showToast(lock ? `Active client locked to: ${clean}` : `Active client set to: ${clean}`, 'success');
      } catch (err) {
        showToast(`Failed setting client: ${err}`, 'error');
      }
    }
  }

  function toggleActiveClientDropdown() {
    const wrap = document.querySelector('.client-selector-wrap');
    const card = document.getElementById('card-active-client');
    if (!wrap) return;
    const isOpen = wrap.classList.contains('open');
    if (isOpen) {
      closeActiveClientDropdown();
    } else {
      wrap.classList.add('open');
      if (card) card.classList.add('dropdown-open');
      if (els.activeClientSearch) {
        els.activeClientSearch.value = '';
        setTimeout(() => els.activeClientSearch.focus(), 50);
      }
      if (els.chkLockClient) {
        els.chkLockClient.checked = state.isClientLocked;
      }
      refreshClientDropdownList();
    }
  }

  function closeActiveClientDropdown() {
    const wrap = document.querySelector('.client-selector-wrap');
    const card = document.getElementById('card-active-client');
    if (wrap) wrap.classList.remove('open');
    if (card) card.classList.remove('dropdown-open');
  }

  // Bind dropdown trigger button
  if (els.btnSelectClient) {
    els.btnSelectClient.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleActiveClientDropdown();
    });
  }

  // Prevent click inside dropdown from closing it
  if (els.activeClientDropdown) {
    els.activeClientDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }

  // Search filter typing
  if (els.activeClientSearch) {
    els.activeClientSearch.addEventListener('input', () => {
      refreshClientDropdownList(els.activeClientSearch.value);
    });
  }

  // Lock checkbox inside dropdown
  if (els.chkLockClient) {
    els.chkLockClient.addEventListener('change', async () => {
      const willLock = els.chkLockClient.checked;
      if (state.activeClient && state.activeClient.toLowerCase() !== 'general clients') {
        state.isClientLocked = willLock;
        updateUIState({ active_client: state.activeClient, is_client_locked: willLock, is_running: state.isRunning });
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.set_client_locked(willLock);
        }
        showToast(willLock ? `Active client locked to: ${state.activeClient}` : 'Unlocked active client (Auto mode)', 'info');
      } else if (willLock) {
        showToast('Select a client folder from the list to lock context.', 'info');
      }
    });
  }

  // Browse & select specific client folder from disk
  async function browseAndSelectClientFolder() {
    if (!window.pywebview || !window.pywebview.api) {
      showToast('Backend bridge not ready.', 'info');
      return;
    }
    try {
      showToast('Opening folder browser...', 'info');
      let res = null;
      if (typeof window.pywebview.api.browse_and_select_client_folder === 'function') {
        res = await window.pywebview.api.browse_and_select_client_folder();
      } else if (typeof window.pywebview.api.browse_folder === 'function') {
        const folder = await window.pywebview.api.browse_folder('clients');
        if (folder) {
          const folderName = folder.split(/[\\/]/).pop();
          res = { success: true, client_name: folderName, selected_path: folder };
        }
      }
      if (res && res.success && res.client_name) {
        closeActiveClientDropdown();
        await selectActiveClient(res.client_name, true);
        if (res.client_list) {
          state.clientList = res.client_list;
        }
        await triggerScanClientFolders();
      }
    } catch (err) {
      showToast(`Folder selection error: ${err}`, 'error');
    }
  }

  // Card 4 quick scan folders button
  if (els.btnCardScanFolders) {
    els.btnCardScanFolders.addEventListener('click', async (e) => {
      e.stopPropagation();
      await triggerScanClientFolders();
    });
  }

  // Dropdown header quick scan folders button
  if (els.btnDropdownRescanFolders) {
    els.btnDropdownRescanFolders.addEventListener('click', async (e) => {
      e.stopPropagation();
      await triggerScanClientFolders();
    });
  }

  // Dropdown header browse folder button
  if (els.btnDropdownBrowseFolder) {
    els.btnDropdownBrowseFolder.addEventListener('click', async (e) => {
      e.stopPropagation();
      await browseAndSelectClientFolder();
    });
  }

  // Settings tab browse client button
  if (els.btnSettingsBrowseClient) {
    els.btnSettingsBrowseClient.addEventListener('click', async () => {
      await browseAndSelectClientFolder();
    });
  }

  // Custom client action in dropdown
  if (els.actionHeaderNewClient) {
    els.actionHeaderNewClient.addEventListener('click', async (e) => {
      e.stopPropagation();
      closeActiveClientDropdown();
      const customName = prompt('Enter client folder name:');
      if (customName && customName.trim()) {
        const shouldLock = els.chkLockClient ? els.chkLockClient.checked : true;
        await selectActiveClient(customName.trim(), shouldLock);
      }
    });
  }

  // Rescan client folders action in dropdown (legacy fallback)
  const actionHeaderScanClients = document.getElementById('action-header-scan-clients');
  if (actionHeaderScanClients) {
    actionHeaderScanClients.addEventListener('click', async (e) => {
      e.stopPropagation();
      await triggerScanClientFolders();
    });
  }

  // Reset / Clear in dropdown (Auto mode)
  if (els.actionHeaderClearClient) {
    els.actionHeaderClearClient.addEventListener('click', async (e) => {
      e.stopPropagation();
      closeActiveClientDropdown();
      state.activeClientEnabled = true;
      state.activeClient = null;
      state.isClientLocked = false;
      updateUIState({ active_client_enabled: true, active_client: null, is_client_locked: false, is_running: state.isRunning });
      if (window.pywebview && window.pywebview.api) {
        if (typeof window.pywebview.api.set_active_client_enabled === 'function') {
          await window.pywebview.api.set_active_client_enabled(true);
        }
        await window.pywebview.api.reset_active_client();
        showToast('Active client context reset to Auto (Auto-detect mode).', 'info');
      }
    });
  }

  // Disable Active Client Context in dropdown
  if (els.actionHeaderDisableClient) {
    els.actionHeaderDisableClient.addEventListener('click', async (e) => {
      e.stopPropagation();
      closeActiveClientDropdown();
      state.activeClientEnabled = false;
      state.activeClient = null;
      state.isClientLocked = false;
      updateUIState({ active_client_enabled: false, active_client: null, is_client_locked: false, is_running: state.isRunning });
      if (window.pywebview && window.pywebview.api) {
        if (typeof window.pywebview.api.set_active_client_enabled === 'function') {
          await window.pywebview.api.set_active_client_enabled(false);
        }
        showToast('Active client context disabled. Unassigned scans will default to Temporary.', 'info');
      }
    });
  }

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    const wrap = document.querySelector('.client-selector-wrap');
    if (wrap && wrap.classList.contains('open')) {
      if (!wrap.contains(e.target)) {
        closeActiveClientDropdown();
      }
    }
  });

  // Action: Toggle Client Lock Button on Card 4
  if (els.btnToggleLockClient) {
    els.btnToggleLockClient.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!window.pywebview || !window.pywebview.api) return;

      if (state.isClientLocked) {
        // Unlock
        await window.pywebview.api.set_client_locked(false);
        showToast('Active client unlocked (Auto-detect mode).', 'info');
      } else {
        // If client is not set, open dropdown to choose or prompt
        if (!state.activeClient || state.activeClient.toLowerCase() === 'general clients') {
          toggleActiveClientDropdown();
          showToast('Select or enter a client to lock context.', 'info');
        } else {
          await window.pywebview.api.set_client_locked(true);
          showToast(`Active client locked to: ${state.activeClient}`, 'success');
        }
      }
    });
  }

  // Action: Settings tab toggle lock
  if (els.btnSettingsToggleLock) {
    els.btnSettingsToggleLock.addEventListener('click', async () => {
      if (!window.pywebview || !window.pywebview.api) return;
      const inputVal = els.settingActiveClientInput ? els.settingActiveClientInput.value.trim() : '';

      if (state.isClientLocked) {
        await window.pywebview.api.set_client_locked(false);
        showToast('Active client unlocked.', 'info');
      } else {
        const clientToLock = inputVal || state.activeClient;
        if (!clientToLock) {
          showToast('Please type or select a client name first.', 'error');
          if (els.settingActiveClientInput) els.settingActiveClientInput.focus();
          return;
        }
        await window.pywebview.api.set_and_lock_client(clientToLock, true);
        showToast(`Active client locked to: ${clientToLock}`, 'success');
      }
    });
  }

  if (els.btnSettingsClearClient) {
    els.btnSettingsClearClient.addEventListener('click', async () => {
      if (!window.pywebview || !window.pywebview.api) return;
      await window.pywebview.api.reset_active_client();
      showToast('Active client context cleared.', 'info');
    });
  }

  // Action: Clear Active Client
  if (els.btnClearClient) {
    els.btnClearClient.addEventListener('click', async () => {
      if (!window.pywebview || !window.pywebview.api) return;
      await window.pywebview.api.reset_active_client();
      showToast('Active client context cleared.', 'info');
    });
  }

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

  // Helper: Synchronize active chip highlighting with current model input
  function syncActiveChip() {
    const currentModel = els.settingModel ? els.settingModel.value.trim() : '';
    document.querySelectorAll('.model-chip').forEach(chip => {
      const chipModel = chip.getAttribute('data-model');
      if (chipModel === currentModel) {
        chip.classList.add('active');
      } else {
        chip.classList.remove('active');
      }
    });
  }

  // Helper: Update provider badge & input hints
  function updateProviderUI(selected) {
    const preset = PROVIDER_PRESETS[selected] || PROVIDER_PRESETS.native;
    if (els.providerBadgeCard) {
      els.providerBadgeCard.className = `provider-badge-card ${preset.type}`;
      els.providerBadgeTitle.textContent = preset.title;
      els.providerBadgeDesc.textContent = preset.desc;
    }
    if (els.hintModel) {
      els.hintModel.textContent = preset.type === 'native'
        ? 'Standard built-in deterministic rules and local OCR.'
        : `Default model for ${preset.title}: ${preset.model}`;
    }
    if (els.settingApiKey) {
      els.settingApiKey.placeholder = preset.keyPlaceholder;
    }
    if (els.hintApiKey) {
      els.hintApiKey.innerHTML = preset.keyHint;
    }
    if (els.nativeCautionBanner) {
      els.nativeCautionBanner.style.display = (selected === 'native') ? 'flex' : 'none';
    }

    // Toggle model quick chips based on provider
    if (els.modelQuickPresets) {
      if (selected === 'openrouter') {
        els.modelQuickPresets.style.display = 'flex';
        if (els.chipsOpenrouter) els.chipsOpenrouter.style.display = 'flex';
        if (els.chipsOllama) els.chipsOllama.style.display = 'none';
      } else if (selected === 'ollama') {
        els.modelQuickPresets.style.display = 'flex';
        if (els.chipsOpenrouter) els.chipsOpenrouter.style.display = 'none';
        if (els.chipsOllama) els.chipsOllama.style.display = 'flex';
      } else {
        els.modelQuickPresets.style.display = 'none';
      }
      syncActiveChip();
    }
  }

  // Wire up quick model selection chips
  document.querySelectorAll('.model-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      e.preventDefault();
      const targetModel = chip.getAttribute('data-model');
      const hint = chip.getAttribute('data-hint');
      if (targetModel && els.settingModel) {
        els.settingModel.value = targetModel;
        syncActiveChip();
        if (els.hintModel && hint) {
          els.hintModel.textContent = hint;
        }
        showToast(`Model set: ${targetModel}`, 'info');
        checkSettingsDirty();
      }
    });
  });

  if (els.settingModel) {
    els.settingModel.addEventListener('input', () => {
      syncActiveChip();
      checkSettingsDirty();
    });
  }

  // Action: Switch to recommended AI from caution banner
  if (els.btnSwitchToAi) {
    els.btnSwitchToAi.addEventListener('click', () => {
      els.settingProvider.value = 'openrouter';
      const preset = PROVIDER_PRESETS.openrouter;
      if (preset) {
        els.settingModel.value = preset.model;
      }
      updateProviderUI('openrouter');
      showToast('Switched to OpenRouter AI (Qwen 3 VL) for ultra-fast document OCR.', 'info');
      if (els.settingApiKey) {
        els.settingApiKey.focus();
      }
      checkSettingsDirty();
    });
  }

  // Action: Provider change handler
  els.settingProvider.addEventListener('change', () => {
    const selected = els.settingProvider.value;
    const preset = PROVIDER_PRESETS[selected];
    if (preset) {
      els.settingModel.value = preset.model;
    }
    updateProviderUI(selected);
    checkSettingsDirty();
  });

  // Action: Browse Watched Directory (Native Windows Folder Picker)
  els.btnBrowseFolder.addEventListener('click', async () => {
    if (!window.pywebview || !window.pywebview.api) return;
    try {
      const selectedPath = await window.pywebview.api.browse_folder();
      if (selectedPath) {
        els.settingWatchDir.value = selectedPath;
        showToast(`Scanner Output: ${selectedPath}`, 'info');
        checkSettingsDirty();
      }
    } catch (err) {
      showToast(`Folder selection error: ${err}`, 'error');
    }
  });

  // Action: Browse Clients Root Directory (Destination)
  if (els.btnBrowseClientsFolder) {
    els.btnBrowseClientsFolder.addEventListener('click', async () => {
      if (!window.pywebview || !window.pywebview.api) return;
      try {
        let selectedPath = null;
        if (typeof window.pywebview.api.browse_clients_folder === 'function') {
          selectedPath = await window.pywebview.api.browse_clients_folder();
        } else if (typeof window.pywebview.api.browse_folder === 'function') {
          try {
            selectedPath = await window.pywebview.api.browse_folder('clients');
          } catch (e) {
            selectedPath = await window.pywebview.api.browse_folder();
          }
        }
        if (selectedPath) {
          if (els.settingClientsDir) {
            els.settingClientsDir.value = selectedPath;
          }
          showToast(`Clients Folder: ${selectedPath}`, 'info');
          checkSettingsDirty();
          // Auto-rescan client folders when a new clients root is selected
          await triggerScanClientFolders(selectedPath);
        }
      } catch (err) {
        showToast(`Folder selection error: ${err}`, 'error');
      }
    });
  }

  // Helper: Rescan Client Folders from disk
  async function triggerScanClientFolders(customDir = null) {
    if (!window.pywebview || !window.pywebview.api) return;
    try {
      showToast('Scanning client directories...', 'info');
      let targetDir = customDir;
      if (!targetDir && els.settingClientsDir) {
        targetDir = els.settingClientsDir.value.trim() || null;
      }

      let res = null;
      if (typeof window.pywebview.api.scan_client_directories === 'function') {
        res = await window.pywebview.api.scan_client_directories(targetDir);
      } else if (typeof window.pywebview.api.get_client_list === 'function') {
        const list = await window.pywebview.api.get_client_list();
        res = { success: true, count: list.length, clients: list };
      }
      if (res && res.clients) {
        state.clientList = res.clients;
        state.clientFolders = res.clients;
        refreshClientDropdownList(els.activeClientSearch ? els.activeClientSearch.value : '');
        showToast(`Discovered ${res.count || res.clients.length} client folders on disk.`, 'success');
      }
    } catch (err) {
      showToast(`Error scanning client folders: ${err}`, 'error');
    }
  }

  // Action: Scan Clients Folder (in Settings)
  const btnScanClientsFolder = document.getElementById('btn-scan-clients-folder');
  if (btnScanClientsFolder) {
    btnScanClientsFolder.addEventListener('click', async () => {
      const customDir = els.settingClientsDir ? els.settingClientsDir.value.trim() : null;
      await triggerScanClientFolders(customDir);
    });
  }

  // Action: Scan Watched Folder for Unprocessed Scans
  const handleScanWatchedFolder = async () => {
    if (!window.pywebview || !window.pywebview.api) return;
    try {
      showToast('Scanning scanner folder for documents...', 'info');
      let res = null;
      if (typeof window.pywebview.api.scan_watched_folder === 'function') {
        res = await window.pywebview.api.scan_watched_folder();
      }
      if (res && res.enqueued_count !== undefined) {
        showToast(`Scan complete: Enqueued ${res.enqueued_count} document(s).`, 'success');
        if (res.status) updateUIState(res.status);
      } else {
        showToast('Scanner folder scan completed.', 'success');
      }
    } catch (err) {
      showToast(`Scan folder error: ${err}`, 'error');
    }
  };

  const btnScanFeed = document.getElementById('btn-scan-feed');
  const btnScanWatchedFolder = document.getElementById('btn-scan-watched-folder');
  if (btnScanFeed) btnScanFeed.addEventListener('click', handleScanWatchedFolder);
  if (btnScanWatchedFolder) btnScanWatchedFolder.addEventListener('click', handleScanWatchedFolder);

  // ============================================================
  // Settings Dirty Tracking & Floating Save Action Bar
  // ============================================================

  function snapshotSettings() {
    state.originalSettings = getCurrentSettingsFormValues();
    setSettingsDirty(false);
  }

  function getCurrentSettingsFormValues() {
    return {
      watch_directories: [els.settingWatchDir ? els.settingWatchDir.value.trim() : ''],
      clients_directory: els.settingClientsDir ? els.settingClientsDir.value.trim() : '',
      provider: els.settingProvider ? els.settingProvider.value : 'native',
      model_name: els.settingModel ? els.settingModel.value.trim() : '',
      api_key: els.settingApiKey ? els.settingApiKey.value.trim() : '',
      num_workers: els.settingWorkers ? (parseInt(els.settingWorkers.value, 10) || 2) : 2,
      stability_timeout: els.settingStability ? (parseInt(els.settingStability.value, 10) || 30) : 30,
      enable_wrapup: Boolean(els.settingWrapup && els.settingWrapup.checked),
      update_clients_docx: Boolean(els.settingDocx && els.settingDocx.checked),
      enable_active_client: els.settingEnableActiveClient ? Boolean(els.settingEnableActiveClient.checked) : true
    };
  }

  function checkSettingsDirty() {
    if (!state.originalSettings) {
      snapshotSettings();
      return;
    }
    const cur = getCurrentSettingsFormValues();
    const orig = state.originalSettings;

    const isDirty = (
      cur.watch_directories[0] !== (orig.watch_directories[0] || '') ||
      cur.clients_directory !== (orig.clients_directory || '') ||
      cur.provider !== (orig.provider || '') ||
      cur.model_name !== (orig.model_name || '') ||
      cur.api_key !== (orig.api_key || '') ||
      cur.num_workers !== (orig.num_workers || 2) ||
      cur.stability_timeout !== (orig.stability_timeout || 30) ||
      cur.enable_wrapup !== Boolean(orig.enable_wrapup) ||
      cur.update_clients_docx !== Boolean(orig.update_clients_docx) ||
      cur.enable_active_client !== Boolean(orig.enable_active_client)
    );

    setSettingsDirty(isDirty);
  }

  function setSettingsDirty(isDirty) {
    state.isDirtySettings = Boolean(isDirty);
    if (els.floatingSettingsSave) {
      if (state.isDirtySettings) {
        els.floatingSettingsSave.classList.add('visible');
      } else {
        els.floatingSettingsSave.classList.remove('visible');
      }
    }
  }

  function discardSettingsChanges() {
    if (!state.originalSettings) return;
    const orig = state.originalSettings;
    if (els.settingWatchDir) els.settingWatchDir.value = (orig.watch_directories && orig.watch_directories[0]) || '';
    if (els.settingClientsDir) els.settingClientsDir.value = orig.clients_directory || '';
    if (els.settingProvider) els.settingProvider.value = orig.provider || 'native';
    if (els.settingModel) els.settingModel.value = orig.model_name || '';
    if (els.settingApiKey) els.settingApiKey.value = orig.api_key || '';
    if (els.settingWorkers) els.settingWorkers.value = orig.num_workers || 2;
    if (els.settingStability) els.settingStability.value = orig.stability_timeout || 30;
    if (els.settingWrapup) els.settingWrapup.checked = Boolean(orig.enable_wrapup);
    if (els.settingDocx) els.settingDocx.checked = Boolean(orig.update_clients_docx);
    if (els.settingEnableActiveClient) els.settingEnableActiveClient.checked = Boolean(orig.enable_active_client);

    updateProviderUI(orig.provider || 'native');
    setSettingsDirty(false);
    showToast('Unsaved settings discarded.', 'info');
  }

  // Common Save Settings Execution
  async function saveSettingsAction() {
    const watchDir = els.settingWatchDir ? els.settingWatchDir.value.trim() : '';
    if (!watchDir) {
      showToast('Please specify a scanner output folder.', 'error');
      return;
    }

    const payload = {
      watch_directories: [watchDir],
      clients_directory: els.settingClientsDir ? (els.settingClientsDir.value.trim() || null) : null,
      provider: els.settingProvider ? els.settingProvider.value : 'native',
      model_name: els.settingModel ? els.settingModel.value.trim() : '',
      api_key: els.settingApiKey ? els.settingApiKey.value.trim() : '',
      num_workers: parseInt(els.settingWorkers ? els.settingWorkers.value : 2, 10) || 2,
      stability_timeout: parseInt(els.settingStability ? els.settingStability.value : 30, 10) || 30,
      enable_wrapup: Boolean(els.settingWrapup && els.settingWrapup.checked),
      update_clients_docx: Boolean(els.settingDocx && els.settingDocx.checked),
      enable_active_client: els.settingEnableActiveClient ? Boolean(els.settingEnableActiveClient.checked) : true
    };

    if (!window.pywebview || !window.pywebview.api) {
      snapshotSettings();
      showToast('Settings saved in preview mode!', 'success');
      return;
    }

    try {
      showToast('Saving settings...', 'info');
      const res = await window.pywebview.api.save_settings(payload);
      if (res && res.success) {
        snapshotSettings();
        if (res.client_list) {
          state.clientList = res.client_list;
          state.clientFolders = res.client_list;
          refreshClientDropdownList(els.activeClientSearch ? els.activeClientSearch.value : '');
        }
        await triggerScanClientFolders(payload.clients_directory);

        if (res.enqueued_count && res.enqueued_count > 0) {
          showToast(`Settings saved! Enqueued ${res.enqueued_count} document(s) from new folder.`, 'success');
        } else {
          showToast('Settings saved successfully!', 'success');
        }
      } else {
        showToast('Settings saved.', 'info');
        snapshotSettings();
      }
    } catch (err) {
      showToast(`Error saving settings: ${err}`, 'error');
    }
  }

  // Attach Dirty Listeners to Settings Form
  if (els.settingsForm) {
    els.settingsForm.addEventListener('input', checkSettingsDirty);
    els.settingsForm.addEventListener('change', checkSettingsDirty);
  }

  // Button Listeners (In-card and Floating)
  if (els.btnSaveSettings) {
    els.btnSaveSettings.addEventListener('click', saveSettingsAction);
  }
  if (els.btnFloatingSaveSettings) {
    els.btnFloatingSaveSettings.addEventListener('click', saveSettingsAction);
  }
  if (els.btnFloatingDiscardSettings) {
    els.btnFloatingDiscardSettings.addEventListener('click', discardSettingsChanges);
  }

  // ============================================================
  // Instructions & Document Types Customization Module
  // ============================================================

  function setInstructionsDirty(isDirty = true) {
    state.isDirtyInstructions = isDirty;
    if (els.txtSaveInstructions) {
      els.txtSaveInstructions.textContent = isDirty ? 'Save Instructions *' : 'Save Instructions';
    }
    if (els.btnSaveInstructions) {
      if (isDirty) {
        els.btnSaveInstructions.style.boxShadow = '0 0 16px rgba(16, 185, 129, 0.6)';
      } else {
        els.btnSaveInstructions.style.boxShadow = '';
      }
    }
  }

  function renderInstructionsUI() {
    if (!els.instructionsCardsList || !state.instructions || !Array.isArray(state.instructions.file_types)) return;

    const fileTypes = state.instructions.file_types;
    const totalCount = fileTypes.length;
    const activeCount = fileTypes.filter(r => r.enabled).length;

    if (els.badgeTotalRules) {
      els.badgeTotalRules.textContent = `${activeCount} Active / ${totalCount} Types`;
    }

    // Populate global rule textareas if not focused
    if (state.instructions.global_instructions) {
      const g = state.instructions.global_instructions;
      if (els.txtSystemRole && document.activeElement !== els.txtSystemRole) {
        els.txtSystemRole.value = g.system_role || '';
      }
      if (els.txtClientRules && document.activeElement !== els.txtClientRules) {
        els.txtClientRules.value = g.client_rules || '';
      }
      if (els.txtFormattingRules && document.activeElement !== els.txtFormattingRules) {
        els.txtFormattingRules.value = g.formatting_rules || '';
      }
    }

    // Filter rules
    const query = (state.instructionsSearch || '').toLowerCase().trim();
    const filter = state.instructionsFilter || 'all';

    const filteredRules = fileTypes.filter(rule => {
      // Status filter
      if (filter === 'active' && !rule.enabled) return false;
      if (filter === 'custom' && rule.is_preset) return false;
      if (filter === 'preset' && !rule.is_preset) return false;

      // Text query
      if (query) {
        const inName = (rule.name || '').toLowerCase().includes(query);
        const inFormat = (rule.naming_format || '').toLowerCase().includes(query);
        const inInst = (rule.instructions || '').toLowerCase().includes(query);
        const inKeywords = (rule.match_keywords || []).some(k => k.toLowerCase().includes(query));
        return inName || inFormat || inInst || inKeywords;
      }

      return true;
    });

    if (filteredRules.length === 0) {
      els.instructionsCardsList.innerHTML = '';
      if (els.instructionsEmptyState) els.instructionsEmptyState.style.display = 'block';
      return;
    }

    if (els.instructionsEmptyState) els.instructionsEmptyState.style.display = 'none';

    // Render cards
    els.instructionsCardsList.innerHTML = filteredRules.map(rule => {
      const keywordsHtml = (rule.match_keywords && rule.match_keywords.length > 0)
        ? rule.match_keywords.map(k => `<span class="keyword-chip">${escapeHtml(k)}</span>`).join('')
        : '<span style="font-size: 11.5px; color: var(--text-muted); font-style: italic;">None specified</span>';

      return `
        <div class="instruction-card ${rule.enabled ? '' : 'disabled-rule'}" data-rule-id="${escapeHtml(rule.id)}">
          <div class="instruction-card-header">
            <div class="instruction-card-title-group">
              <span class="rule-priority-badge">#${rule.priority || 1}</span>
              <span class="instruction-card-name">${escapeHtml(rule.name)}</span>
              <span class="rule-tag ${rule.is_preset ? 'preset' : 'custom'}">${rule.is_preset ? 'Preset' : 'Custom'}</span>
            </div>
            <div class="instruction-card-controls">
              <label class="rule-switch" title="${rule.enabled ? 'Click to disable rule' : 'Click to enable rule'}">
                <input type="checkbox" class="chk-rule-toggle" data-rule-id="${escapeHtml(rule.id)}" ${rule.enabled ? 'checked' : ''}>
                <span class="rule-slider"></span>
              </label>
            </div>
          </div>

          <div class="instruction-format-box">
            <span class="instruction-format-label">Target Format:</span>
            <code class="instruction-format-code">${escapeHtml(rule.naming_format || 'Standard')}</code>
          </div>

          <div class="instruction-keywords-row">
            <span class="instruction-format-label">Trigger Keywords:</span>
            ${keywordsHtml}
          </div>

          ${rule.instructions ? `
            <div class="instruction-snippet-text">${escapeHtml(rule.instructions)}</div>
          ` : ''}

          <div class="instruction-card-actions">
            <button type="button" class="btn-icon-text btn-edit-rule" data-rule-id="${escapeHtml(rule.id)}" title="Edit rule details">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 20h9"></path>
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
              </svg>
              <span>Edit</span>
            </button>
            <button type="button" class="btn-icon-text btn-dup-rule" data-rule-id="${escapeHtml(rule.id)}" title="Duplicate as new custom rule">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              <span>Duplicate</span>
            </button>
            ${!rule.is_preset ? `
            <button type="button" class="btn-icon-text danger btn-delete-rule" data-rule-id="${escapeHtml(rule.id)}" title="Delete custom rule">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
              <span>Delete</span>
            </button>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  }

  function openRuleModal(ruleToEdit = null) {
    if (!els.modalEditInstruction) return;

    if (ruleToEdit) {
      state.editingRuleId = ruleToEdit.id;
      if (els.modalRuleTitle) els.modalRuleTitle.textContent = `Edit Document Type: ${ruleToEdit.name}`;
      if (els.modalRuleSubtitle) els.modalRuleSubtitle.textContent = ruleToEdit.is_preset ? 'Editing preset default document rule' : 'Editing custom document type rule';
      if (els.editRuleId) els.editRuleId.value = ruleToEdit.id;
      if (els.editRuleName) els.editRuleName.value = ruleToEdit.name || '';
      if (els.editRulePriority) els.editRulePriority.value = ruleToEdit.priority || 1;
      if (els.editRuleKeywords) els.editRuleKeywords.value = (ruleToEdit.match_keywords || []).join(', ');
      if (els.editRuleFormat) els.editRuleFormat.value = ruleToEdit.naming_format || '';
      if (els.editRuleInstructions) els.editRuleInstructions.value = ruleToEdit.instructions || '';
      if (els.editRuleEnabled) els.editRuleEnabled.checked = Boolean(ruleToEdit.enabled);
    } else {
      state.editingRuleId = null;
      if (els.modalRuleTitle) els.modalRuleTitle.textContent = 'Add New Document Type';
      if (els.modalRuleSubtitle) els.modalRuleSubtitle.textContent = 'Define recognition keywords, target naming pattern, and extraction instructions';
      if (els.editRuleId) els.editRuleId.value = '';
      if (els.editRuleName) els.editRuleName.value = '';
      if (els.editRulePriority) els.editRulePriority.value = (state.instructions.file_types ? state.instructions.file_types.length + 1 : 1);
      if (els.editRuleKeywords) els.editRuleKeywords.value = '';
      if (els.editRuleFormat) els.editRuleFormat.value = '<Document_Title> MM_DD_YYYY.pdf';
      if (els.editRuleInstructions) els.editRuleInstructions.value = '';
      if (els.editRuleEnabled) els.editRuleEnabled.checked = true;
    }

    els.modalEditInstruction.style.display = 'flex';
    setTimeout(() => {
      if (els.editRuleName) els.editRuleName.focus();
    }, 50);
  }

  function closeRuleModal() {
    if (els.modalEditInstruction) {
      els.modalEditInstruction.style.display = 'none';
      state.editingRuleId = null;
    }
  }

  function saveRuleFromModal() {
    const name = (els.editRuleName.value || '').trim();
    if (!name) {
      showToast('Please enter a Document / File Type Name', 'error');
      if (els.editRuleName) els.editRuleName.focus();
      return;
    }

    const format = (els.editRuleFormat.value || '').trim();
    if (!format) {
      showToast('Please enter a Target Filename Format Pattern', 'error');
      if (els.editRuleFormat) els.editRuleFormat.focus();
      return;
    }

    const priority = parseInt(els.editRulePriority.value, 10) || 1;
    const rawKeywords = (els.editRuleKeywords.value || '').split(',');
    const keywords = rawKeywords.map(k => k.trim()).filter(k => k.length > 0);
    const instructions = (els.editRuleInstructions.value || '').trim();
    const enabled = Boolean(els.editRuleEnabled.checked);

    if (state.editingRuleId) {
      // Updating existing rule
      const idx = state.instructions.file_types.findIndex(r => r.id === state.editingRuleId);
      if (idx !== -1) {
        const existing = state.instructions.file_types[idx];
        state.instructions.file_types[idx] = {
          ...existing,
          name,
          priority,
          match_keywords: keywords,
          naming_format: format,
          instructions,
          enabled
        };
      }
    } else {
      // Adding new custom rule
      const newId = 'custom_' + Date.now();
      state.instructions.file_types.push({
        id: newId,
        name,
        is_preset: false,
        priority,
        match_keywords: keywords,
        naming_format: format,
        instructions,
        enabled
      });
    }

    // Sort by priority
    state.instructions.file_types.sort((a, b) => (a.priority || 999) - (b.priority || 999));

    setInstructionsDirty(true);
    renderInstructionsUI();
    closeRuleModal();
    showToast(`Document rule "${name}" saved in draft. Click "Save Instructions" to commit changes.`, 'info');
  }

  // Search & Filter listeners
  if (els.instructionsSearch) {
    els.instructionsSearch.addEventListener('input', (e) => {
      state.instructionsSearch = e.target.value;
      renderInstructionsUI();
    });
  }

  document.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.instructionsFilter = pill.getAttribute('data-filter') || 'all';
      renderInstructionsUI();
    });
  });

  // Global instructions textarea change listeners
  [els.txtSystemRole, els.txtClientRules, els.txtFormattingRules].forEach(input => {
    if (input) {
      input.addEventListener('input', () => {
        if (!state.instructions.global_instructions) {
          state.instructions.global_instructions = {};
        }
        if (els.txtSystemRole) state.instructions.global_instructions.system_role = els.txtSystemRole.value;
        if (els.txtClientRules) state.instructions.global_instructions.client_rules = els.txtClientRules.value;
        if (els.txtFormattingRules) state.instructions.global_instructions.formatting_rules = els.txtFormattingRules.value;
        setInstructionsDirty(true);
      });
    }
  });

  // Toggle Global Rules Collapsible
  if (els.btnToggleGlobalRules) {
    els.btnToggleGlobalRules.addEventListener('click', () => {
      const isOpen = els.globalInstructionsBody.style.display !== 'none';
      els.globalInstructionsBody.style.display = isOpen ? 'none' : 'block';
      if (els.iconChevronGlobal) {
        els.iconChevronGlobal.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(180deg)';
      }
    });
  }

  // Cards List Action delegation
  if (els.instructionsCardsList) {
    els.instructionsCardsList.addEventListener('click', (e) => {
      // Toggle
      const toggle = e.target.closest('.chk-rule-toggle');
      if (toggle) {
        const ruleId = toggle.getAttribute('data-rule-id');
        const rule = state.instructions.file_types.find(r => r.id === ruleId);
        if (rule) {
          rule.enabled = toggle.checked;
          setInstructionsDirty(true);
          renderInstructionsUI();
        }
        return;
      }

      // Edit
      const editBtn = e.target.closest('.btn-edit-rule');
      if (editBtn) {
        const ruleId = editBtn.getAttribute('data-rule-id');
        const rule = state.instructions.file_types.find(r => r.id === ruleId);
        if (rule) openRuleModal(rule);
        return;
      }

      // Duplicate
      const dupBtn = e.target.closest('.btn-dup-rule');
      if (dupBtn) {
        const ruleId = dupBtn.getAttribute('data-rule-id');
        const rule = state.instructions.file_types.find(r => r.id === ruleId);
        if (rule) {
          const duplicated = {
            ...rule,
            id: 'custom_' + Date.now(),
            name: `${rule.name} (Copy)`,
            is_preset: false,
            priority: (rule.priority || 1) + 1
          };
          state.instructions.file_types.push(duplicated);
          state.instructions.file_types.sort((a, b) => (a.priority || 999) - (b.priority || 999));
          setInstructionsDirty(true);
          renderInstructionsUI();
          showToast(`Duplicated "${rule.name}" as custom rule.`, 'info');
        }
        return;
      }

      // Delete
      const delBtn = e.target.closest('.btn-delete-rule');
      if (delBtn) {
        const ruleId = delBtn.getAttribute('data-rule-id');
        const rule = state.instructions.file_types.find(r => r.id === ruleId);
        if (rule) {
          if (confirm(`Delete custom rule "${rule.name}"?`)) {
            state.instructions.file_types = state.instructions.file_types.filter(r => r.id !== ruleId);
            setInstructionsDirty(true);
            renderInstructionsUI();
            showToast(`Deleted rule "${rule.name}".`, 'info');
          }
        }
        return;
      }
    });
  }

  // Add rule button
  if (els.btnAddFileType) {
    els.btnAddFileType.addEventListener('click', () => openRuleModal(null));
  }

  // Modal actions
  if (els.btnCloseRuleModal) els.btnCloseRuleModal.addEventListener('click', closeRuleModal);
  if (els.btnCancelRuleModal) els.btnCancelRuleModal.addEventListener('click', closeRuleModal);
  if (els.btnSaveRuleModal) els.btnSaveRuleModal.addEventListener('click', saveRuleFromModal);

  // Close modals on Escape key or backdrop click
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (els.modalEditInstruction && els.modalEditInstruction.style.display !== 'none') {
        closeRuleModal();
      }
      if (els.modalPromptPreview && els.modalPromptPreview.style.display !== 'none') {
        els.modalPromptPreview.style.display = 'none';
      }
    }
  });

  [els.modalEditInstruction, els.modalPromptPreview].forEach(backdrop => {
    if (backdrop) {
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
          backdrop.style.display = 'none';
          if (backdrop === els.modalEditInstruction) state.editingRuleId = null;
        }
      });
    }
  });

  // Save Instructions Action
  if (els.btnSaveInstructions) {
    els.btnSaveInstructions.addEventListener('click', async () => {
      if (!window.pywebview || !window.pywebview.api) {
        showToast('Connecting to desktop backend...', 'info');
        return;
      }

      try {
        showToast('Saving document instructions...', 'info');
        const res = await window.pywebview.api.save_instructions(state.instructions);
        if (res && res.success) {
          if (res.instructions) state.instructions = res.instructions;
          if (res.prompt_preview) state.promptPreview = res.prompt_preview;
          setInstructionsDirty(false);
          renderInstructionsUI();
          showToast('Document instructions saved and applied to active ingestion!', 'success');
        } else {
          showToast(`Failed to save instructions: ${res ? res.error : 'Unknown error'}`, 'error');
        }
      } catch (err) {
        showToast(`Save error: ${err}`, 'error');
      }
    });
  }

  // Reset Instructions Action
  if (els.btnResetInstructions) {
    els.btnResetInstructions.addEventListener('click', async () => {
      if (!window.pywebview || !window.pywebview.api) return;

      if (!confirm('Are you sure you want to reset all document instructions to preset defaults? Any custom document types will be removed.')) {
        return;
      }

      try {
        showToast('Resetting document instructions...', 'info');
        const res = await window.pywebview.api.reset_instructions();
        if (res && res.success) {
          if (res.instructions) state.instructions = res.instructions;
          if (res.prompt_preview) state.promptPreview = res.prompt_preview;
          setInstructionsDirty(false);
          renderInstructionsUI();
          showToast('Document instructions restored to preset defaults.', 'info');
        } else {
          showToast(`Reset failed: ${res ? res.error : 'Unknown error'}`, 'error');
        }
      } catch (err) {
        showToast(`Reset error: ${err}`, 'error');
      }
    });
  }

  // Prompt Preview Modal Action
  if (els.btnPreviewPrompt) {
    els.btnPreviewPrompt.addEventListener('click', async () => {
      if (window.pywebview && window.pywebview.api) {
        try {
          const res = await window.pywebview.api.get_instructions();
          if (res && res.prompt_preview) {
            state.promptPreview = res.prompt_preview;
          }
        } catch (e) {
          console.warn('Could not refresh prompt preview:', e);
        }
      }

      let preview = state.promptPreview;
      if (!preview && state.instructions) {
        const g = state.instructions.global_instructions || {};
        const activeRules = (state.instructions.file_types || [])
          .filter(r => r.enabled !== false)
          .sort((a, b) => (a.priority || 99) - (b.priority || 99))
          .map((r, idx) => `Rule ${idx + 1} (${r.name}):\n- Match Keywords: ${(r.match_keywords || r.keywords || []).join(', ')}\n- Format: "${r.naming_format || r.format_pattern || ''}"\n- Guidance: ${r.instructions || ''}`)
          .join('\n\n');

        const parts = [];
        if (g.system_role) parts.push(g.system_role);
        if (activeRules) parts.push(`### DOCUMENT TYPE CLASSIFICATION RULES:\n${activeRules}`);
        if (g.client_rules) parts.push(g.client_rules);
        if (g.formatting_rules) parts.push(g.formatting_rules);
        preview = parts.join('\n\n').trim();
      }

      if (els.promptPreviewText) {
        els.promptPreviewText.textContent = preview || 'No prompt preview available.';
      }
      if (els.modalPromptPreview) {
        els.modalPromptPreview.style.display = 'flex';
      }
    });
  }

  if (els.btnClosePromptModal) {
    els.btnClosePromptModal.addEventListener('click', () => {
      if (els.modalPromptPreview) els.modalPromptPreview.style.display = 'none';
    });
  }
  if (els.btnDismissPromptModal) {
    els.btnDismissPromptModal.addEventListener('click', () => {
      if (els.modalPromptPreview) els.modalPromptPreview.style.display = 'none';
    });
  }

  if (els.btnCopyPrompt) {
    els.btnCopyPrompt.addEventListener('click', async () => {
      const text = (els.promptPreviewText && els.promptPreviewText.textContent) || state.promptPreview || '';
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        if (els.txtCopyPrompt) els.txtCopyPrompt.textContent = 'Copied to Clipboard!';
        showToast('Prompt copied to clipboard!', 'success');
        setTimeout(() => {
          if (els.txtCopyPrompt) els.txtCopyPrompt.textContent = 'Copy Prompt to Clipboard';
        }, 2500);
      } catch (err) {
        showToast('Could not copy to clipboard.', 'error');
      }
    });
  }

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
          if (els.settingClientsDir) {
            els.settingClientsDir.value = s.clients_directory || '';
          }
          els.settingProvider.value = s.provider || 'native';
          els.settingModel.value = s.model_name || 'Built-in Rules + Local PP-OCR';
          els.settingApiKey.value = s.api_key || '';
          els.settingWorkers.value = s.num_workers || 2;
          els.settingStability.value = s.stability_timeout || 30;
          els.settingWrapup.checked = Boolean(s.enable_wrapup);
          els.settingDocx.checked = Boolean(s.update_clients_docx);
          if (els.settingEnableActiveClient && s.enable_active_client !== undefined) {
            els.settingEnableActiveClient.checked = Boolean(s.enable_active_client);
          }
          updateProviderUI(els.settingProvider.value);
          snapshotSettings();
        }

        if (data.recent_records && Array.isArray(data.recent_records)) {
          data.recent_records.forEach(rec => addDocumentToFeed(rec));
        }

        if (data.client_list && Array.isArray(data.client_list)) {
          state.clientList = data.client_list;
        }

        if (data.instructions) {
          state.instructions = data.instructions;
          state.promptPreview = data.prompt_preview || '';
          renderInstructionsUI();
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

  // Standalone browser preview fallback (when opened directly in browser or subagent)
  window.addEventListener('DOMContentLoaded', () => {
    setTimeout(async () => {
      if (!window.pywebview && (!state.instructions.file_types || state.instructions.file_types.length === 0)) {
        try {
          const res = await fetch('../instructions.json');
          if (res.ok) {
            const data = await res.json();
            if (data && data.file_types) {
              state.instructions = data;
              renderInstructionsUI();
            }
          }
        } catch (e) {
          console.debug('Standalone fallback instructions fetch not available:', e);
        }

        try {
          const sRes = await fetch('../settings.json');
          if (sRes.ok) {
            const sData = await sRes.json();
            if (sData) {
              if (els.settingWatchDir && sData.watch_directories) els.settingWatchDir.value = sData.watch_directories[0] || '';
              if (els.settingClientsDir) els.settingClientsDir.value = sData.clients_directory || '';
              if (els.settingProvider && sData.provider) els.settingProvider.value = sData.provider;
              if (els.settingModel && sData.model_name) els.settingModel.value = sData.model_name;
              if (els.settingWorkers && sData.num_workers) els.settingWorkers.value = sData.num_workers;
              if (els.settingStability && sData.stability_timeout) els.settingStability.value = sData.stability_timeout;
              updateProviderUI(els.settingProvider ? els.settingProvider.value : 'native');
            }
          }
        } catch (e) {
          console.debug('Standalone fallback settings fetch not available:', e);
        }

        snapshotSettings();
      }
    }, 150);
  });

  // Close any open client dropdowns when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.doc-client-dropdown-wrap')) {
      document.querySelectorAll('.doc-client-dropdown-wrap.open').forEach(w => {
        w.classList.remove('open');
        const m = w.querySelector('.client-dropdown-menu');
        if (m) m.style.display = 'none';
      });
    }
  });

})();
