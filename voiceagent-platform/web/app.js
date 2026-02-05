/**
 * VoiceAgent Platform - Web Dashboard
 *
 * Modules:
 *   State            - Centralized app state
 *   WS               - WebSocket with auto-reconnect
 *   MessageHandler   - Dispatches WS messages to handlers
 *   UI               - DOM update methods
 *   Tabs             - Tab switching
 */
(function () {
    'use strict';

    // ============================================
    // STATE
    // ============================================
    var State = {
        wsConnected: false,
        sipRegistered: false,
        callActive: false,
        callerId: null,
        activeAgent: null,
        availableAgents: [],
        aiMuted: false,
        firewallEnabled: true,
        codingProgress: {
            projectId: null,
            status: 'idle',
            currentAction: '',
            filesChanged: [],
            toolsUsed: [],
        },
    };

    // ============================================
    // DOM CACHE
    // ============================================
    var DOM = {};

    function cacheDOMReferences() {
        DOM.sipStatus    = document.getElementById('sip-status');
        DOM.sipDot       = DOM.sipStatus.querySelector('.status-badge__dot');
        DOM.sipLabel     = DOM.sipStatus.querySelector('.status-badge__label');
        DOM.callStatus   = document.getElementById('call-status');
        DOM.callDot      = DOM.callStatus.querySelector('.status-badge__dot');
        DOM.callLabel    = DOM.callStatus.querySelector('.status-badge__label');
        DOM.agentSelect  = document.getElementById('agent-select');
        DOM.btnMute      = document.getElementById('btn-mute');
        DOM.btnHangup    = document.getElementById('btn-hangup');
        DOM.wsStatus     = document.getElementById('ws-status');
        DOM.wsDot        = DOM.wsStatus.querySelector('.status-badge__dot');

        DOM.transcript        = document.getElementById('transcript');
        DOM.btnClearTranscript = document.getElementById('btn-clear-transcript');

        DOM.tabButtons = document.querySelectorAll('.tabs__tab');
        DOM.tabPanels  = document.querySelectorAll('.tabs__content');

        DOM.taskList       = document.getElementById('task-list');
        DOM.codingStatus   = document.getElementById('coding-status');
        DOM.codingProject  = document.getElementById('coding-project');
        DOM.codingProgress = document.getElementById('coding-progress');
        DOM.codingFiles    = document.getElementById('coding-files');
        DOM.codingTools    = document.getElementById('coding-tools');
        DOM.ideasList      = document.getElementById('ideas-list');
        DOM.blacklistList  = document.getElementById('blacklist-list');
        DOM.agentsList     = document.getElementById('agents-list');
        DOM.firewallStatus = document.getElementById('firewall-status');
        DOM.btnFirewallToggle = document.getElementById('btn-firewall-toggle');
        DOM.debugLog       = document.getElementById('debug-log');
        DOM.btnClearDebug  = document.getElementById('btn-clear-debug');
        DOM.statusbarText  = document.getElementById('statusbar-text');
    }

    // ============================================
    // HELPERS
    // ============================================
    function esc(str) {
        var d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function ts() {
        return new Date().toTimeString().substring(0, 8);
    }

    function addTranscriptLine(role, text) {
        var prefixes = { caller: 'Anrufer', user: 'Anrufer', assistant: 'AI', system: 'System' };
        var cls = role === 'user' ? 'caller' : (role || 'system');
        var prefix = prefixes[role] || role;

        var div = document.createElement('div');
        div.className = 'transcript__line transcript__line--' + cls;
        div.innerHTML =
            '<span class="transcript__prefix">[' + esc(prefix) + ']</span>' +
            '<span class="transcript__text">' + esc(text) + '</span>';

        DOM.transcript.appendChild(div);

        // Auto-scroll if near bottom
        var el = DOM.transcript;
        if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
            el.scrollTop = el.scrollHeight;
        }
    }

    function addDebug(text) {
        if (!DOM.debugLog) return;
        var div = document.createElement('div');
        div.className = 'debug-log__line';
        div.innerHTML = '<span class="debug-log__timestamp">' + ts() + '</span>' + esc(text);
        DOM.debugLog.appendChild(div);

        while (DOM.debugLog.children.length > 500) {
            DOM.debugLog.removeChild(DOM.debugLog.firstChild);
        }
        DOM.debugLog.scrollTop = DOM.debugLog.scrollHeight;
    }

    // ============================================
    // WEBSOCKET
    // ============================================
    var WS = {
        socket: null,
        reconnectTimer: null,

        connect: function () {
            var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            var url = protocol + '//' + location.host + '/ws';

            try {
                this.socket = new WebSocket(url);
            } catch (e) {
                this.scheduleReconnect();
                return;
            }

            var self = this;

            this.socket.onopen = function () {
                State.wsConnected = true;
                clearTimeout(self.reconnectTimer);
                UI.setWSConnected(true);
                UI.setStatusBar('Verbunden');
                addDebug('[WS] Verbunden');
            };

            this.socket.onclose = function () {
                State.wsConnected = false;
                UI.setWSConnected(false);
                UI.setStatusBar('Verbindung verloren - Reconnect...');
                addDebug('[WS] Getrennt');
                self.scheduleReconnect();
            };

            this.socket.onerror = function () {
                addDebug('[WS] Fehler');
            };

            this.socket.onmessage = function (event) {
                try {
                    var data = JSON.parse(event.data);
                    MessageHandler.dispatch(data);
                } catch (e) {
                    addDebug('[WS] Parse-Fehler: ' + e.message);
                }
            };
        },

        scheduleReconnect: function () {
            var self = this;
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = setTimeout(function () { self.connect(); }, 3000);
        },

        send: function (msg) {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify(msg));
            }
        },
    };

    // ============================================
    // MESSAGE HANDLER
    // ============================================
    var MessageHandler = {
        dispatch: function (data) {
            var handler = this.handlers[data.type];
            if (handler) {
                handler(data);
            } else {
                addDebug('[MSG] Unbekannt: ' + data.type);
            }
        },

        handlers: {
            status: function (data) {
                State.sipRegistered = data.sip_registered || false;
                State.callActive = data.call_active || false;
                State.activeAgent = data.active_agent || null;
                State.availableAgents = data.available_agents || [];

                UI.setSIPStatus(State.sipRegistered);
                UI.setCallStatus(State.callActive, null);
                UI.populateAgents(State.availableAgents, State.activeAgent);

                fetchAgentsInfo();
                fetchTasks();
            },

            call_incoming: function (data) {
                State.callerId = data.caller_id || 'Unbekannt';
                UI.setCallIncoming(State.callerId);
                addTranscriptLine('system', 'Eingehender Anruf: ' + State.callerId);
                addDebug('[CALL] Eingehend: ' + State.callerId);
            },

            call_active: function (data) {
                State.callActive = true;
                State.callerId = data.caller_id || 'Aktiv';
                UI.setCallActive(State.callerId);
                DOM.btnHangup.disabled = false;
                DOM.btnMute.disabled = false;
                if (data.agent) {
                    addTranscriptLine('system', 'Agent: ' + data.agent);
                }
                addDebug('[CALL] Aktiv: ' + State.callerId);
            },

            call_ended: function (data) {
                State.callActive = false;
                State.callerId = null;
                UI.setCallEnded();
                addTranscriptLine('system', 'Anruf beendet' + (data.reason ? ': ' + data.reason : ''));
                addDebug('[CALL] Beendet: ' + (data.reason || ''));
            },

            call_rejected: function (data) {
                addTranscriptLine('system', 'Abgelehnt: ' + (data.caller_id || '') + ' (' + (data.reason || '') + ')');
                addDebug('[CALL] Abgelehnt: ' + (data.reason || ''));
            },

            transcript: function (data) {
                if (data.text && data.is_final) {
                    addTranscriptLine(data.role || 'system', data.text);
                }
            },

            function_call: function (data) {
                addDebug('[Tool] ' + (data.name || ''));
            },

            function_result: function (data) {
                var result = (data.result || '').substring(0, 100);
                addDebug('[Tool Result] ' + (data.name || '') + ': ' + result);
            },

            agent_changed: function (data) {
                State.activeAgent = data.new_agent || '';
                addTranscriptLine('system', 'Agent: ' + (data.old_agent || '') + ' → ' + State.activeAgent);
                UI.updateAgentSelect(State.activeAgent);
                fetchAgentsInfo();
                addDebug('[AGENT] ' + (data.old_agent || '') + ' → ' + State.activeAgent);
            },

            coding_progress: function (data) {
                var cp = State.codingProgress;
                cp.projectId = data.project_id || cp.projectId;
                cp.status = data.status || 'running';
                cp.currentAction = data.current_action || '';
                if (data.files_changed) cp.filesChanged = data.files_changed;
                if (data.tools_used) cp.toolsUsed = data.tools_used;

                UI.updateCodingPanel(cp);
                addDebug('[CODING] ' + cp.status + ': ' + cp.currentAction.substring(0, 80));
            },

            firewall_status: function (data) {
                State.firewallEnabled = data.enabled;
                UI.updateFirewall(data.enabled);
            },

            blacklist_updated: function () {
                fetchBlacklist();
                addDebug('[BLACKLIST] Aktualisiert');
            },
        },
    };

    // ============================================
    // UI
    // ============================================
    var UI = {
        setWSConnected: function (connected) {
            DOM.wsDot.className = 'status-badge__dot ' +
                (connected ? 'status-badge__dot--online' : 'status-badge__dot--offline');
        },

        setSIPStatus: function (registered) {
            DOM.sipDot.className = 'status-badge__dot ' +
                (registered ? 'status-badge__dot--online' : 'status-badge__dot--offline');
            DOM.sipLabel.textContent = registered ? 'SIP: Registriert' : 'SIP: Offline';
        },

        setCallStatus: function (active, callerId) {
            if (active) {
                DOM.callDot.className = 'status-badge__dot status-badge__dot--active';
                DOM.callLabel.textContent = 'Anruf aktiv' + (callerId ? ': ' + callerId : '');
                DOM.btnHangup.disabled = false;
                DOM.btnMute.disabled = false;
            } else {
                DOM.callDot.className = 'status-badge__dot status-badge__dot--offline';
                DOM.callLabel.textContent = 'Kein Anruf';
                DOM.btnHangup.disabled = true;
                DOM.btnMute.disabled = true;
            }
        },

        setCallIncoming: function (callerId) {
            DOM.callDot.className = 'status-badge__dot status-badge__dot--warning';
            DOM.callLabel.textContent = 'Eingehend: ' + callerId;
        },

        setCallActive: function (callerId) {
            DOM.callDot.className = 'status-badge__dot status-badge__dot--active';
            DOM.callLabel.textContent = 'Anruf aktiv: ' + callerId;
            DOM.btnHangup.disabled = false;
            DOM.btnMute.disabled = false;
        },

        setCallEnded: function () {
            DOM.callDot.className = 'status-badge__dot status-badge__dot--offline';
            DOM.callLabel.textContent = 'Kein Anruf';
            DOM.btnHangup.disabled = true;
            DOM.btnMute.disabled = true;
            // Reset mute state
            State.aiMuted = false;
            DOM.btnMute.textContent = 'Stumm';
            DOM.btnMute.classList.remove('btn--muted');
        },

        setStatusBar: function (text) {
            DOM.statusbarText.textContent = text;
        },

        populateAgents: function (agents, activeAgent) {
            DOM.agentSelect.innerHTML = '';
            agents.forEach(function (name) {
                var opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                if (name === activeAgent) opt.selected = true;
                DOM.agentSelect.appendChild(opt);
            });
        },

        updateAgentSelect: function (name) {
            var opts = DOM.agentSelect.options;
            for (var i = 0; i < opts.length; i++) {
                if (opts[i].value === name) {
                    DOM.agentSelect.selectedIndex = i;
                    break;
                }
            }
        },

        updateTasks: function (tasks) {
            DOM.taskList.innerHTML = '';
            if (!tasks || tasks.length === 0) {
                DOM.taskList.innerHTML = '<div class="empty-state">Keine Tasks</div>';
                return;
            }

            tasks.forEach(function (task) {
                var div = document.createElement('div');
                div.className = 'task-item';

                var cancel = '';
                if (task.status === 'pending' || task.status === 'running') {
                    cancel = '<button class="btn btn--small btn--ghost" data-task-id="' +
                        task.id + '">Abbrechen</button>';
                }

                div.innerHTML =
                    '<span class="task-item__desc">' + esc(task.description || '') + '</span>' +
                    '<span class="task-item__status task-item__status--' + task.status + '">' +
                    task.status + '</span>' + cancel;
                DOM.taskList.appendChild(div);
            });

            DOM.taskList.querySelectorAll('[data-task-id]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    cancelTask(this.getAttribute('data-task-id'));
                });
            });
        },

        updateCodingPanel: function (progress) {
            // Indicator
            var ind = DOM.codingStatus.querySelector('.coding-panel__indicator');
            ind.className = 'coding-panel__indicator';
            if (progress.status !== 'idle') {
                ind.classList.add('coding-panel__indicator--' + progress.status);
            }

            var label = { idle: 'Bereit', running: 'Laeuft...', completed: 'Fertig', failed: 'Fehler' };
            DOM.codingStatus.querySelector('span:last-child').textContent = label[progress.status] || progress.status;

            // Project
            if (progress.projectId) {
                DOM.codingProject.textContent = 'Projekt: ' + progress.projectId;
            }

            // Progress line
            if (progress.currentAction) {
                var line = document.createElement('div');
                var isTool = progress.currentAction.indexOf('[Tool:') === 0;
                line.className = 'coding-panel__progress-line' + (isTool ? ' coding-panel__progress-line--tool' : '');
                line.textContent = progress.currentAction;
                DOM.codingProgress.appendChild(line);
                DOM.codingProgress.scrollTop = DOM.codingProgress.scrollHeight;
            }

            // Files
            DOM.codingFiles.innerHTML = '';
            (progress.filesChanged || []).forEach(function (f) {
                var li = document.createElement('li');
                li.textContent = f;
                DOM.codingFiles.appendChild(li);
            });

            // Tools (deduplicated)
            DOM.codingTools.innerHTML = '';
            var seen = {};
            (progress.toolsUsed || []).forEach(function (t) {
                if (seen[t]) return;
                seen[t] = true;
                var span = document.createElement('span');
                span.className = 'coding-panel__tool-tag';
                span.textContent = t;
                DOM.codingTools.appendChild(span);
            });
        },

        updateAgentsPanel: function (agents, activeAgent) {
            DOM.agentsList.innerHTML = '';
            agents.forEach(function (agent) {
                var div = document.createElement('div');
                div.className = 'agent-card' + (agent.name === activeAgent ? ' agent-card--active' : '');
                div.innerHTML =
                    '<div class="agent-card__name">' + esc(agent.display_name || agent.name) + '</div>' +
                    '<div class="agent-card__desc">' + esc(agent.description || '') + '</div>' +
                    '<div class="agent-card__meta">' + (agent.tools_count || 0) + ' Tools</div>';
                DOM.agentsList.appendChild(div);
            });
        },

        updateFirewall: function (enabled) {
            DOM.firewallStatus.textContent = 'Status: ' + (enabled ? 'Aktiv' : 'DEAKTIVIERT');
            DOM.firewallStatus.style.color = enabled ? '' : 'var(--ctp-red)';
        },

        updateBlacklist: function (entries) {
            DOM.blacklistList.innerHTML = '';
            if (!entries || entries.length === 0) {
                DOM.blacklistList.innerHTML = '<div class="empty-state">Keine gesperrten Nummern</div>';
                return;
            }

            entries.forEach(function (entry) {
                var div = document.createElement('div');
                div.className = 'blacklist-item';

                var date = entry.blocked_at ? new Date(entry.blocked_at).toLocaleString('de-DE') : '';

                div.innerHTML =
                    '<div class="blacklist-item__info">' +
                        '<span class="blacklist-item__number">' + esc(entry.caller_id || '') + '</span>' +
                        '<span class="blacklist-item__meta">' + esc(date) +
                        (entry.reason ? ' — ' + esc(entry.reason) : '') + '</span>' +
                    '</div>' +
                    '<button class="btn btn--small btn--danger blacklist-item__remove" data-caller-id="' +
                        esc(entry.caller_id || '') + '">&#10005;</button>';

                DOM.blacklistList.appendChild(div);
            });

            DOM.blacklistList.querySelectorAll('[data-caller-id]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    removeFromBlacklist(this.getAttribute('data-caller-id'));
                });
            });
        },
    };

    // ============================================
    // REST API
    // ============================================
    function fetchAgentsInfo() {
        fetch('/agents')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                UI.updateAgentsPanel(data.agents || [], data.active);
            })
            .catch(function (e) { addDebug('[API] Agents: ' + e.message); });
    }

    function fetchTasks() {
        fetch('/tasks')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                UI.updateTasks(data.tasks || []);
            })
            .catch(function (e) { addDebug('[API] Tasks: ' + e.message); });
    }

    function cancelTask(taskId) {
        fetch('/tasks/' + taskId + '/cancel', { method: 'POST' })
            .then(function () { fetchTasks(); })
            .catch(function (e) { addDebug('[API] Cancel: ' + e.message); });
    }

    function fetchBlacklist() {
        fetch('/blacklist')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                UI.updateBlacklist(data.entries || []);
            })
            .catch(function (e) { addDebug('[API] Blacklist: ' + e.message); });
    }

    function removeFromBlacklist(callerId) {
        fetch('/blacklist/' + encodeURIComponent(callerId), { method: 'DELETE' })
            .then(function () { fetchBlacklist(); })
            .catch(function (e) { addDebug('[API] Blacklist Remove: ' + e.message); });
    }

    function toggleFirewall() {
        fetch('/firewall', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: !State.firewallEnabled }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                State.firewallEnabled = data.enabled;
                UI.updateFirewall(data.enabled);
            })
            .catch(function (e) { addDebug('[API] Firewall: ' + e.message); });
    }

    // ============================================
    // TABS
    // ============================================
    function initTabs() {
        DOM.tabButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                var target = this.getAttribute('data-tab');

                DOM.tabButtons.forEach(function (b) {
                    b.classList.remove('tabs__tab--active');
                    b.setAttribute('aria-selected', 'false');
                });
                DOM.tabPanels.forEach(function (p) {
                    p.classList.remove('tabs__content--active');
                });

                this.classList.add('tabs__tab--active');
                this.setAttribute('aria-selected', 'true');
                document.getElementById('tab-' + target).classList.add('tabs__content--active');
            });
        });
    }

    // ============================================
    // EVENT BINDINGS
    // ============================================
    function bindEvents() {
        DOM.btnHangup.addEventListener('click', function () {
            WS.send({ type: 'hangup' });
        });

        DOM.btnMute.addEventListener('click', function () {
            State.aiMuted = !State.aiMuted;
            if (State.aiMuted) {
                WS.send({ type: 'mute_ai' });
                DOM.btnMute.textContent = 'Unmute';
                DOM.btnMute.classList.add('btn--muted');
            } else {
                WS.send({ type: 'unmute_ai' });
                DOM.btnMute.textContent = 'Stumm';
                DOM.btnMute.classList.remove('btn--muted');
            }
        });

        DOM.agentSelect.addEventListener('change', function () {
            var name = this.value;
            if (name && name !== State.activeAgent) {
                WS.send({ type: 'switch_agent', agent_name: name });
            }
        });

        DOM.btnClearTranscript.addEventListener('click', function () {
            DOM.transcript.innerHTML = '';
        });

        DOM.btnClearDebug.addEventListener('click', function () {
            DOM.debugLog.innerHTML = '';
        });

        DOM.btnFirewallToggle.addEventListener('click', toggleFirewall);
    }

    // ============================================
    // INIT
    // ============================================
    function init() {
        cacheDOMReferences();
        initTabs();
        bindEvents();
        WS.connect();

        // Periodic refresh
        setInterval(fetchTasks, 10000);
        setInterval(fetchBlacklist, 10000);
        fetchBlacklist();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
