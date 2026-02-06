/**
 * VoiceAgent Platform - Web Dashboard
 *
 * Modules:
 *   State            - Centralized app state
 *   Mobile           - Viewport detection & mobile state
 *   WS               - WebSocket with auto-reconnect
 *   MessageHandler   - Dispatches WS messages to handlers
 *   UI               - DOM update methods
 *   Tabs             - Tab switching (desktop + mobile bottom nav)
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
        aiState: 'idle',
        callCost: 0,
        currentModel: 'mini',
        firewallEnabled: true,
        ideas: [],
        projects: [],
        codingProgress: {
            projectId: null,
            status: 'idle',
            currentAction: '',
            filesChanged: [],
            toolsUsed: [],
        },
    };

    // ============================================
    // MOBILE STATE
    // ============================================
    var Mobile = {
        isMobile: false,
        menuOpen: false,
        breakpoint: 768,

        check: function () {
            this.isMobile = window.innerWidth <= this.breakpoint;
            return this.isMobile;
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
        DOM.aiStatus     = document.getElementById('ai-status');
        DOM.aiDot        = DOM.aiStatus.querySelector('.status-badge__dot');
        DOM.aiLabel      = DOM.aiStatus.querySelector('.status-badge__label');
        DOM.callCost     = document.getElementById('call-cost');
        DOM.costLabel    = DOM.callCost.querySelector('.cost-badge__label');
        DOM.modelBadge   = document.getElementById('model-badge');
        DOM.modelLabel   = DOM.modelBadge.querySelector('.model-badge__label');
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
        DOM.btnRefreshIdeas = document.getElementById('btn-refresh-ideas');
        DOM.blacklistList  = document.getElementById('blacklist-list');
        DOM.whitelistList  = document.getElementById('whitelist-list');
        DOM.callerActions  = document.getElementById('caller-actions');
        DOM.callerActionsNumber = document.getElementById('caller-actions-number');
        DOM.btnAddBlacklist = document.getElementById('btn-add-blacklist');
        DOM.btnAddWhitelist = document.getElementById('btn-add-whitelist');
        DOM.agentsList     = document.getElementById('agents-list');
        DOM.firewallStatus = document.getElementById('firewall-status');
        DOM.btnFirewallToggle = document.getElementById('btn-firewall-toggle');
        DOM.debugLog       = document.getElementById('debug-log');
        DOM.btnClearDebug  = document.getElementById('btn-clear-debug');
        DOM.statusbarText  = document.getElementById('statusbar-text');

        // Mobile elements
        DOM.btnMenuToggle      = document.getElementById('btn-menu-toggle');
        DOM.headerCollapsible  = document.getElementById('header-collapsible');
        DOM.bottomNav          = document.getElementById('bottom-nav');
        DOM.bottomNavItems     = document.querySelectorAll('.bottom-nav__item');
        DOM.mobileTranscript   = document.getElementById('mobile-transcript');
    }

    // ============================================
    // HELPERS
    // ============================================
    function esc(str) {
        var d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function escAttr(str) {
        return esc(str).replace(/"/g, '&quot;');
    }

    function ts() {
        return new Date().toTimeString().substring(0, 8);
    }

    function autoScroll(el) {
        if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
            el.scrollTop = el.scrollHeight;
        }
    }

    function addTranscriptLine(role, text) {
        var prefixes = { caller: 'Anrufer', user: 'Anrufer', assistant: 'AI', system: 'System' };
        var cls = role === 'user' ? 'caller' : (role || 'system');
        var prefix = prefixes[role] || role;

        var html =
            '<span class="transcript__prefix">[' + esc(prefix) + ']</span>' +
            '<span class="transcript__text">' + esc(text) + '</span>';

        // Desktop transcript panel
        var div1 = document.createElement('div');
        div1.className = 'transcript__line transcript__line--' + cls;
        div1.innerHTML = html;
        DOM.transcript.appendChild(div1);
        autoScroll(DOM.transcript);

        // Mobile transcript tab
        if (DOM.mobileTranscript) {
            var div2 = document.createElement('div');
            div2.className = 'transcript__line transcript__line--' + cls;
            div2.innerHTML = html;
            DOM.mobileTranscript.appendChild(div2);
            autoScroll(DOM.mobileTranscript);
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
                State.currentModel = data.current_model || 'mini';

                UI.setSIPStatus(State.sipRegistered);
                UI.setCallStatus(State.callActive, null);
                UI.populateAgents(State.availableAgents, State.activeAgent);
                UI.setModelBadge(State.currentModel);

                fetchAgentsInfo();
                fetchTasks();
                fetchIdeas();
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
                State.callCost = 0;
                State.currentModel = 'mini';
                UI.setCallActive(State.callerId);
                UI.setCallCost(0);
                UI.setModelBadge('mini');
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

            ai_state: function (data) {
                State.aiState = data.state || 'idle';
                UI.setAIState(State.aiState);
                addDebug('[AI] ' + State.aiState);
            },

            call_cost: function (data) {
                State.callCost = data.cost_cents || 0;
                UI.setCallCost(State.callCost);
            },

            model_changed: function (data) {
                State.currentModel = data.model || 'mini';
                UI.setModelBadge(State.currentModel);
                addDebug('[MODEL] ' + State.currentModel);
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

            idea_update: function (data) {
                var action = data.action;
                var idea = data.idea;

                if (action === 'created') {
                    State.ideas.unshift(idea);
                    addDebug('[IDEE] Neu: ' + idea.title);
                } else if (action === 'updated' || action === 'archived') {
                    for (var i = 0; i < State.ideas.length; i++) {
                        if (State.ideas[i].id === idea.id) {
                            State.ideas[i] = idea;
                            break;
                        }
                    }
                    addDebug('[IDEE] ' + action + ': ' + idea.title);
                }

                UI.updateIdeasPanel(State.ideas, State.projects);
            },

            project_update: function (data) {
                var action = data.action;
                var project = data.project;

                if (action === 'created') {
                    State.projects.unshift(project);
                    addDebug('[PROJEKT] Neu: ' + project.title);
                } else {
                    for (var i = 0; i < State.projects.length; i++) {
                        if (State.projects[i].id === project.id) {
                            State.projects[i] = project;
                            break;
                        }
                    }
                }

                UI.updateIdeasPanel(State.ideas, State.projects);
            },

            blacklist_updated: function () {
                fetchBlacklist();
                addDebug('[BLACKLIST] Aktualisiert');
            },

            whitelist_updated: function () {
                fetchWhitelist();
                addDebug('[WHITELIST] Aktualisiert');
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
            // Caller-Actions anzeigen
            if (DOM.callerActions && callerId) {
                DOM.callerActionsNumber.textContent = callerId;
                DOM.callerActions.style.display = '';
            }
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
            // Caller-Actions ausblenden
            if (DOM.callerActions) {
                DOM.callerActions.style.display = 'none';
            }
        },

        setAIState: function (state) {
            var labels = {
                idle: 'AI: Idle',
                listening: 'AI: Hoert zu',
                user_speaking: 'Anrufer spricht',
                thinking: 'AI: Denkt...',
                speaking: 'AI: Spricht',
            };
            var dotClasses = {
                idle: 'status-badge__dot--offline',
                listening: 'status-badge__dot--online',
                user_speaking: 'status-badge__dot--active',
                thinking: 'status-badge__dot--thinking',
                speaking: 'status-badge__dot--speaking',
            };
            DOM.aiLabel.textContent = labels[state] || 'AI: ' + state;
            DOM.aiDot.className = 'status-badge__dot ' + (dotClasses[state] || '');
        },

        setCallCost: function (cents) {
            if (cents >= 100) {
                DOM.costLabel.textContent = (cents / 100).toFixed(2) + ' EUR';
            } else {
                DOM.costLabel.textContent = cents.toFixed(2) + ' ct';
            }
        },

        setModelBadge: function (model) {
            var labels = { mini: 'Mini', premium: 'Premium' };
            DOM.modelLabel.textContent = labels[model] || model;
            DOM.modelBadge.className = 'status-badge model-badge model-badge--' + model;
        },

        setStatusBar: function (text) {
            if (DOM.statusbarText) {
                DOM.statusbarText.textContent = text;
            }
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

        updateIdeasPanel: function (ideas, projects) {
            DOM.ideasList.innerHTML = '';

            if ((!ideas || ideas.length === 0) && (!projects || projects.length === 0)) {
                DOM.ideasList.innerHTML = '<div class="empty-state">Keine Ideen</div>';
                return;
            }

            // --- Projects Section ---
            if (projects && projects.length > 0) {
                var projHeader = document.createElement('h3');
                projHeader.className = 'section-title';
                projHeader.textContent = 'Projekte (' + projects.length + ')';
                DOM.ideasList.appendChild(projHeader);

                projects.forEach(function (project) {
                    var div = document.createElement('div');
                    div.className = 'project-card';
                    var linkedCount = (project.ideas || []).length;
                    div.innerHTML =
                        '<div class="project-card__header">' +
                            '<span class="project-card__title">' + esc(project.title) + '</span>' +
                            '<span class="project-card__status project-card__status--' + project.status + '">' + esc(project.status) + '</span>' +
                        '</div>' +
                        '<div class="project-card__desc">' + esc(project.description || '') + '</div>' +
                        '<div class="project-card__meta">' + linkedCount + ' verknuepfte Ideen</div>';
                    DOM.ideasList.appendChild(div);
                });
            }

            // --- Ideas grouped by category ---
            var active = [];
            var archived = [];
            (ideas || []).forEach(function (idea) {
                if (idea.status === 'archived') {
                    archived.push(idea);
                } else {
                    active.push(idea);
                }
            });

            var categories = {};
            active.forEach(function (idea) {
                var cat = idea.category || 'sonstiges';
                if (!categories[cat]) categories[cat] = [];
                categories[cat].push(idea);
            });

            var catLabels = {
                software: 'Software',
                business: 'Business',
                automation: 'Automation',
                kreativ: 'Kreativ',
                sonstiges: 'Sonstiges'
            };
            var catOrder = ['software', 'business', 'automation', 'kreativ', 'sonstiges'];

            if (active.length > 0) {
                var ideasHeader = document.createElement('h3');
                ideasHeader.className = 'section-title';
                ideasHeader.textContent = 'Ideen (' + active.length + ')';
                DOM.ideasList.appendChild(ideasHeader);
            }

            catOrder.forEach(function (cat) {
                if (!categories[cat]) return;

                var catDiv = document.createElement('div');
                catDiv.className = 'idea-category';

                var catHeader = document.createElement('div');
                catHeader.className = 'idea-category__header';
                catHeader.innerHTML =
                    '<span class="idea-category__label idea-category__label--' + cat + '">' +
                    esc(catLabels[cat] || cat) + '</span>' +
                    '<span class="idea-category__count">' + categories[cat].length + '</span>';
                catDiv.appendChild(catHeader);

                categories[cat].forEach(function (idea) {
                    var card = document.createElement('div');
                    card.className = 'idea-card';

                    var notesCount = (idea.notes || []).length;
                    var dateStr = idea.created_at ? new Date(idea.created_at).toLocaleDateString('de-DE') : '';

                    var notesHtml = '';
                    if (notesCount > 0) {
                        var notesListHtml = '';
                        (idea.notes || []).forEach(function (note) {
                            var noteDate = note.timestamp ? new Date(note.timestamp).toLocaleString('de-DE') : '';
                            notesListHtml +=
                                '<div class="idea-card__note-item">' +
                                    '<span class="idea-card__note-date">' + esc(noteDate) + '</span>' +
                                    '<span class="idea-card__note-text">' + esc(note.text || '') + '</span>' +
                                '</div>';
                        });
                        notesHtml =
                            '<div class="idea-card__notes-toggle">' + notesCount + ' Notizen &#9660;</div>' +
                            '<div class="idea-card__notes-list" style="display:none;">' + notesListHtml + '</div>';
                    }

                    card.innerHTML =
                        '<div class="idea-card__header">' +
                            '<span class="idea-card__title">' + esc(idea.title) + '</span>' +
                            '<span class="idea-card__status idea-card__status--' + idea.status + '">' + esc(idea.status) + '</span>' +
                        '</div>' +
                        '<div class="idea-card__desc">' + esc(idea.description || '') + '</div>' +
                        notesHtml +
                        '<div class="idea-card__footer">' +
                            '<span class="idea-card__date">' + dateStr + '</span>' +
                            '<button class="btn btn--small btn--ghost idea-card__archive" data-idea-id="' + idea.id + '">Archivieren</button>' +
                        '</div>';

                    catDiv.appendChild(card);
                });

                DOM.ideasList.appendChild(catDiv);
            });

            // --- Archived section (collapsed) ---
            if (archived.length > 0) {
                var archiveSection = document.createElement('div');
                archiveSection.className = 'idea-archive-section';
                archiveSection.innerHTML =
                    '<button class="idea-archive-toggle btn btn--small btn--ghost">' +
                    'Archiviert (' + archived.length + ')</button>' +
                    '<div class="idea-archive-list" style="display:none;"></div>';

                var toggleBtn = archiveSection.querySelector('.idea-archive-toggle');
                var archiveList = archiveSection.querySelector('.idea-archive-list');

                toggleBtn.addEventListener('click', function () {
                    archiveList.style.display = archiveList.style.display === 'none' ? 'block' : 'none';
                });

                archived.forEach(function (idea) {
                    var card = document.createElement('div');
                    card.className = 'idea-card idea-card--archived';
                    var dateStr = idea.created_at ? new Date(idea.created_at).toLocaleDateString('de-DE') : '';
                    card.innerHTML =
                        '<div class="idea-card__header">' +
                            '<span class="idea-card__title">' + esc(idea.title) + '</span>' +
                            '<span class="idea-card__category">' + esc(catLabels[idea.category] || idea.category || '') + '</span>' +
                        '</div>' +
                        '<div class="idea-card__desc">' + esc(idea.description || '') + '</div>' +
                        '<div class="idea-card__date">' + dateStr + '</div>';
                    archiveList.appendChild(card);
                });

                DOM.ideasList.appendChild(archiveSection);
            }

            // Bind archive buttons
            DOM.ideasList.querySelectorAll('[data-idea-id]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    archiveIdea(this.getAttribute('data-idea-id'));
                });
            });

            // Bind notes toggle
            DOM.ideasList.querySelectorAll('.idea-card__notes-toggle').forEach(function (toggle) {
                toggle.addEventListener('click', function () {
                    var list = this.nextElementSibling;
                    if (list) {
                        var open = list.style.display !== 'none';
                        list.style.display = open ? 'none' : 'block';
                        this.innerHTML = (this.textContent.match(/\d+/)[0]) + ' Notizen ' + (open ? '&#9660;' : '&#9650;');
                    }
                });
            });

            // Update compact live-feed ideas section
            updateLiveIdeas(ideas);
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
                    '</div>';

                var btn = document.createElement('button');
                btn.className = 'btn btn--small btn--danger blacklist-item__remove';
                btn.setAttribute('data-caller-id', entry.caller_id || '');
                btn.innerHTML = '&#10005;';
                div.appendChild(btn);

                DOM.blacklistList.appendChild(div);
            });
        },

        updateWhitelist: function (entries) {
            DOM.whitelistList.innerHTML = '';
            if (!entries || entries.length === 0) {
                DOM.whitelistList.innerHTML = '<div class="empty-state">Keine freigeschalteten Nummern</div>';
                return;
            }

            entries.forEach(function (entry) {
                var div = document.createElement('div');
                div.className = 'whitelist-item';

                var date = entry.added_at ? new Date(entry.added_at).toLocaleString('de-DE') : '';

                div.innerHTML =
                    '<div class="whitelist-item__info">' +
                        '<span class="whitelist-item__number">' + esc(entry.caller_id || '') + '</span>' +
                        '<span class="whitelist-item__meta">' + esc(date) +
                        (entry.note ? ' — ' + esc(entry.note) : '') + '</span>' +
                    '</div>';

                var btn = document.createElement('button');
                btn.className = 'btn btn--small btn--danger whitelist-item__remove';
                btn.setAttribute('data-whitelist-id', entry.caller_id || '');
                btn.innerHTML = '&#10005;';
                div.appendChild(btn);

                DOM.whitelistList.appendChild(div);
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

    function fetchIdeas() {
        fetch('/ideas')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                State.ideas = data.ideas || [];
                fetchProjects();
            })
            .catch(function (e) { addDebug('[API] Ideas: ' + e.message); });
    }

    function fetchProjects() {
        fetch('/projects')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                State.projects = data.projects || [];
                UI.updateIdeasPanel(State.ideas, State.projects);
            })
            .catch(function (e) { addDebug('[API] Projects: ' + e.message); });
    }

    function archiveIdea(ideaId) {
        fetch('/ideas/' + ideaId + '/archive', { method: 'PUT' })
            .then(function (r) { return r.json(); })
            .then(function () { fetchIdeas(); })
            .catch(function (e) { addDebug('[API] Archive: ' + e.message); });
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

    function addCurrentCallerToBlacklist() {
        if (!State.callActive || !State.callerId) return;
        fetch('/blacklist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caller_id: State.callerId, reason: 'Manuell via Dashboard' }),
        })
            .then(function () { fetchBlacklist(); })
            .catch(function (e) { addDebug('[API] Blacklist Add: ' + e.message); });
    }

    function fetchWhitelist() {
        fetch('/whitelist')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                UI.updateWhitelist(data.entries || []);
            })
            .catch(function (e) { addDebug('[API] Whitelist: ' + e.message); });
    }

    function addCurrentCallerToWhitelist() {
        if (!State.callActive || !State.callerId) return;
        fetch('/whitelist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caller_id: State.callerId }),
        })
            .then(function () { fetchWhitelist(); })
            .catch(function (e) { addDebug('[API] Whitelist Add: ' + e.message); });
    }

    function removeFromWhitelist(callerId) {
        fetch('/whitelist/' + encodeURIComponent(callerId), { method: 'DELETE' })
            .then(function () { fetchWhitelist(); })
            .catch(function (e) { addDebug('[API] Whitelist Remove: ' + e.message); });
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
    // TABS (shared between desktop top-tabs and mobile bottom-nav)
    // ============================================
    function switchTab(target) {
        // Deactivate all top tab buttons
        DOM.tabButtons.forEach(function (b) {
            b.classList.remove('tabs__tab--active');
            b.setAttribute('aria-selected', 'false');
        });
        // Deactivate all tab panels
        DOM.tabPanels.forEach(function (p) {
            p.classList.remove('tabs__content--active');
        });

        // Activate matching top tab button
        DOM.tabButtons.forEach(function (b) {
            if (b.getAttribute('data-tab') === target) {
                b.classList.add('tabs__tab--active');
                b.setAttribute('aria-selected', 'true');
            }
        });

        // Activate matching tab panel
        var panel = document.getElementById('tab-' + target);
        if (panel) {
            panel.classList.add('tabs__content--active');
        }

        // Update bottom nav active state
        if (DOM.bottomNavItems) {
            DOM.bottomNavItems.forEach(function (b) {
                b.classList.remove('bottom-nav__item--active');
                if (b.getAttribute('data-tab') === target) {
                    b.classList.add('bottom-nav__item--active');
                }
            });
        }
    }

    function initTabs() {
        DOM.tabButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                switchTab(this.getAttribute('data-tab'));
            });
        });
    }

    function initBottomNav() {
        if (!DOM.bottomNav) return;

        DOM.bottomNavItems.forEach(function (btn) {
            btn.addEventListener('click', function () {
                switchTab(this.getAttribute('data-tab'));
            });
        });
    }

    // ============================================
    // HAMBURGER MENU
    // ============================================
    function initHamburger() {
        if (!DOM.btnMenuToggle) return;

        DOM.btnMenuToggle.addEventListener('click', function () {
            Mobile.menuOpen = !Mobile.menuOpen;
            DOM.btnMenuToggle.classList.toggle('header__menu-toggle--open', Mobile.menuOpen);
            DOM.headerCollapsible.classList.toggle('header__collapsible--open', Mobile.menuOpen);
        });

        // Close menu when clicking outside
        document.addEventListener('click', function (e) {
            if (Mobile.menuOpen &&
                !DOM.headerCollapsible.contains(e.target) &&
                !DOM.btnMenuToggle.contains(e.target)) {
                Mobile.menuOpen = false;
                DOM.btnMenuToggle.classList.remove('header__menu-toggle--open');
                DOM.headerCollapsible.classList.remove('header__collapsible--open');
            }
        });
    }

    // ============================================
    // VIEWPORT RESIZE HANDLER
    // ============================================
    function handleResize() {
        var wasMobile = Mobile.isMobile;
        Mobile.check();

        if (Mobile.isMobile && !wasMobile) {
            // Switched to mobile: activate Live tab
            switchTab('transkript');
        } else if (!Mobile.isMobile && wasMobile) {
            // Switched to desktop: activate Tasks tab (default)
            switchTab('tasks');
            // Close hamburger if open
            Mobile.menuOpen = false;
            if (DOM.btnMenuToggle) {
                DOM.btnMenuToggle.classList.remove('header__menu-toggle--open');
            }
            if (DOM.headerCollapsible) {
                DOM.headerCollapsible.classList.remove('header__collapsible--open');
            }
        }
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
            if (DOM.mobileTranscript) {
                DOM.mobileTranscript.innerHTML = '';
            }
        });

        DOM.btnClearDebug.addEventListener('click', function () {
            DOM.debugLog.innerHTML = '';
        });

        DOM.btnFirewallToggle.addEventListener('click', toggleFirewall);

        // Blacklist: Event delegation (survives DOM re-renders from periodic refresh)
        DOM.blacklistList.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-caller-id]');
            if (btn) {
                removeFromBlacklist(btn.getAttribute('data-caller-id'));
            }
        });

        // Whitelist: Event delegation
        DOM.whitelistList.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-whitelist-id]');
            if (btn) {
                removeFromWhitelist(btn.getAttribute('data-whitelist-id'));
            }
        });

        // Caller-Actions: Aktuellen Anrufer zu Black/Whitelist hinzufuegen
        if (DOM.btnAddBlacklist) {
            DOM.btnAddBlacklist.addEventListener('click', addCurrentCallerToBlacklist);
        }
        if (DOM.btnAddWhitelist) {
            DOM.btnAddWhitelist.addEventListener('click', addCurrentCallerToWhitelist);
        }

        if (DOM.btnRefreshIdeas) {
            DOM.btnRefreshIdeas.addEventListener('click', fetchIdeas);
        }
    }

    // ============================================
    // INIT
    // ============================================
    function init() {
        cacheDOMReferences();
        Mobile.check();
        initTabs();
        initBottomNav();
        initHamburger();
        bindEvents();
        WS.connect();

        // Set initial tab based on viewport
        if (Mobile.isMobile) {
            switchTab('transkript');
        }

        window.addEventListener('resize', handleResize);

        // Periodic refresh
        setInterval(fetchTasks, 10000);
        setInterval(fetchBlacklist, 10000);
        setInterval(fetchWhitelist, 10000);
        fetchBlacklist();
        fetchWhitelist();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
