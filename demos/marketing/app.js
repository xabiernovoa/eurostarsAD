(function () {
    "use strict";

    var refs = {
        navItems: document.querySelectorAll(".nav-item[data-section]"),
        sectionViews: document.querySelectorAll(".section-view"),
        sidebarUpdated: document.getElementById("sidebarUpdated"),
        overviewWindow: document.getElementById("overviewWindow"),
        overviewStats: document.getElementById("overviewStats"),
        channelDistribution: document.getElementById("channelDistribution"),
        momentDistribution: document.getElementById("momentDistribution"),
        topHotels: document.getElementById("topHotels"),
        signalFacts: document.getElementById("signalFacts"),
        dataQuality: document.getElementById("dataQuality"),
        audienceAge: document.getElementById("audienceAge"),
        audienceValue: document.getElementById("audienceValue"),
        audienceAffinity: document.getElementById("audienceAffinity"),
        audienceCountry: document.getElementById("audienceCountry"),
        segmentsBySize: document.getElementById("segmentsBySize"),
        segmentsByAdr: document.getElementById("segmentsByAdr"),
        contextSaveBtn: document.getElementById("contextSaveBtn"),
        contextForm: document.getElementById("contextForm"),
        strategicPriority: document.getElementById("strategicPriority"),
        managerNotes: document.getElementById("managerNotes"),
        receptionNotes: document.getElementById("receptionNotes"),
        externalSignals: document.getElementById("externalSignals"),
        generateBtn: document.getElementById("generateBtn"),
        generatorMeta: document.getElementById("generatorMeta"),
        proposalGrid: document.getElementById("proposalGrid"),
        chatSuggestions: document.getElementById("chatSuggestions"),
        chatMessages: document.getElementById("chatMessages"),
        chatTyping: document.getElementById("chatTyping"),
        chatInput: document.getElementById("chatInput"),
        chatSendBtn: document.getElementById("chatSendBtn"),
        modifyOverlay: document.getElementById("modifyOverlay"),
        modifyCloseBtn: document.getElementById("modifyCloseBtn"),
        modifyCampaignName: document.getElementById("modifyCampaignName"),
        modifyCurrentSubject: document.getElementById("modifyCurrentSubject"),
        modifyCurrentPreview: document.getElementById("modifyCurrentPreview"),
        modifyInstructions: document.getElementById("modifyInstructions"),
        modifySuggestions: document.getElementById("modifySuggestions"),
        modifyApplyBtn: document.getElementById("modifyApplyBtn"),
        modifyResult: document.getElementById("modifyResult"),
    };

    var currentDashboard = null;
    var generatorLoaded = false;
    var currentProposals = [];
    var currentProposalSource = "heuristic";
    var selectedCampaignId = null;
    var chatHistory = [];

    function esc(value) {
        return String(value != null ? value : "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function fmtPct(value) {
        return Math.round((value || 0) * 100) + "%";
    }

    function fmtInt(value) {
        return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 }).format(value || 0);
    }

    function fmtNumber(value, decimals) {
        return new Intl.NumberFormat("es-ES", {
            minimumFractionDigits: decimals || 0,
            maximumFractionDigits: decimals || 0,
        }).format(value || 0);
    }

    function fmtDate(value) {
        if (!value) return "—";
        var date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return new Intl.DateTimeFormat("es-ES", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    function fmtDateShort(value) {
        if (!value) return "—";
        var date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return new Intl.DateTimeFormat("es-ES", {
            day: "2-digit",
            month: "short",
            year: "numeric",
        }).format(date);
    }

    function linesFromTextarea(textarea) {
        return textarea.value
            .split("\n")
            .map(function (line) { return line.trim(); })
            .filter(Boolean);
    }

    function sourceLabel(source) {
        return source === "gemini" ? "Gemini" : "Motor heurístico";
    }

    function renderEmpty(container, text) {
        container.innerHTML = '<div class="empty-state">' + esc(text) + "</div>";
    }

    function currentSection() {
        var active = document.querySelector(".nav-item.active");
        return active ? active.dataset.section : "overview";
    }

    function normalizeSection(sectionId) {
        var allowed = {
            overview: true,
            audience: true,
            context: true,
            generator: true,
        };
        return allowed[sectionId] ? sectionId : "overview";
    }

    async function fetchDashboard() {
        var response = await fetch("/api/dashboard");
        if (!response.ok) throw new Error("No se pudo cargar el dashboard");
        return response.json();
    }

    async function saveContext() {
        var payload = {
            strategic_priority: refs.strategicPriority.value.trim(),
            manager_notes: linesFromTextarea(refs.managerNotes),
            reception_notes: linesFromTextarea(refs.receptionNotes),
            external_signals: linesFromTextarea(refs.externalSignals),
        };
        var response = await fetch("/api/context", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error("No se pudo guardar el contexto");
        return response.json();
    }

    async function fetchProposals() {
        var response = await fetch("/api/campaigns");
        if (!response.ok) throw new Error("No se pudieron generar las propuestas");
        return response.json();
    }

    async function sendChatMessage(message, history) {
        var response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message, history: history || [] }),
        });
        if (!response.ok) throw new Error("No se pudo consultar al agente");
        return response.json();
    }

    async function modifyCampaign(campaignId, instructions, campaign) {
        var response = await fetch("/api/campaigns/modify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ campaign_id: campaignId, instructions: instructions, campaign: campaign || null }),
        });
        if (!response.ok) throw new Error("No se pudo refinar la propuesta");
        return response.json();
    }

    function renderStats(overview) {
        var cards = [
            {
                label: "Usuarios segmentados",
                value: fmtInt(overview.guest_count),
                note: "Base actual con segmento asignado",
            },
            {
                label: "Piezas registradas",
                value: fmtInt(overview.message_count),
                note: "Filas deduplicadas del log",
            },
            {
                label: "Países origen",
                value: fmtInt(overview.country_count),
                note: "País real del usuario segmentado",
            },
            {
                label: "Hoteles recomendados",
                value: fmtInt(overview.hotel_count),
                note: "Hoteles distintos presentes en el log",
            },
            {
                label: "Eventos e insights",
                value: fmtInt(overview.signal_count),
                note: "Contexto externo activo",
            },
        ];

        refs.overviewStats.innerHTML = cards.map(function (card) {
            return (
                '<article class="stat-card">' +
                '<div class="stat-label">' + esc(card.label) + "</div>" +
                '<div class="stat-value">' + esc(card.value) + "</div>" +
                '<div class="stat-note">' + esc(card.note) + "</div>" +
                "</article>"
            );
        }).join("");

        refs.overviewWindow.textContent =
            "Ventana del log: " +
            fmtDateShort(overview.first_activity_at) +
            " - " +
            fmtDateShort(overview.last_activity_at);
    }

    function renderBarList(container, items, options) {
        if (!items || !items.length) {
            renderEmpty(container, "Sin datos disponibles.");
            return;
        }

        options = options || {};
        container.innerHTML = '<div class="bar-list">' + items.map(function (item) {
            var detail = options.detail ? options.detail(item) : "";
            return (
                '<div class="bar-item">' +
                '<div class="bar-meta">' +
                '<div class="bar-label-group">' +
                '<span class="bar-label">' + esc(item.label) + "</span>" +
                (detail ? '<span class="bar-detail">' + esc(detail) + "</span>" : "") +
                "</div>" +
                '<div class="bar-value">' + esc(fmtInt(item.count)) + " · " + esc(fmtPct(item.share)) + "</div>" +
                "</div>" +
                '<div class="bar-track"><div class="bar-fill" style="width:' + Math.max(1, Math.round((item.share || 0) * 100)) + '%"></div></div>' +
                "</div>"
            );
        }).join("") + "</div>";
    }

    function renderMomentDistribution(items) {
        if (!items || !items.length) {
            renderEmpty(refs.momentDistribution, "Sin datos disponibles.");
            return;
        }

        refs.momentDistribution.innerHTML = '<div class="moment-list">' + items.map(function (item) {
            var channels = (item.channels || []).map(function (channel) {
                return '<span class="tag">' + esc(channel.label) + ": " + esc(fmtInt(channel.count)) + "</span>";
            }).join("");

            return (
                '<article class="moment-card">' +
                '<div class="moment-card-top">' +
                '<div>' +
                '<div class="moment-label">' + esc(item.label) + "</div>" +
                '<div class="moment-count">' + esc(fmtInt(item.count)) + " piezas</div>" +
                "</div>" +
                '<div class="moment-share">' + esc(fmtPct(item.share)) + "</div>" +
                "</div>" +
                '<div class="moment-detail">Hotel recomendado: ' +
                esc(fmtInt(item.with_hotel)) + " con dato · " +
                esc(fmtInt(item.without_hotel)) + " sin dato</div>" +
                '<div class="tag-row">' + channels + "</div>" +
                "</article>"
            );
        }).join("") + "</div>";
    }

    function renderTopHotels(items) {
        if (!items || !items.length) {
            renderEmpty(refs.topHotels, "No hay hoteles recomendados en el log.");
            return;
        }

        refs.topHotels.innerHTML = '<div class="list-stack">' + items.map(function (item) {
            return (
                '<div class="stack-row">' +
                '<div class="stack-main">' + esc(item.hotel) + "</div>" +
                '<div class="stack-side">' + esc(fmtInt(item.count)) + " · " + esc(fmtPct(item.share)) + "</div>" +
                "</div>"
            );
        }).join("") + "</div>";
    }

    function renderSignals(signalFacts) {
        var signals = signalFacts && signalFacts.signals ? signalFacts.signals : [];
        if (!signals.length) {
            renderEmpty(refs.signalFacts, "No hay eventos o insights guardados.");
            return;
        }

        refs.signalFacts.innerHTML = '<div class="signal-list">' + signals.map(function (signal) {
            return (
                '<div class="signal-item">' +
                (signal.city ? '<div class="signal-city">' + esc(signal.city) + "</div>" : "") +
                '<div class="signal-text">' + esc(signal.text) + "</div>" +
                "</div>"
            );
        }).join("") + "</div>";
    }

    function renderDataQuality(overview) {
        var rowsWithHotelShare = overview.message_count ? overview.rows_with_hotel / overview.message_count : 0;
        var rowsWithSubjectShare = overview.message_count ? overview.rows_with_subject / overview.message_count : 0;
        var items = [
            {
                label: "Cobertura hotel recomendado",
                value: fmtPct(rowsWithHotelShare),
                note: fmtInt(overview.rows_with_hotel) + " de " + fmtInt(overview.message_count) + " piezas",
            },
            {
                label: "Cobertura asunto",
                value: fmtPct(rowsWithSubjectShare),
                note: fmtInt(overview.rows_with_subject) + " de " + fmtInt(overview.message_count) + " piezas",
            },
            {
                label: "Filas sin hotel",
                value: fmtInt(overview.rows_without_hotel),
                note: "Se concentran en check-in y postestancia",
            },
            {
                label: "Ultima actividad",
                value: fmtDateShort(overview.last_activity_at),
                note: "Fecha más reciente presente en el log",
            },
        ];

        refs.dataQuality.innerHTML = items.map(function (item) {
            return (
                '<div class="quality-card">' +
                '<div class="quality-label">' + esc(item.label) + "</div>" +
                '<div class="quality-value">' + esc(item.value) + "</div>" +
                '<div class="quality-note">' + esc(item.note) + "</div>" +
                "</div>"
            );
        }).join("");
    }

    function renderSegmentTable(container, items, mode) {
        if (!items || !items.length) {
            container.innerHTML = '<tr><td colspan="4" class="table-empty">Sin datos.</td></tr>';
            return;
        }

        container.innerHTML = items.map(function (item) {
            if (mode === "size") {
                return (
                    "<tr>" +
                    '<td><div class="table-primary">' + esc(item.segment_label) + "</div><div class=\"table-secondary\">" + esc(fmtPct(item.share)) + " de la base</div></td>" +
                    "<td>" + esc(fmtInt(item.users)) + "</td>" +
                    "<td>" + esc(fmtNumber(item.avg_adr, 2)) + " €</td>" +
                    "<td>" + esc(fmtNumber(item.avg_leadtime, 1)) + " días</td>" +
                    "</tr>"
                );
            }
            return (
                "<tr>" +
                '<td><div class="table-primary">' + esc(item.segment_label) + "</div><div class=\"table-secondary\">Canal dominante: " + esc(item.top_channel || "—") + "</div></td>" +
                "<td>" + esc(fmtInt(item.users)) + "</td>" +
                "<td>" + esc(fmtNumber(item.avg_adr, 2)) + " €</td>" +
                "<td>" + esc(item.top_country || "—") + "</td>" +
                "</tr>"
            );
        }).join("");
    }

    function fillContextForm(context) {
        refs.strategicPriority.value = context.strategic_priority || "";
        refs.managerNotes.value = (context.manager_notes || []).join("\n");
        refs.receptionNotes.value = (context.reception_notes || []).join("\n");
        refs.externalSignals.value = (context.external_signals || []).join("\n");
    }

    function renderGeneratorPlaceholder() {
        renderEmpty(refs.proposalGrid, "Pulsa “Generar propuestas” para crear ideas de campaña a partir del panel actual.");
        refs.generatorMeta.textContent = "Las propuestas se generan a demanda y se muestran separadas de la analítica factual.";
    }

    function renderProposals(data) {
        currentProposals = data.proposals || [];
        currentProposalSource = data.source || currentProposalSource;
        refs.generatorMeta.textContent =
            "Fuente actual: " + sourceLabel(currentProposalSource) + ". Las propuestas son sugerencias asistidas, no métricas observadas.";

        if (!currentProposals.length) {
            renderEmpty(refs.proposalGrid, "No se pudieron generar propuestas con el contexto actual.");
            return;
        }

        refs.proposalGrid.innerHTML = '<div class="proposal-grid">' + currentProposals.map(function (proposal) {
            return (
                '<article class="proposal-card">' +
                '<div class="proposal-top">' +
                '<div class="proposal-category">' + esc(proposal.category_label || "Propuesta") + "</div>" +
                '<div class="proposal-priority">' + esc((proposal.priority || "media").toUpperCase()) + "</div>" +
                "</div>" +
                '<h3 class="proposal-title">' + esc(proposal.name || "Campaña") + "</h3>" +
                '<p class="proposal-objective">' + esc(proposal.objective || "") + "</p>" +
                '<div class="tag-row">' +
                (proposal.channel ? '<span class="tag">' + esc(proposal.channel) + "</span>" : "") +
                (proposal.segment ? '<span class="tag">' + esc(proposal.segment) + "</span>" : "") +
                (proposal.timing ? '<span class="tag">' + esc(proposal.timing) + "</span>" : "") +
                "</div>" +
                (proposal.subject_line ? '<div class="proposal-subject">' + esc(proposal.subject_line) + "</div>" : "") +
                (proposal.preview_text ? '<div class="proposal-preview">' + esc(proposal.preview_text) + "</div>" : "") +
                (proposal.body_summary ? '<div class="proposal-body">' + esc(proposal.body_summary) + "</div>" : "") +
                (proposal.rationale ? '<div class="proposal-rationale">' + esc(proposal.rationale) + "</div>" : "") +
                '<div class="proposal-actions">' +
                '<button class="filter-chip refine-btn" data-id="' + esc(proposal.id) + '">Refinar copy</button>' +
                "</div>" +
                "</article>"
            );
        }).join("") + "</div>";
    }

    function ensureChatContainerReady() {
        var empty = refs.chatMessages.querySelector(".chat-empty");
        if (empty) empty.remove();
    }

    function addChatMessage(role, text, source) {
        ensureChatContainerReady();
        var message = document.createElement("div");
        message.className = "chat-message " + role;
        message.innerHTML =
            '<div class="chat-bubble">' + esc(text).replace(/\n/g, "<br>") + "</div>" +
            (role === "assistant" && source
                ? '<div class="chat-source">' + esc(sourceLabel(source)) + "</div>"
                : "");
        refs.chatMessages.insertBefore(message, refs.chatTyping);
        refs.chatMessages.scrollTop = refs.chatMessages.scrollHeight;
    }

    async function handleChatSend(prefill) {
        var message = (prefill != null ? prefill : refs.chatInput.value).trim();
        if (!message) return;

        refs.chatInput.value = "";
        addChatMessage("user", message);
        chatHistory.push({ role: "user", content: message });
        refs.chatTyping.classList.add("visible");
        refs.chatSendBtn.disabled = true;

        try {
            var result = await sendChatMessage(message, chatHistory);
            refs.chatTyping.classList.remove("visible");
            addChatMessage("assistant", result.reply, result.source);
            chatHistory.push({ role: "assistant", content: result.reply });
        } catch (error) {
            refs.chatTyping.classList.remove("visible");
            addChatMessage("assistant", error.message, "heuristic");
            chatHistory.push({ role: "assistant", content: error.message });
        }

        refs.chatSendBtn.disabled = false;
    }

    function closeModifyModal() {
        refs.modifyOverlay.classList.remove("open");
        selectedCampaignId = null;
        refs.modifyInstructions.value = "";
        refs.modifyResult.innerHTML = "";
    }

    function openModifyModal(proposal) {
        selectedCampaignId = proposal.id;
        refs.modifyCampaignName.textContent = proposal.name || "—";
        refs.modifyCurrentSubject.textContent = proposal.subject_line || "—";
        refs.modifyCurrentPreview.textContent = proposal.preview_text || "—";
        refs.modifyInstructions.value = "";
        refs.modifyResult.innerHTML = "";
        refs.modifyOverlay.classList.add("open");
    }

    async function loadProposals() {
        refs.generateBtn.disabled = true;
        refs.generateBtn.textContent = "Generando…";
        refs.generatorMeta.textContent = "Generando propuestas asistidas a partir del panel actual…";
        renderEmpty(refs.proposalGrid, "Generando propuestas…");

        try {
            var data = await fetchProposals();
            renderProposals(data);
            generatorLoaded = true;
        } catch (error) {
            renderEmpty(refs.proposalGrid, error.message);
            refs.generatorMeta.textContent = "No se pudieron generar propuestas en esta lectura.";
        }

        refs.generateBtn.disabled = false;
        refs.generateBtn.textContent = "Generar propuestas";
    }

    function renderDashboard(dashboard) {
        currentDashboard = dashboard;

        renderStats(dashboard.overview_facts || {});
        renderBarList(refs.channelDistribution, dashboard.channel_distribution || []);
        renderMomentDistribution(dashboard.moment_distribution || []);
        renderTopHotels(dashboard.top_hotels || []);
        renderSignals(dashboard.signal_facts || {});
        renderDataQuality(dashboard.overview_facts || {});

        renderBarList(refs.audienceAge, (dashboard.audience_facts || {}).by_age || [], {
            detail: function (item) { return "ADR medio " + fmtNumber(item.avg_adr, 2) + " €"; },
        });
        renderBarList(refs.audienceValue, (dashboard.audience_facts || {}).by_value || [], {
            detail: function (item) { return "Stay medio " + fmtNumber(item.avg_stay, 1) + " días"; },
        });
        renderBarList(refs.audienceAffinity, (dashboard.audience_facts || {}).by_affinity || [], {
            detail: function (item) { return "Lead time " + fmtNumber(item.avg_leadtime, 1) + " días"; },
        });
        renderBarList(refs.audienceCountry, (dashboard.audience_facts || {}).by_country || [], {
            detail: function (item) { return "ADR medio " + fmtNumber(item.avg_adr, 2) + " €"; },
        });

        renderSegmentTable(refs.segmentsBySize, (dashboard.segment_rankings || {}).by_size || [], "size");
        renderSegmentTable(refs.segmentsByAdr, (dashboard.segment_rankings || {}).by_adr || [], "adr");

        fillContextForm(dashboard.context || {});
        refs.sidebarUpdated.textContent = fmtDate(dashboard.generated_at);
    }

    function switchSection(sectionId, syncHash) {
        sectionId = normalizeSection(sectionId);
        refs.navItems.forEach(function (item) {
            item.classList.toggle("active", item.dataset.section === sectionId);
        });
        refs.sectionViews.forEach(function (view) {
            var expectedId = "view" + sectionId.charAt(0).toUpperCase() + sectionId.slice(1);
            view.classList.toggle("active", view.id === expectedId);
        });
        if (sectionId === "generator" && !generatorLoaded) {
            loadProposals();
        }
        if (syncHash !== false && window.location.hash !== "#" + sectionId) {
            window.location.hash = sectionId;
        }
    }

    refs.navItems.forEach(function (item) {
        item.addEventListener("click", function () {
            switchSection(item.dataset.section);
        });
    });

    window.addEventListener("hashchange", function () {
        switchSection(window.location.hash.replace(/^#/, ""), false);
    });

    refs.generateBtn.addEventListener("click", loadProposals);

    refs.chatSendBtn.addEventListener("click", function () {
        handleChatSend();
    });

    refs.chatInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleChatSend();
        }
    });

    refs.chatSuggestions.addEventListener("click", function (event) {
        var button = event.target.closest(".filter-chip");
        if (!button) return;
        handleChatSend(button.dataset.msg || "");
    });

    refs.contextSaveBtn.addEventListener("click", function () {
        refs.contextForm.requestSubmit();
    });

    refs.contextForm.addEventListener("submit", async function (event) {
        event.preventDefault();
        refs.contextSaveBtn.disabled = true;
        refs.contextSaveBtn.textContent = "Guardando…";

        try {
            var response = await saveContext();
            renderDashboard(response.dashboard);
            generatorLoaded = false;
            renderGeneratorPlaceholder();
            if (currentSection() === "generator") {
                loadProposals();
            }
            switchSection("context");
        } catch (error) {
            window.alert(error.message);
        }

        refs.contextSaveBtn.disabled = false;
        refs.contextSaveBtn.textContent = "Guardar contexto";
    });

    refs.proposalGrid.addEventListener("click", function (event) {
        var button = event.target.closest(".refine-btn");
        if (!button) return;
        var proposal = currentProposals.find(function (item) { return item.id === button.dataset.id; });
        if (!proposal) return;
        openModifyModal(proposal);
    });

    refs.modifyCloseBtn.addEventListener("click", closeModifyModal);
    refs.modifyOverlay.addEventListener("click", function (event) {
        if (event.target === refs.modifyOverlay) closeModifyModal();
    });

    refs.modifySuggestions.addEventListener("click", function (event) {
        var button = event.target.closest(".filter-chip");
        if (!button) return;
        refs.modifyInstructions.value = button.dataset.instr || "";
    });

    refs.modifyApplyBtn.addEventListener("click", async function () {
        var instructions = refs.modifyInstructions.value.trim();
        if (!instructions || !selectedCampaignId) return;

        refs.modifyApplyBtn.disabled = true;
        refs.modifyApplyBtn.textContent = "Aplicando…";
        refs.modifyResult.innerHTML = "";

        try {
            var proposal = currentProposals.find(function (item) { return item.id === selectedCampaignId; }) || null;
            var result = await modifyCampaign(selectedCampaignId, instructions, proposal);
            var campaign = result.campaign || {};
            currentProposals = currentProposals.map(function (item) {
                return item.id === selectedCampaignId ? Object.assign({}, item, campaign) : item;
            });
            renderProposals({ proposals: currentProposals, source: currentProposalSource });
            refs.modifyResult.innerHTML =
                '<div class="modify-result-card">' +
                '<div class="proposal-category">Fuente: ' + esc(sourceLabel(result.source)) + "</div>" +
                '<div class="proposal-subject">' + esc(campaign.subject_line || "—") + "</div>" +
                '<div class="proposal-preview">' + esc(campaign.preview_text || "—") + "</div>" +
                '<div class="proposal-body">' + esc(campaign.body_summary || "—") + "</div>" +
                "</div>";
        } catch (error) {
            refs.modifyResult.innerHTML = '<div class="empty-state">' + esc(error.message) + "</div>";
        }

        refs.modifyApplyBtn.disabled = false;
        refs.modifyApplyBtn.textContent = "Aplicar";
    });

    renderGeneratorPlaceholder();

    switchSection(window.location.hash.replace(/^#/, "") || currentSection(), false);

    fetchDashboard()
        .then(renderDashboard)
        .catch(function (error) {
            refs.sidebarUpdated.textContent = "Error";
            refs.overviewStats.innerHTML = '<div class="empty-state">' + esc(error.message) + "</div>";
        });
})();
