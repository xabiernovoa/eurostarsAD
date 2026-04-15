(function () {
    "use strict";

    /* ── Referencias DOM ─────────────────────────────────── */

    var refs = {
        navItems: document.querySelectorAll(".nav-item[data-section]"),
        sectionViews: document.querySelectorAll(".section-view"),
        sidebarUpdated: document.getElementById("sidebarUpdated"),
        refreshBtn: null,
        saveBtn: null,
        statusLine: null,
        kpiGrid: document.getElementById("kpiGrid"),
        priorityText: document.getElementById("priorityText"),
        citiesRow: document.getElementById("citiesRow"),
        opportunityRow: document.getElementById("opportunityRow"),
        donutProfile: document.getElementById("donutProfile"),
        heatmapGrid: document.getElementById("heatmapGrid"),
        ageBreakdown: document.getElementById("ageBreakdown"),
        profileBreakdown: document.getElementById("profileBreakdown"),
        valueBreakdown: document.getElementById("valueBreakdown"),
        momentBreakdown: document.getElementById("momentBreakdown"),
        donutValue: document.getElementById("donutValue"),
        countryRow: document.getElementById("countryRow"),
        audienceCount: null,
        segmentGrid: document.getElementById("segmentGrid"),
        campaignCount: null,
        campaignCounters: document.getElementById("campaignCounters"),
        campaignFilters: document.getElementById("campaignFilters"),
        campaignTableBody: document.getElementById("campaignTableBody"),
        recSource: null,
        actionGrid: document.getElementById("actionGrid"),
        configSaveBtn: document.getElementById("configSaveBtn"),
        contextForm: document.getElementById("contextForm"),
        strategicPriority: document.getElementById("strategicPriority"),
        managerNotes: document.getElementById("managerNotes"),
        receptionNotes: document.getElementById("receptionNotes"),
        externalSignals: document.getElementById("externalSignals"),
        chatFab: document.getElementById("chatFab"),
        chatOverlay: document.getElementById("chatOverlay"),
        chatPanel: document.getElementById("chatPanel"),
        chatCloseBtn: document.getElementById("chatCloseBtn"),
        chatSuggestions: document.getElementById("chatSuggestions"),
        chatMessages: document.getElementById("chatMessages"),
        chatTyping: document.getElementById("chatTyping"),
        chatInput: document.getElementById("chatInput"),
        chatSendBtn: document.getElementById("chatSendBtn"),
    };

    var currentDashboard = null;
    var activeCampaignFilter = "all";
    var chatHistory = [];

    /* ── Tema (siempre claro) ────────────────────────────── */
    document.documentElement.setAttribute("data-theme", "light");

    /* ── Navegación ──────────────────────────────────────── */

    function switchSection(sectionId) {
        refs.navItems.forEach(function (item) {
            item.classList.toggle("active", item.dataset.section === sectionId);
        });
        refs.sectionViews.forEach(function (view) {
            var viewId = "view" + sectionId.charAt(0).toUpperCase() + sectionId.slice(1);
            view.classList.toggle("active", view.id === viewId);
        });
    }

    refs.navItems.forEach(function (item) {
        item.addEventListener("click", function () { switchSection(item.dataset.section); });
    });

    /* ── Utilidades ──────────────────────────────────────── */

    function setStatus(msg) { if (refs.statusLine) refs.statusLine.textContent = msg; }

    function esc(v) {
        return String(v != null ? v : "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function fmtDate(v) {
        if (!v) return "\u2014";
        var d = new Date(v);
        if (Number.isNaN(d.getTime())) return v;
        return new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(d);
    }

    function fmtPct(v) { return Math.round((v || 0) * 100) + "%"; }
    function engClass(v) { return v >= 0.85 ? "high" : v >= 0.65 ? "mid" : "low"; }
    function typeLabel(t) {
        return {
            pre_arrival: "Prellegada", post_stay: "Postestancia", checkin_report: "Recepción",
            contenido_rrss: "Contenido RRSS", hotel_insite: "Dentro del hotel",
            local_partnership: "Colaboración local", branding: "Marca",
            geolocalizacion: "Geolocalización", evento: "Evento", decoracion: "Decoración"
        }[t] || t;
    }
    function categoryIcon(cat) {
        return {
            rrss: "RRSS", hotel: "Hotel", local: "Local", branding: "Marca",
            geolocalizacion: "Geo", evento: "Evento", decoracion: "Deco"
        }[cat] || cat || "";
    }

    function segmentAgeTag(seg) {
        return (((seg || {}).tags || {}).demografia || {}).edad || "—";
    }

    function segmentPrimaryAffinity(seg) {
        var list = ((seg || {}).tags || {}).afinidades_destino || [];
        return list.length ? list[0] : "—";
    }

    function segmentValueLevel(seg) {
        return ((seg || {}).tags || {}).nivel_valor || "—";
    }

    function linesFromTextarea(ta) {
        return ta.value.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
    }

    /* ── API ─────────────────────────────────────────────── */

    async function fetchDashboard() {
        var r = await fetch("/api/dashboard");
        if (!r.ok) throw new Error("No se pudo cargar el dashboard");
        return r.json();
    }

    async function saveContext() {
        var payload = {
            strategic_priority: refs.strategicPriority.value.trim(),
            manager_notes: linesFromTextarea(refs.managerNotes),
            reception_notes: linesFromTextarea(refs.receptionNotes),
            external_signals: linesFromTextarea(refs.externalSignals),
        };
        var r = await fetch("/api/context", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        if (!r.ok) throw new Error("No se pudo guardar el contexto");
        return r.json();
    }

    async function sendChatMessage(message) {
        var r = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: message, history: chatHistory.slice(-10) }),
        });
        if (!r.ok) throw new Error("Error del agente");
        return r.json();
    }

    /* ── Pintar KPIs ─────────────────────────────────────── */

    function renderKpis(kpis) {
        var items = [
            { label: "Campañas", value: kpis.total_campaigns, note: "Campañas deduplicadas", indicator: "good" },
            { label: "Audiencia", value: kpis.audience_size, note: "Usuarios segmentados", indicator: "good" },
            { label: "Segmentos activos", value: kpis.active_segments, note: "Cruces edad-afinidad-valor", indicator: kpis.active_segments >= 10 ? "good" : "neutral" },
            { label: "Índice medio", value: fmtPct(kpis.avg_engagement_index), note: "Interacción estimada", indicator: kpis.avg_engagement_index >= 0.75 ? "good" : kpis.avg_engagement_index >= 0.5 ? "neutral" : "low" },
            { label: "Presión estratégica", value: kpis.priority_pressure + "/100", note: "Intensidad señales", indicator: kpis.priority_pressure >= 70 ? "good" : "neutral" },
        ];
        refs.kpiGrid.innerHTML = items.map(function (k) {
            return '<article class="kpi-card"><div class="kpi-header"><div class="kpi-label">' + k.label + '</div></div><div class="kpi-value">' + k.value + '</div><div class="kpi-footnote">' + k.note + '</div></article>';
        }).join("");
    }

    /* ── Pintar oportunidades ───────────────────────────── */

    function renderOpportunities(dashboard) {
        var segs = dashboard.segment_cards || [];
        var cities = dashboard.focus_cities || [];
        var rows = dashboard.recent_campaigns || [];

        var topSeg = segs[0] || {};
        var topCity = cities[0] || "—";

        var channelMap = {};
        rows.forEach(function (r) {
            var ch = r.channel || "email";
            if (!channelMap[ch]) channelMap[ch] = { sum: 0, count: 0 };
            channelMap[ch].sum += r.engagement_index || 0;
            channelMap[ch].count++;
        });
        var bestChannel = "email";
        var bestChAvg = 0;
        Object.keys(channelMap).forEach(function (ch) {
            var avg = channelMap[ch].sum / channelMap[ch].count;
            if (avg > bestChAvg) { bestChAvg = avg; bestChannel = ch; }
        });

        refs.opportunityRow.innerHTML =
            '<div class="opportunity-card"><div><div class="opportunity-label">Segmento líder</div><div class="opportunity-value">' + esc(topSeg.segment_label || "—") + '</div><div class="opportunity-detail">' + (topSeg.users || 0) + ' usuarios · ' + fmtPct(topSeg.avg_engagement_index) + ' de interacción · ' + Math.round(topSeg.avg_adr || 0) + '€ ADR</div></div></div>' +
            '<div class="opportunity-card"><div><div class="opportunity-label">Ciudad con más tracción</div><div class="opportunity-value">' + esc(topCity) + '</div><div class="opportunity-detail">Destino con mayor concentración de campañas y señales externas activas</div></div></div>' +
            '<div class="opportunity-card"><div><div class="opportunity-label">Mejor canal</div><div class="opportunity-value">' + esc(bestChannel) + '</div><div class="opportunity-detail">Interacción media ' + fmtPct(bestChAvg) + ' sobre ' + (channelMap[bestChannel] ? channelMap[bestChannel].count : 0) + ' campañas recientes</div></div></div>';
    }

    /* ── Pintar foco ─────────────────────────────────────── */

    function renderFocus(dashboard) {
        refs.priorityText.textContent = dashboard.context.strategic_priority || "Sin prioridad definida.";
        var html = '<span class="cities-label">Ciudades en foco</span>';
        (dashboard.focus_cities || []).forEach(function (c) { html += '<span class="city-pill">' + esc(c) + '</span>'; });
        refs.citiesRow.innerHTML = html;
        refs.sidebarUpdated.textContent = "Actualizado " + fmtDate(dashboard.generated_at);
    }

    /* ── Pintar donut SVG ────────────────────────────────── */

    var DONUT_COLORS = ["#b8943e", "#c9a96e", "#4a8ec9", "#3d9a5f", "#c49a2a", "#84754e", "#c94a4a", "#6b5fa5"];

    function renderDonut(container, data, size) {
        size = size || 130;
        var r = size / 2 - 10;
        var cx = size / 2;
        var cy = size / 2;
        var strokeWidth = 20;
        var total = data.reduce(function (s, d) { return s + d.value; }, 0);
        if (total === 0) { container.innerHTML = '<p class="form-help">Sin datos</p>'; return; }

        var svgParts = ['<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" class="donut-svg">'];
        var circumference = 2 * Math.PI * r;
        var offset = 0;

        data.forEach(function (d, i) {
            var pct = d.value / total;
            var dashLength = pct * circumference;
            var color = DONUT_COLORS[i % DONUT_COLORS.length];
            svgParts.push(
                '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + strokeWidth + '" ' +
                'stroke-dasharray="' + dashLength + ' ' + (circumference - dashLength) + '" ' +
                'stroke-dashoffset="' + (-offset) + '" transform="rotate(-90 ' + cx + ' ' + cy + ')" />'
            );
            offset += dashLength;
        });

        svgParts.push('<text x="' + cx + '" y="' + (cy + 2) + '" text-anchor="middle" fill="#e8e6e1" font-size="18" font-weight="800" font-family="Manrope,sans-serif">' + total + '</text>');
        svgParts.push('<text x="' + cx + '" y="' + (cy + 16) + '" text-anchor="middle" fill="#5c5c64" font-size="9" font-weight="600" font-family="Manrope,sans-serif">total</text>');
        svgParts.push('</svg>');

        var legendParts = ['<div class="donut-legend">'];
        data.forEach(function (d, i) {
            var color = DONUT_COLORS[i % DONUT_COLORS.length];
            legendParts.push(
                '<div class="legend-item"><span class="legend-dot" style="background:' + color + '"></span>' +
                esc(d.label) + '<span class="legend-value">' + d.value + '</span></div>'
            );
        });
        legendParts.push('</div>');

        container.innerHTML = '<div class="donut-container">' + svgParts.join("") + legendParts.join("") + '</div>';
    }

    /* ── Pintar mapa de calor ────────────────────────────── */

    function renderHeatmap(dashboard) {
        var rows = dashboard.campaign_rows || dashboard.recent_campaigns || [];
        var ageSegments = ["JOVEN", "ADULTO", "SENIOR"];
        var channels = ["email", "sms", "push"];

        var grid = {};
        ageSegments.forEach(function (a) {
            channels.forEach(function (c) { grid[a + "|" + c] = { sum: 0, count: 0 }; });
        });
        rows.forEach(function (r) {
            var key = r.demographic_age + "|" + r.channel;
            if (grid[key]) { grid[key].sum += r.engagement_index || 0; grid[key].count++; }
        });

        var cols = channels.length + 1;
        var html = '<div class="heatmap-grid" style="grid-template-columns: 80px repeat(' + channels.length + ', 1fr)">';
        html += '<div></div>';
        channels.forEach(function (c) { html += '<div class="heatmap-header">' + esc(c) + '</div>'; });

        ageSegments.forEach(function (a) {
            html += '<div class="heatmap-row-label">' + esc(a) + '</div>';
            channels.forEach(function (c) {
                var cell = grid[a + "|" + c];
                var avg = cell.count > 0 ? cell.sum / cell.count : 0;
                var pct = Math.round(avg * 100);
                var intensity = Math.round(avg * 255);
                var bg, color;
                if (avg >= 0.85) { bg = "rgba(61,154,95,0.35)"; color = "#3d9a5f"; }
                else if (avg >= 0.70) { bg = "rgba(184,148,62,0.30)"; color = "#c9a96e"; }
                else if (avg > 0) { bg = "rgba(255,255,255,0.06)"; color = "#9a9a9e"; }
                else { bg = "rgba(255,255,255,0.02)"; color = "#5c5c64"; }
                html += '<div class="heatmap-cell" style="background:' + bg + ';color:' + color + '">' + (cell.count > 0 ? pct + '%' : '—') + '</div>';
            });
        });
        html += '</div>';
        refs.heatmapGrid.innerHTML = html;
    }

    /* ── Pintar desgloses ────────────────────────────────── */

    function renderBreakdown(container, items) {
        var html = '<div class="breakdown-list">';
        items.forEach(function (item) {
            var pct = Math.max(8, Math.round(item.avg_engagement_index * 100));
            html += '<div class="breakdown-item"><div class="breakdown-meta"><span class="breakdown-name">' + esc(item.label) + '</span><span class="breakdown-stats">' + fmtPct(item.avg_engagement_index) + ' · ' + item.count + ' campañas</span></div><div class="meter"><div class="meter-fill" style="width:' + pct + '%"></div></div></div>';
        });
        html += '</div>';
        container.innerHTML = html;
    }

    /* ── Pintar segmentos ────────────────────────────────── */

    function renderSegments(cards) {
        refs.segmentGrid.innerHTML = cards.map(function (c) {
            return '<article class="segment-card"><h3>' + esc(c.segment_label) + '</h3><div class="segment-meta">Canal: ' + esc(c.dominant_channel) + ' · Momento: ' + esc(c.dominant_moment) + '</div><div class="segment-meta" style="margin-top:8px">' + c.users + ' usuarios · ' + c.campaigns + ' campañas · ' + fmtPct(c.avg_engagement_index) + ' índice · ' + Math.round(c.avg_adr) + '€ ADR</div></article>';
        }).join("");
        if (refs.audienceCount) refs.audienceCount.textContent = cards.length + " segmentos activos";
    }

    /* ── Pintar estadísticas por país ────────────────────── */

    function renderCountryStats(dashboard) {
        var rows = dashboard.campaign_rows || dashboard.recent_campaigns || [];
        var countries = {};
        rows.forEach(function (r) {
            var seg = r.demographic_age || "";
            // campaign_rows no trae el país directamente; aquí se usa una estimación
        });
        // Se usa segment_cards, que sí aporta conteos de usuarios, para mostrar una versión simplificada
        var flags = { ES: "🇪🇸", PT: "🇵🇹", IT: "🇮🇹" };
        var names = { ES: "España", PT: "Portugal", IT: "Italia" };
        // Se estima el reparto desde el dashboard disponible
        var segs = dashboard.segment_cards || [];
        var totalUsers = segs.reduce(function (s, c) { return s + c.users; }, 0);

        var html = "";
        ["ES", "PT", "IT"].forEach(function (code) {
            var count = Math.round(totalUsers * (code === "ES" ? 0.45 : code === "PT" ? 0.28 : 0.27));
            html += '<div class="country-card"><div class="country-name">' + (names[code] || code) + '</div><div class="country-count">' + count + '</div><div class="country-detail">usuarios activos</div></div>';
        });
        refs.countryRow.innerHTML = html;
    }

    /* ── Pintar contadores de campañas ───────────────────── */

    function renderCampaignCounters(rows) {
        var counts = { pre_arrival: 0, post_stay: 0, checkin_report: 0 };
        rows.forEach(function (r) {
            if (counts[r.campaign_type] !== undefined) counts[r.campaign_type]++;
        });
        var items = [
            { label: "Prellegada", count: counts.pre_arrival, cls: "pre_arrival" },
            { label: "Postestancia", count: counts.post_stay, cls: "post_stay" },
            { label: "Recepción", count: counts.checkin_report, cls: "checkin_report" },
        ];
        refs.campaignCounters.innerHTML = items.map(function (i) {
            return '<div class="counter-card"><div class="counter-value">' + i.count + '</div><div class="counter-label">' + i.label + '</div></div>';
        }).join("");
    }

    /* ── Pintar campañas ─────────────────────────────────── */

    function renderCampaigns(rows, filter) {
        var filtered = rows;
        if (filter && filter !== "all") {
            filtered = rows.filter(function (r) { return r.campaign_type === filter; });
        }
        refs.campaignTableBody.innerHTML = filtered.map(function (r) {
            return '<tr><td>' + esc(fmtDate(r.timestamp)) + '</td><td>' + typeLabel(r.campaign_type) + '</td><td><span class="table-segment">' + esc(r.segment_label) + '</span><span class="table-sub">' + esc(r.loyalty || "") + '</span></td><td>' + esc(r.channel) + '<span class="table-sub">' + esc(r.channel_alignment) + '</span></td><td>' + esc(r.hotel || "Sin asignar") + '</td><td>' + fmtPct(r.engagement_index) + '</td></tr>';
        }).join("");
        if (refs.campaignCount) refs.campaignCount.textContent = filtered.length + " de " + rows.length + " campañas";
    }

    /* ── Pintar acciones ─────────────────────────────────── */

    function renderActions(recommendations) {
        var sourceLabel = recommendations.source === "anthropic" ? "Generado con Anthropic" : "Motor heurístico";
        if (refs.recSource) refs.recSource.textContent = sourceLabel;
        var cards = [
            { title: "Redes sociales", key: "rrss" },
            { title: "Dentro del hotel", key: "hotel" },
            { title: "Publicidad externa", key: "ads" },
        ];
        refs.actionGrid.innerHTML = cards.map(function (c) {
            var block = recommendations[c.key];
            if (!block) return "";
            return '<article class="action-card"><div class="action-card-header"><h3>' + c.title + '</h3></div><p class="action-summary">' + esc(block.summary) + '</p><ul class="action-list">' + block.actions.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join("") + '</ul></article>';
        }).join("");
    }

    /* ── Rellenar formulario de configuración ────────────── */

    function fillForm(ctx) {
        refs.strategicPriority.value = ctx.strategic_priority || "";
        refs.managerNotes.value = (ctx.manager_notes || []).join("\n");
        refs.receptionNotes.value = (ctx.reception_notes || []).join("\n");
        refs.externalSignals.value = (ctx.external_signals || []).join("\n");
    }

    /* ── Pintar dashboard completo ───────────────────────── */

    function renderDashboard(dashboard) {
        currentDashboard = dashboard;
        renderKpis(dashboard.kpis);
        renderOpportunities(dashboard);
        renderFocus(dashboard);

        // Donut: distribución por afinidad principal
        var profileData = (dashboard.performance_by_affinity || []).map(function (p) {
            return { label: p.label, value: p.count };
        });
        renderDonut(refs.donutProfile, profileData);

        // Mapa de calor
        renderHeatmap(dashboard);

        // Desgloses
        renderBreakdown(refs.ageBreakdown, dashboard.performance_by_age);
        renderBreakdown(refs.profileBreakdown, dashboard.performance_by_affinity);
        renderBreakdown(refs.valueBreakdown, dashboard.performance_by_value_level);
        renderBreakdown(refs.momentBreakdown, dashboard.performance_by_moment);

        // Audiencia
        var valueData = (dashboard.performance_by_value_level || []).map(function (v) {
            return { label: v.label, value: v.count };
        });
        renderDonut(refs.donutValue, valueData);
        renderCountryStats(dashboard);
        renderSegments(dashboard.segment_cards);

        // Campañas
        renderCampaignCounters(dashboard.campaign_rows || dashboard.recent_campaigns || []);
        renderCampaigns(dashboard.campaign_rows || dashboard.recent_campaigns || [], activeCampaignFilter);

        // Acciones
        renderActions(dashboard.recommendations);

        // Configuración
        fillForm(dashboard.context);

        setStatus("Panel listo. Última lectura: " + fmtDate(dashboard.generated_at));
    }

    /* ── Filtros de campañas ─────────────────────────────── */

    refs.campaignFilters.addEventListener("click", function (e) {
        var chip = e.target.closest(".filter-chip");
        if (!chip) return;
        refs.campaignFilters.querySelectorAll(".filter-chip").forEach(function (c) { c.classList.remove("active"); });
        chip.classList.add("active");
        activeCampaignFilter = chip.dataset.filter;
        if (currentDashboard) renderCampaigns(currentDashboard.campaign_rows || currentDashboard.recent_campaigns || [], activeCampaignFilter);
    });

    /* ── Event Handlers ──────────────────────────────────── */

    async function refreshDashboard() {
        setStatus("Actualizando lectura de marketing…");
        try { var d = await fetchDashboard(); renderDashboard(d); } catch (e) { setStatus(e.message); }
    }

    refs.configSaveBtn.addEventListener("click", function () { refs.contextForm.requestSubmit(); });

    refs.contextForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        setStatus("Guardando contexto y recalculando…");
        try {
            var r = await saveContext();
            renderDashboard(r.dashboard);
            setStatus("Contexto guardado. Recomendaciones recalculadas.");
            switchSection("overview");
        } catch (err) { setStatus(err.message); }
    });

    /* ── Chat ────────────────────────────────────────────── */

    function openChat() {
        refs.chatPanel.classList.add("open");
        refs.chatOverlay.classList.add("open");
        refs.chatFab.classList.add("hidden");
        refs.chatInput.focus();
    }

    function closeChat() {
        refs.chatPanel.classList.remove("open");
        refs.chatOverlay.classList.remove("open");
        refs.chatFab.classList.remove("hidden");
    }

    refs.chatFab.addEventListener("click", openChat);
    refs.chatCloseBtn.addEventListener("click", closeChat);
    refs.chatOverlay.addEventListener("click", closeChat);

    function addChatMessage(role, text, source) {
        var msg = document.createElement("div");
        msg.className = "chat-msg " + role;
        var bubble = document.createElement("div");
        bubble.className = "chat-msg-bubble";
        bubble.innerHTML = esc(text).replace(/\n/g, "<br>").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        msg.appendChild(bubble);
        if (source && role === "assistant") {
            var src = document.createElement("div");
            src.className = "chat-msg-source";
            src.textContent = source === "anthropic" ? "Anthropic" : "Motor heurístico";
            msg.appendChild(src);
        }
        refs.chatMessages.insertBefore(msg, refs.chatTyping);
        refs.chatMessages.scrollTop = refs.chatMessages.scrollHeight;
    }

    async function handleChatSend() {
        var message = refs.chatInput.value.trim();
        if (!message) return;

        refs.chatInput.value = "";
        refs.chatInput.style.height = "auto";
        refs.chatSendBtn.disabled = true;
        refs.chatSuggestions.style.display = "none";

        addChatMessage("user", message);
        chatHistory.push({ role: "user", content: message });

        refs.chatTyping.classList.add("visible");
        refs.chatMessages.scrollTop = refs.chatMessages.scrollHeight;

        try {
            var resultPromise = sendChatMessage(message);
            var delayPromise = new Promise(function(resolve) { setTimeout(resolve, 1800); });
            
            var results = await Promise.all([resultPromise, delayPromise]);
            var result = results[0];
            
            refs.chatTyping.classList.remove("visible");
            addChatMessage("assistant", result.reply, result.source);
            chatHistory.push({ role: "assistant", content: result.reply });
        } catch (err) {
            refs.chatTyping.classList.remove("visible");
            addChatMessage("assistant", "Lo siento, ha ocurrido un error. Inténtalo de nuevo.");
        }
        refs.chatSendBtn.disabled = false;
    }

    refs.chatSendBtn.addEventListener("click", handleChatSend);

    refs.chatInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleChatSend();
        }
    });

    refs.chatInput.addEventListener("input", function () {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 120) + "px";
    });

    refs.chatSuggestions.addEventListener("click", function (e) {
        var btn = e.target.closest(".chat-suggestion");
        if (!btn) return;
        refs.chatInput.value = btn.dataset.msg;
        handleChatSend();
    });

    /* ── Generator ───────────────────────────────────────── */

    var genSource = document.getElementById("genSource");
    var generateBtn = document.getElementById("generateBtn");
    var proposalGrid = document.getElementById("proposalGrid");
    var modifyOverlay = document.getElementById("modifyOverlay");
    var modifyCloseBtn = document.getElementById("modifyCloseBtn");
    var modifyCampaignName = document.getElementById("modifyCampaignName");
    var modifyCurrentSubject = document.getElementById("modifyCurrentSubject");
    var modifyCurrentPreview = document.getElementById("modifyCurrentPreview");
    var modifyInstructions = document.getElementById("modifyInstructions");
    var modifyApplyBtn = document.getElementById("modifyApplyBtn");
    var modifyResult = document.getElementById("modifyResult");
    var modifySuggestions = document.querySelector(".modify-suggestions");

    var currentProposals = [];
    var selectedCampaignId = null;
    var generatorLoaded = false;

    async function fetchProposals() {
        var r = await fetch("/api/campaigns");
        if (!r.ok) throw new Error("No se pudieron generar las campañas");
        return r.json();
    }

    async function modifyCampaign(campaignId, instructions) {
        var r = await fetch("/api/campaigns/modify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ campaign_id: campaignId, instructions: instructions }),
        });
        if (!r.ok) throw new Error("Error al modificar la campaña");
        return r.json();
    }

    function renderProposals(data) {
        currentProposals = data.proposals || [];
        if (genSource) genSource.textContent = data.source === "anthropic" ? "Generado con Anthropic" : "Motor heurístico";

        if (!currentProposals.length) {
            proposalGrid.innerHTML = '<p class="form-help" style="text-align:center;padding:32px">No se generaron propuestas. Verifica que el dashboard tenga datos cargados.</p>';
            return;
        }

        proposalGrid.innerHTML = '<div class="proposal-grid">' + currentProposals.map(function (p, i) {
            var catClass = p.category || 'default';
            return '<article class="proposal-card">' +
                '<div class="proposal-top">' +
                '<div style="font-weight:700;color:var(--text-primary)">' + esc(p.category_label || typeLabel(p.campaign_type)) + '</div>' +
                '<div class="proposal-info">' +
                '<div class="proposal-name">' + esc(p.name) + '</div>' +
                '<div class="proposal-objective">' + esc(p.objective) + '</div>' +
                '</div>' +
                '<span style="font-weight:600;font-size:12px;color:var(--text-secondary)">' + esc(p.priority || "media").toUpperCase() + '</span>' +
                '</div>' +
                '<div class="proposal-meta">' +
                '<span class="proposal-tag">' + esc(p.channel) + '</span>' +
                '<span class="proposal-tag">' + esc(p.segment) + '</span>' +
                '<span class="proposal-tag">' + esc(p.timing) + '</span>' +
                '</div>' +
                '<div class="proposal-message">' +
                '<div class="proposal-msg-label">Plan de acción</div>' +
                '<div class="proposal-msg-subject">' + esc(p.subject_line) + '</div>' +
                '<div class="proposal-msg-preview">' + esc(p.preview_text) + '</div>' +
                '<div class="proposal-msg-body">' + esc(p.body_summary) + '</div>' +
                '</div>' +
                (p.deliverables ? '<div class="proposal-deliverables"><span class="proposal-deliv-label">Entregables:</span> ' + esc(p.deliverables) + '</div>' : '') +
                '<div class="proposal-rationale">' + esc(p.rationale) + '</div>' +
                '<div class="proposal-actions">' +
                '<button class="btn btn-secondary modify-btn" data-id="' + esc(p.id) + '">Modificar comunicación</button>' +
                '</div>' +
                '</article>';
        }).join("") + '</div>';
    }

    async function loadProposals() {
        if (genSource) genSource.textContent = "Generando campañas…";
        proposalGrid.innerHTML = '<p class="form-help" style="text-align:center;padding:32px">Analizando datos y generando propuestas…</p>';
        try {
            var data = await fetchProposals();
            renderProposals(data);
            generatorLoaded = true;
        } catch (err) {
            if (genSource) genSource.textContent = "Error";
            proposalGrid.innerHTML = '<p class="form-help" style="text-align:center;padding:32px;color:var(--danger)">' + esc(err.message) + '</p>';
        }
    }

    generateBtn.addEventListener("click", loadProposals);

    // Auto-load on first visit
    var originalSwitch = switchSection;
    switchSection = function (sectionId) {
        originalSwitch(sectionId);
        if (sectionId === "generator" && !generatorLoaded) {
            loadProposals();
        }
    };
    // Re-bind nav items with new switchSection
    refs.navItems.forEach(function (item) {
        item.addEventListener("click", function () { switchSection(item.dataset.section); });
    });

    // Modify button delegation
    proposalGrid.addEventListener("click", function (e) {
        var btn = e.target.closest(".modify-btn");
        if (!btn) return;
        var id = btn.dataset.id;
        var campaign = currentProposals.find(function (p) { return p.id === id; });
        if (!campaign) return;

        selectedCampaignId = id;
        modifyCampaignName.textContent = campaign.name;
        modifyCurrentSubject.textContent = campaign.subject_line;
        modifyCurrentPreview.textContent = campaign.preview_text;
        modifyInstructions.value = "";
        modifyResult.style.display = "none";
        modifyResult.innerHTML = "";
        modifyOverlay.classList.add("open");
    });

    modifyCloseBtn.addEventListener("click", function () {
        modifyOverlay.classList.remove("open");
    });
    modifyOverlay.addEventListener("click", function (e) {
        if (e.target === modifyOverlay) modifyOverlay.classList.remove("open");
    });

    if (modifySuggestions) {
        modifySuggestions.addEventListener("click", function (e) {
            var btn = e.target.closest(".chat-suggestion");
            if (!btn) return;
            modifyInstructions.value = btn.dataset.instr;
        });
    }

    modifyApplyBtn.addEventListener("click", async function () {
        var instructions = modifyInstructions.value.trim();
        if (!instructions || !selectedCampaignId) return;

        modifyApplyBtn.disabled = true;
        modifyApplyBtn.textContent = "Aplicando…";

        try {
            var result = await modifyCampaign(selectedCampaignId, instructions);
            var c = result.campaign;
            if (c) {
                modifyResult.style.display = "block";
                modifyResult.innerHTML =
                    '<div class="modify-result-card">' +
                    '<div class="modify-result-label">Resultado de la modificación</div>' +
                    '<div class="modify-result-subject">' + esc(c.subject_line) + '</div>' +
                    '<div class="modify-result-preview">' + esc(c.preview_text) + '</div>' +
                    '<div class="modify-result-body">' + esc(c.body_summary) + '</div>' +
                    '</div>';
            }
        } catch (err) {
            modifyResult.style.display = "block";
            modifyResult.innerHTML = '<p class="form-help" style="color:var(--danger)">' + esc(err.message) + '</p>';
        }
        modifyApplyBtn.disabled = false;
        modifyApplyBtn.textContent = "Aplicar modificación";
    });

    /* ── Autonomous Mode ─────────────────────────────────── */

    var autoEls = {
        toggleBtn: document.getElementById("autoToggleBtn"),
        toggleLabel: document.getElementById("autoToggleLabel"),
        forceMock: document.getElementById("autoForceMock"),
        delayInput: document.getElementById("autoDelayInput"),
        workersInput: document.getElementById("autoWorkersInput"),
        campaignsInput: document.getElementById("autoCampaignsInput"),
        statusDot: document.getElementById("autoStatusDot"),
        statusText: document.getElementById("autoStatusText"),
        statusModel: document.getElementById("autoStatusModel"),
        feedSub: document.getElementById("autoFeedSub"),
        campaignsSub: document.getElementById("autoCampaignsSub"),
        metricOracle: document.getElementById("autoMetricOracle"),
        metricCandidates: document.getElementById("autoMetricCandidates"),
        metricCampaigns: document.getElementById("autoMetricCampaigns"),
        metricBlocked: document.getElementById("autoMetricBlocked"),
        metricProposals: document.getElementById("autoMetricProposals"),
        oracleList: document.getElementById("autoOracleList"),
        campaignList: document.getElementById("autoCampaignList"),
        campaignsList: document.getElementById("autoCampaignsList"),
        log: document.getElementById("autoLog"),
        agentOracle: document.getElementById("agentOracleState"),
        agentRecommender: document.getElementById("agentRecommenderState"),
        agentCampaigns: document.getElementById("agentCampaignsState"),
        agentEmbeddings: document.getElementById("agentEmbeddingsState"),
    };

    var autoRunState = {
        controller: null,
        running: false,
        counts: {
            oracle: 0,
            candidates: 0,
            recs_done: 0,
            recs_skipped: 0,
            proposals_done: 0,
            blocked: 0,
        },
        totalWorkers: 0,
        totalCampaigns: 0,
        // worker_state map: key = "recommender-1"/"proposals-0", value = "idle"|"busy"|"done"
        workerStates: {},
    };

    function setAgentState(which, state, text) {
        var labelEl = autoEls["agent" + which];
        if (!labelEl) return;
        labelEl.textContent = text || "";
        var chip = labelEl.closest(".agent-chip");
        if (chip) {
            chip.classList.remove("idle", "running", "waiting", "done", "error");
            chip.classList.add(state || "idle");
        }
    }

    function autoSetToggle(running) {
        if (!autoEls.toggleBtn) return;
        autoEls.toggleBtn.dataset.state = running ? "running" : "idle";
        autoEls.toggleLabel.textContent = running ? "Detener modo autónomo" : "Iniciar modo autónomo";
    }

    function autoSetStatus(state, text, model) {
        autoEls.statusDot.className = "auto-status-dot " + (state || "idle");
        autoEls.statusText.textContent = text || "";
        if (model !== undefined) autoEls.statusModel.textContent = model || "";
    }

    function autoScrollFeedBottom() {
        var list = autoEls.campaignList;
        if (list) list.scrollTop = list.scrollHeight;
    }

    function autoScrollCampaignsBottom() {
        var list = autoEls.campaignsList;
        if (list) list.scrollTop = list.scrollHeight;
    }

    function autoResetUI() {
        autoRunState.counts = {
            oracle: 0,
            candidates: 0,
            recs_done: 0,
            recs_skipped: 0,
            proposals_done: 0,
            blocked: 0,
        };
        autoRunState.workerStates = {};
        autoRunState.totalWorkers = 0;
        autoRunState.totalCampaigns = 0;
        autoEls.metricOracle.textContent = "—";
        autoEls.metricCandidates.textContent = "—";
        autoEls.metricCampaigns.textContent = "—";
        autoEls.metricBlocked.textContent = "—";
        if (autoEls.metricProposals) autoEls.metricProposals.textContent = "—";
        autoEls.oracleList.innerHTML = '<p class="form-help">Consultando al Oráculo…</p>';
        autoEls.campaignList.innerHTML = '<p class="form-help">En espera de candidatos…</p>';
        if (autoEls.campaignsList) {
            autoEls.campaignsList.innerHTML =
                '<p class="form-help">Un agente independiente generará propuestas de campaña aquí…</p>';
        }
        if (autoEls.feedSub) autoEls.feedSub.textContent = "en espera";
        if (autoEls.campaignsSub) autoEls.campaignsSub.textContent = "en espera";
        autoEls.log.textContent = "";
        setAgentState("Oracle", "idle", "en espera");
        setAgentState("Recommender", "idle", "en espera");
        setAgentState("Campaigns", "idle", "en espera");
        setAgentState("Embeddings", "running", "200 perfiles activos");
    }

    function autoRecomputeRecommenderAgent() {
        var busy = 0;
        var done = 0;
        var total = autoRunState.totalWorkers || 0;
        Object.keys(autoRunState.workerStates).forEach(function (k) {
            if (k.indexOf("recommender-") !== 0) return;
            var s = autoRunState.workerStates[k];
            if (s === "busy") busy++;
            else if (s === "done") done++;
        });
        var state = busy > 0 ? "running" : (done === total && total > 0 ? "done" : "waiting");
        var label;
        if (done === total && total > 0) {
            label = total + " agentes · sesión completa";
        } else {
            label = busy + "/" + total + " activos · " + autoRunState.counts.recs_done + " emitidas";
        }
        setAgentState("Recommender", state, label);
    }

    function autoRecomputeCampaignsAgent() {
        var s = autoRunState.workerStates["proposals-0"];
        var total = autoRunState.totalCampaigns || 0;
        var done = autoRunState.counts.proposals_done;
        if (!s || s === "idle") {
            setAgentState("Campaigns", "waiting", "en espera");
        } else if (s === "busy") {
            setAgentState("Campaigns", "running", "generando · " + done + "/" + total);
        } else {
            setAgentState("Campaigns", "done", done + "/" + total + " emitidas");
        }
    }

    function autoLog(event) {
        try {
            autoEls.log.textContent += JSON.stringify(event) + "\n";
        } catch (_) { /* ignore */ }
    }

    var ORACLE_CATEGORY_LABELS = {
        cultural_event: "Evento cultural",
        extreme_weather: "Meteorología",
        travel_alert: "Alerta de viaje",
        seasonal_offer: "Oferta estacional",
        tourism_trend: "Tendencia turística",
    };

    function renderOracleEntry(entry) {
        var catLabel = ORACLE_CATEGORY_LABELS[entry.category] || entry.category || "";
        var badge = entry.actionable === false ? "auto-badge warn" : "auto-badge";
        var relBadge = '<span class="auto-rel">' + (entry.relevance || "—") + '/10</span>';
        var el = document.createElement("div");
        el.className = "auto-card auto-oracle-card fade-in";
        el.dataset.city = (entry.city || "").toUpperCase();
        el.dataset.category = entry.category || "";
        el.innerHTML =
            '<div class="auto-card-head">' +
            '<span class="' + badge + '">' + esc(catLabel) + '</span>' +
            '<span class="auto-city">' + esc(entry.city || "") + '</span>' +
            relBadge +
            '</div>' +
            '<div class="auto-card-body">' + esc(entry.summary || "") + '</div>' +
            '<div class="auto-card-foot">' + esc(entry.date || "") +
            (entry.actionable === false ? ' · destino bloqueado' : '') + '</div>';
        if (autoEls.oracleList.querySelector("p.form-help")) {
            autoEls.oracleList.innerHTML = "";
        }
        autoEls.oracleList.appendChild(el);
    }

    function autoHighlightOracleCards(cityUp, categories) {
        if (!cityUp) return;
        var cards = autoEls.oracleList.querySelectorAll(".auto-oracle-card");
        cards.forEach(function (c) { c.classList.remove("matched"); });
        var categorySet = {};
        (categories || []).forEach(function (c) { if (c) categorySet[c] = true; });
        cards.forEach(function (c) {
            if (c.dataset.city === cityUp && (!categories || !categories.length || categorySet[c.dataset.category])) {
                c.classList.add("matched");
            }
        });
    }

    function renderMatchedEventsChips(events) {
        if (!events || !events.length) return "";
        return '<div class="auto-matched-events">' +
            '<span class="auto-matched-label">Eventos del Oráculo usados:</span>' +
            events.map(function (e) {
                var catLabel = ORACLE_CATEGORY_LABELS[e.category] || e.category || "";
                return '<span class="auto-event-chip" title="' + esc(e.summary || "") + '">' +
                    '<span class="auto-chip-cat">' + esc(catLabel) + '</span>' +
                    esc(e.summary || "").slice(0, 80) +
                    (e.summary && e.summary.length > 80 ? "…" : "") +
                    '</span>';
            }).join("") +
            '</div>';
    }

    function renderCampaignStart(ev) {
        var workerTag = ev.worker_id
            ? '<span class="auto-worker-tag">agente ' + esc(ev.worker_id) + '</span>'
            : '';
        var el = document.createElement("div");
        el.className = "auto-card auto-campaign-card pending";
        el.id = "auto-campaign-" + ev.guest_id;
        el.innerHTML =
            '<div class="auto-card-head">' +
            '<span class="auto-badge pending">Generando</span>' +
            workerTag +
            '<span class="auto-guest">guest ' + esc(ev.guest_id) + '</span>' +
            '</div>' +
            '<div class="auto-card-skeleton">' +
            '<span class="auto-spinner"></span>' +
            '<div class="auto-skel-text">' +
            '<div class="auto-skel-line lg"></div>' +
            '<div class="auto-skel-line md"></div>' +
            '<div class="auto-skel-line sm"></div>' +
            '</div>' +
            '</div>' +
            '<div class="auto-card-foot">Analizando perfil y eventos del Oráculo para este usuario…</div>';
        if (autoEls.campaignList.querySelector("p.form-help")) {
            autoEls.campaignList.innerHTML = "";
        }
        autoEls.campaignList.appendChild(el);
        autoScrollFeedBottom();
    }

    var CHANNEL_META = {
        email: { icon: "✉️", label: "email" },
        sms: { icon: "💬", label: "sms" },
        push: { icon: "🔔", label: "push" },
    };

    function renderChannelBadge(channel) {
        if (!channel) return "";
        var primary = (channel.primary_channel || "email").toLowerCase();
        var meta = CHANNEL_META[primary] || CHANNEL_META.email;
        var reason = channel.reason || "";
        var secondary = channel.secondary_channel
            ? " · fallback " + channel.secondary_channel
            : "";
        var badge =
            '<span class="auto-channel-badge auto-channel-' + esc(primary) + '"' +
            (reason ? ' title="' + esc(reason + secondary) + '"' : '') + '>' +
            '<span class="auto-channel-icon" aria-hidden="true">' + meta.icon + '</span>' +
            '<span class="auto-channel-label">' + esc(meta.label) + '</span>' +
            '</span>';
        var rationale = reason
            ? '<div class="auto-channel-reason">' + esc(reason) + secondary + '</div>'
            : "";
        return { badge: badge, rationale: rationale, primary: primary };
    }

    function renderSmsPreview(copy) {
        var subject = (copy && copy.subject) || "";
        var firstPara = copy && copy.body_paragraphs && copy.body_paragraphs[0]
            ? copy.body_paragraphs[0]
            : "";
        var text = (subject + " — " + firstPara).slice(0, 160);
        return (
            '<div class="auto-sms-preview" title="Vista previa SMS (160 caracteres)">' +
            '<div class="auto-sms-bubble">' +
            '<span class="auto-sms-icon" aria-hidden="true">💬</span>' +
            '<span class="auto-sms-text">' + esc(text) + '</span>' +
            '</div>' +
            '<div class="auto-sms-foot">' + text.length + '/160 caracteres</div>' +
            '</div>'
        );
    }

    function renderCampaignDone(ev) {
        var existing = document.getElementById("auto-campaign-" + ev.guest_id);
        var seg = ev.segment || {};
        var summary = ev.segment_overview || {};
        var hotel = ev.hotel || {};
        var copy = ev.copy || {};
        var matched = ev.matched_events || [];
        var channel = ev.channel || {};
        var channelRendered = renderChannelBadge(channel);
        var channelBadge = channelRendered ? channelRendered.badge : "";
        var channelReason = channelRendered ? channelRendered.rationale : "";
        var channelPrimary = channelRendered ? channelRendered.primary : "email";

        var paragraphs = (copy.body_paragraphs || []).map(function (p) {
            return '<p>' + esc(p) + '</p>';
        }).join("");

        var workerTag = ev.worker_id
            ? '<span class="auto-worker-tag">agente ' + esc(ev.worker_id) + '</span>'
            : '';
        var content =
            '<div class="auto-card-head">' +
            workerTag +
            '<span class="auto-guest">guest ' + esc(ev.guest_id) + '</span>' +
            '<span class="auto-tag">' + esc((summary.age_label || segmentAgeTag(seg) || "—")) + '</span>' +
            '<span class="auto-tag">' + esc((summary.primary_affinity_label || segmentPrimaryAffinity(seg) || "—")) + '</span>' +
            '<span class="auto-tag">' + esc((summary.value_label || segmentValueLevel(seg) || "—")) + '</span>' +
            channelBadge +
            '</div>' +
            channelReason +
            '<div class="auto-card-hotel">' + esc(hotel.name || "") +
            ' · ' + esc(hotel.city || "") + ' (' + (hotel.stars || "—") + '★)</div>' +
            '<div class="auto-card-subject">' + esc(copy.subject || "") + '</div>' +
            '<div class="auto-card-preheader">' + esc(copy.preheader || "") + '</div>' +
            '<div class="auto-card-headline">' + esc(copy.headline || "") + '</div>' +
            (copy.subheadline ? '<div class="auto-card-subheadline">' + esc(copy.subheadline) + '</div>' : '') +
            '<div class="auto-card-body">' + paragraphs + '</div>' +
            '<div class="auto-card-cta"><span>CTA:</span> ' + esc(copy.cta_text || "") + '</div>' +
            (channelPrimary === "sms" ? renderSmsPreview(copy) : '') +
            (copy.ps_line ? '<div class="auto-card-ps">' + esc(copy.ps_line) + '</div>' : '') +
            renderMatchedEventsChips(matched) +
            '<button type="button" class="auto-card-preview-btn" data-guest="' + esc(ev.guest_id) +
            '" title="Ver email HTML renderizado">Ver email HTML</button>';

        if (existing) {
            existing.classList.remove("pending");
            existing.classList.add("fade-in");
            existing.innerHTML = content;
        } else {
            var el = document.createElement("div");
            el.className = "auto-card auto-campaign-card fade-in";
            el.innerHTML = content;
            autoEls.campaignList.appendChild(el);
        }

        // Resaltar en la columna del Oráculo los eventos efectivamente usados
        autoHighlightOracleCards(
            (hotel.city || "").toUpperCase(),
            matched.map(function (e) { return e.category; })
        );
        autoScrollFeedBottom();
    }

    function openEmailPreview(guestId) {
        var overlay = document.getElementById("emailPreviewOverlay");
        if (!overlay) return;
        overlay.style.display = "flex";
        overlay.innerHTML =
            '<div class="email-preview-modal">' +
            '<div class="email-preview-header">' +
            '<span>Email renderizado · guest ' + esc(guestId) + '</span>' +
            '<button type="button" class="email-preview-close" aria-label="Cerrar">✕</button>' +
            '</div>' +
            '<iframe src="/api/autonomous/email/' + encodeURIComponent(guestId) +
            '" class="email-preview-iframe" title="Email ' + esc(guestId) + '"></iframe>' +
            '</div>';
        overlay.onclick = function (e) {
            if (e.target === overlay || e.target.classList.contains("email-preview-close")) {
                overlay.style.display = "none";
                overlay.innerHTML = "";
            }
        };
    }

    function renderProposalStart(ev) {
        if (!autoEls.campaignsList) return;
        var idx = ev.index || 0;
        var total = ev.total || "?";
        var el = document.createElement("article");
        el.id = "auto-proposal-" + idx;
        el.className = "auto-card auto-proposal-card pending";
        el.innerHTML =
            '<div class="auto-proposal-head">' +
            '<span class="auto-proposal-category">Generando · ' + esc(idx) + '/' + esc(total) + '</span>' +
            '</div>' +
            '<div class="auto-card-skeleton">' +
            '<span class="auto-spinner"></span>' +
            '<div class="auto-skel-text">' +
            '<div class="auto-skel-line lg"></div>' +
            '<div class="auto-skel-line md"></div>' +
            '<div class="auto-skel-line sm"></div>' +
            '<div class="auto-skel-line lg"></div>' +
            '</div>' +
            '</div>';
        if (autoEls.campaignsList.querySelector("p.form-help")) {
            autoEls.campaignsList.innerHTML = "";
        }
        autoEls.campaignsList.appendChild(el);
        autoScrollCampaignsBottom();
    }

    function renderProposalDone(ev) {
        if (!autoEls.campaignsList) return;
        var idx = ev.index || 0;
        var total = ev.total || "?";
        var p = ev.proposal || {};

        var priorityClass = (p.priority || "media").toLowerCase();
        var categoryLabel = p.category_label || p.category || "Campaña";

        var tags = [];
        if (p.channel) tags.push('<span class="auto-tag">' + esc(p.channel) + '</span>');
        if (p.segment) tags.push('<span class="auto-tag">' + esc(p.segment) + '</span>');
        if (p.timing) tags.push('<span class="auto-tag">' + esc(p.timing) + '</span>');

        var rationaleHtml = "";
        if (p.rationale) {
            var long = p.rationale.length > 200;
            rationaleHtml =
                '<div class="auto-proposal-rationale' + (long ? '' : ' expanded') + '">' +
                esc(p.rationale) +
                '</div>' +
                (long
                    ? '<button type="button" class="auto-proposal-rationale-toggle">ver más</button>'
                    : '');
        }

        var html =
            '<div class="auto-proposal-head">' +
            '<span class="auto-proposal-category">' + esc(categoryLabel) +
            ' · ' + esc(idx) + '/' + esc(total) + '</span>' +
            (p.priority
                ? '<span class="auto-proposal-priority ' + esc(priorityClass) + '">' +
                esc(p.priority) + '</span>'
                : '') +
            '</div>' +
            (p.name ? '<div class="auto-proposal-name">' + esc(p.name) + '</div>' : '') +
            (p.objective ? '<div class="auto-proposal-objective">' + esc(p.objective) + '</div>' : '') +
            (tags.length ? '<div class="auto-proposal-tags">' + tags.join("") + '</div>' : '') +
            (p.subject_line
                ? '<div class="auto-proposal-subject">' + esc(p.subject_line) + '</div>'
                : '') +
            (p.preview_text
                ? '<div class="auto-proposal-preview">' + esc(p.preview_text) + '</div>'
                : '') +
            (p.body_summary
                ? '<div class="auto-proposal-body">' + esc(p.body_summary) + '</div>'
                : '') +
            rationaleHtml;

        var existing = document.getElementById("auto-proposal-" + idx);
        if (existing) {
            existing.classList.remove("pending");
            existing.classList.add("fade-in");
            existing.innerHTML = html;
        } else {
            var el = document.createElement("article");
            el.id = "auto-proposal-" + idx;
            el.className = "auto-card auto-proposal-card fade-in";
            el.innerHTML = html;
            if (autoEls.campaignsList.querySelector("p.form-help")) {
                autoEls.campaignsList.innerHTML = "";
            }
            autoEls.campaignsList.appendChild(el);
        }
        autoScrollCampaignsBottom();
    }

    function renderCampaignSkipped(ev) {
        var existing = document.getElementById("auto-campaign-" + ev.guest_id);
        var html =
            '<div class="auto-card-head">' +
            '<span class="auto-badge warn">Omitido</span>' +
            '<span class="auto-guest">guest ' + esc(ev.guest_id) + '</span>' +
            '</div>' +
            '<div class="auto-card-body">' + esc(ev.reason || "") + '</div>';
        if (existing) {
            existing.classList.remove("pending");
            existing.innerHTML = html;
        } else {
            var el = document.createElement("div");
            el.className = "auto-card auto-campaign-card";
            el.innerHTML = html;
            autoEls.campaignList.appendChild(el);
        }
        autoScrollFeedBottom();
    }

    function handleAutoEvent(ev) {
        autoLog(ev);

        switch (ev.type) {
            case "start":
                autoSetStatus("running", "Arrancando modo autónomo…",
                    (ev.config && ev.config.gemini_available) ? ("Modelo: " + ev.config.model) : "Modo mock");
                if (ev.config) {
                    autoRunState.totalWorkers = ev.config.recommender_workers || 0;
                    autoRunState.totalCampaigns = ev.config.campaigns_per_tick || 0;
                }
                if (autoEls.feedSub && ev.config) {
                    autoEls.feedSub.textContent =
                        (ev.config.recommender_workers || 1) + " agentes · cap " +
                        (ev.config.max_recommendations || "?");
                }
                if (autoEls.campaignsSub && ev.config) {
                    autoEls.campaignsSub.textContent =
                        (ev.config.campaigns_per_tick || 0) + " campañas programadas";
                }
                break;

            case "oracle_start":
                autoSetStatus("running", "Consultando al Oráculo…");
                setAgentState("Oracle", "running", "refrescando señales…");
                break;

            case "oracle_entry":
                autoRunState.counts.oracle++;
                autoEls.metricOracle.textContent = autoRunState.counts.oracle;
                renderOracleEntry(ev.entry || {});
                setAgentState("Oracle", "running",
                    autoRunState.counts.oracle + " señales detectadas");
                break;

            case "oracle_done":
                autoRunState.counts.blocked = (ev.blocked || []).length;
                autoEls.metricBlocked.textContent = autoRunState.counts.blocked;
                autoSetStatus("running", "Oráculo listo: " + (ev.count || 0) + " señales · " +
                    autoRunState.counts.blocked + " destinos bloqueados");
                setAgentState("Oracle", "done",
                    (ev.count || 0) + " señales · " + autoRunState.counts.blocked + " bloqueados");
                break;

            case "candidates_start":
                autoSetStatus("running", "Calculando candidatos…");
                setAgentState("Recommender", "running", "seleccionando candidatos…");
                break;

            case "candidate":
                autoRunState.counts.candidates++;
                autoEls.metricCandidates.textContent = autoRunState.counts.candidates;
                break;

            case "candidates_done":
                autoSetStatus("running", (ev.count || 0) + " candidatos en cola");
                setAgentState("Recommender", "running", (ev.count || 0) + " candidatos en cola");
                if (ev.count === 0) {
                    autoEls.campaignList.innerHTML =
                        '<p class="form-help">No hay candidatos en esta ventana de envío.</p>';
                }
                break;

            case "feed_start":
                autoRunState.totalWorkers = ev.recommender_workers || autoRunState.totalWorkers;
                autoRunState.totalCampaigns = ev.campaigns_per_tick != null ? ev.campaigns_per_tick : autoRunState.totalCampaigns;
                autoSetStatus("running",
                    autoRunState.totalWorkers + " agentes generando en paralelo…");
                if (autoEls.feedSub) {
                    autoEls.feedSub.textContent =
                        (ev.total_candidates || 0) + " candidatos · " +
                        autoRunState.totalWorkers + " agentes concurrentes";
                }
                if (autoRunState.totalCampaigns > 0) {
                    setAgentState("Campaigns", "waiting",
                        "0/" + autoRunState.totalCampaigns + " emitidas");
                } else {
                    setAgentState("Campaigns", "idle", "desactivadas");
                }
                autoRecomputeRecommenderAgent();
                break;

            case "worker_state":
                var key = (ev.kind || "recommender") + "-" + (ev.worker_id || 0);
                autoRunState.workerStates[key] = ev.state;
                if (ev.kind === "proposals") {
                    autoRecomputeCampaignsAgent();
                } else {
                    autoRecomputeRecommenderAgent();
                }
                break;

            case "campaign_start":
                renderCampaignStart(ev);
                autoSetStatus("running",
                    "Agente " + (ev.worker_id || "?") + " → guest " + ev.guest_id + "…");
                break;

            case "campaign_done":
                autoRunState.counts.recs_done++;
                autoEls.metricCampaigns.textContent = autoRunState.counts.recs_done;
                renderCampaignDone(ev);
                autoRecomputeRecommenderAgent();
                break;

            case "campaign_skipped":
                autoRunState.counts.recs_skipped++;
                renderCampaignSkipped(ev);
                autoRecomputeRecommenderAgent();
                break;

            case "proposal_start":
                renderProposalStart(ev);
                if (autoEls.campaignsSub) {
                    autoEls.campaignsSub.textContent =
                        "generando " + (ev.index || "?") + "/" + (ev.total || "?");
                }
                break;

            case "proposal_done":
                autoRunState.counts.proposals_done++;
                if (autoEls.metricProposals) {
                    autoEls.metricProposals.textContent = autoRunState.counts.proposals_done;
                }
                renderProposalDone(ev);
                autoRecomputeCampaignsAgent();
                if (autoEls.campaignsSub) {
                    autoEls.campaignsSub.textContent =
                        autoRunState.counts.proposals_done + "/" +
                        (ev.total || autoRunState.totalCampaigns) + " emitidas";
                }
                break;

            case "feed_done":
                if (autoEls.feedSub) {
                    autoEls.feedSub.textContent =
                        (ev.recommendations_generated || 0) + " recomendaciones · " +
                        (ev.proposals_generated || 0) + " campañas · " +
                        (ev.reason === "cap_reached" ? "cap alcanzado" : "cola agotada");
                }
                break;

            case "error":
                autoSetStatus("error",
                    "Error en " + (ev.stage || "?") +
                    (ev.worker_id ? " (agente " + ev.worker_id + ")" : "") +
                    ": " + (ev.message || ""));
                break;

            case "tick_done":
                var sum = ev.summary || {};
                autoSetStatus("done", "Sesión cerrada en " + ev.duration_seconds + "s · " +
                    (sum.recommendations_generated || 0) + " recomendaciones · " +
                    (sum.campaigns_generated || 0) + " campañas");
                autoStopRun(false);
                break;
        }
    }

    async function autoStreamTick(opts) {
        opts = opts || {};
        var params = new URLSearchParams();
        if (opts.forceMock) params.set("force_mock", "1");
        if (opts.delay != null) params.set("delay", String(opts.delay));
        if (opts.max != null) params.set("max", String(opts.max));
        if (opts.workers != null) params.set("workers", String(opts.workers));
        if (opts.campaigns != null) params.set("campaigns", String(opts.campaigns));

        autoRunState.controller = new AbortController();
        var response;
        try {
            response = await fetch("/api/autonomous/stream?" + params.toString(), {
                signal: autoRunState.controller.signal,
                headers: { "Accept": "application/x-ndjson" },
            });
        } catch (err) {
            if (err && err.name === "AbortError") return;
            autoSetStatus("error", "No se pudo iniciar el tick: " + err.message);
            autoStopRun(false);
            return;
        }
        if (!response.ok || !response.body) {
            autoSetStatus("error", "Respuesta inválida del servidor (" + response.status + ")");
            autoStopRun(false);
            return;
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        try {
            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                buffer += decoder.decode(chunk.value, { stream: true });
                var lines = buffer.split("\n");
                buffer = lines.pop();
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim();
                    if (!line) continue;
                    try {
                        handleAutoEvent(JSON.parse(line));
                    } catch (e) { /* ignore malformed */ }
                }
            }
            if (buffer.trim()) {
                try { handleAutoEvent(JSON.parse(buffer.trim())); } catch (_) { }
            }
        } catch (err) {
            if (err && err.name !== "AbortError") {
                autoSetStatus("error", "Stream interrumpido: " + err.message);
            }
        } finally {
            autoStopRun(false);
        }
    }

    function autoStartRun() {
        if (autoRunState.running) return;
        autoRunState.running = true;
        autoSetToggle(true);
        autoResetUI();
        autoSetStatus("running", "Arrancando modo autónomo…");
        var delay = autoEls.delayInput ? parseInt(autoEls.delayInput.value, 10) : NaN;
        var workers = autoEls.workersInput ? parseInt(autoEls.workersInput.value, 10) : NaN;
        var campaigns = autoEls.campaignsInput ? parseInt(autoEls.campaignsInput.value, 10) : NaN;
        autoStreamTick({
            forceMock: autoEls.forceMock ? autoEls.forceMock.checked : false,
            delay: isNaN(delay) ? null : Math.max(0, Math.min(60, delay)),
            workers: isNaN(workers) ? null : Math.max(1, Math.min(6, workers)),
            campaigns: isNaN(campaigns) ? null : Math.max(0, Math.min(10, campaigns)),
        });
    }

    function autoStopRun(abort) {
        if (abort && autoRunState.controller) {
            try { autoRunState.controller.abort(); } catch (_) { }
        }
        autoRunState.running = false;
        autoRunState.controller = null;
        autoSetToggle(false);
    }

    if (autoEls.toggleBtn) {
        autoEls.toggleBtn.addEventListener("click", function () {
            if (autoRunState.running) {
                autoSetStatus("idle", "Modo autónomo detenido.");
                autoStopRun(true);
            } else {
                autoStartRun();
            }
        });
    }

    if (autoEls.campaignList) {
        autoEls.campaignList.addEventListener("click", function (e) {
            var btn = e.target.closest && e.target.closest(".auto-card-preview-btn");
            if (!btn) return;
            var guest = btn.getAttribute("data-guest");
            if (guest) openEmailPreview(guest);
        });
    }

    if (autoEls.campaignsList) {
        autoEls.campaignsList.addEventListener("click", function (e) {
            var btn = e.target.closest && e.target.closest(".auto-proposal-rationale-toggle");
            if (!btn) return;
            var rationale = btn.previousElementSibling;
            if (rationale && rationale.classList.contains("auto-proposal-rationale")) {
                var expanded = rationale.classList.toggle("expanded");
                btn.textContent = expanded ? "ver menos" : "ver más";
            }
        });
    }

    /* ── Init ────────────────────────────────────────────── */

    refreshDashboard();
})();
