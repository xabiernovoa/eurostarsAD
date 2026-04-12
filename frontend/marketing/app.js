(function () {
    "use strict";

    /* ── DOM References ──────────────────────────────────── */

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

    /* ── Theme (always light) ────────────────────────────── */
    document.documentElement.setAttribute("data-theme", "light");

    /* ── Navigation ──────────────────────────────────────── */

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

    /* ── Helpers ──────────────────────────────────────────── */

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
            pre_arrival: "Pre-Arrival", post_stay: "Post-Stay", checkin_report: "Check-in",
            contenido_rrss: "Contenido RRSS", hotel_insite: "In-Hotel",
            local_partnership: "Partnership local", branding: "Branding",
            geolocalizacion: "Geolocalización", evento: "Evento", decoracion: "Decoración"
        }[t] || t;
    }
    function categoryIcon(cat) {
        return {
            rrss: "RRSS", hotel: "Hotel", local: "Local", branding: "Brand",
            geolocalizacion: "Geo", evento: "Evento", decoracion: "Deco"
        }[cat] || cat || "";
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

    /* ── Render: KPIs ────────────────────────────────────── */

    function renderKpis(kpis) {
        var items = [
            { label: "Campañas", value: kpis.total_campaigns, note: "Campañas deduplicadas", indicator: "good" },
            { label: "Audiencia", value: kpis.audience_size, note: "Usuarios segmentados", indicator: "good" },
            { label: "Segmentos activos", value: kpis.active_segments, note: "Cruces edad-perfil", indicator: kpis.active_segments >= 10 ? "good" : "neutral" },
            { label: "Índice medio", value: fmtPct(kpis.avg_engagement_index), note: "Engagement estimado", indicator: kpis.avg_engagement_index >= 0.75 ? "good" : kpis.avg_engagement_index >= 0.5 ? "neutral" : "low" },
            { label: "Presión estratégica", value: kpis.priority_pressure + "/100", note: "Intensidad señales", indicator: kpis.priority_pressure >= 70 ? "good" : "neutral" },
        ];
        refs.kpiGrid.innerHTML = items.map(function (k) {
            return '<article class="kpi-card"><div class="kpi-header"><div class="kpi-label">' + k.label + '</div></div><div class="kpi-value">' + k.value + '</div><div class="kpi-footnote">' + k.note + '</div></article>';
        }).join("");
    }

    /* ── Render: Opportunities ───────────────────────────── */

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
            '<div class="opportunity-card"><div><div class="opportunity-label">Segmento top</div><div class="opportunity-value">' + esc(topSeg.segment_label || "—") + '</div><div class="opportunity-detail">' + (topSeg.users || 0) + ' usuarios · ' + fmtPct(topSeg.avg_engagement_index) + ' engagement · ' + Math.round(topSeg.avg_adr || 0) + '€ ADR</div></div></div>' +
            '<div class="opportunity-card"><div><div class="opportunity-label">Ciudad con más tracción</div><div class="opportunity-value">' + esc(topCity) + '</div><div class="opportunity-detail">Destino con mayor concentración de campañas y señales externas activas</div></div></div>' +
            '<div class="opportunity-card"><div><div class="opportunity-label">Mejor canal</div><div class="opportunity-value">' + esc(bestChannel) + '</div><div class="opportunity-detail">Engagement medio ' + fmtPct(bestChAvg) + ' sobre ' + (channelMap[bestChannel] ? channelMap[bestChannel].count : 0) + ' campañas recientes</div></div></div>';
    }

    /* ── Render: Focus ───────────────────────────────────── */

    function renderFocus(dashboard) {
        refs.priorityText.textContent = dashboard.context.strategic_priority || "Sin prioridad definida.";
        var html = '<span class="cities-label">Ciudades en foco</span>';
        (dashboard.focus_cities || []).forEach(function (c) { html += '<span class="city-pill">' + esc(c) + '</span>'; });
        refs.citiesRow.innerHTML = html;
        refs.sidebarUpdated.textContent = "Actualizado " + fmtDate(dashboard.generated_at);
    }

    /* ── Render: SVG Donut ───────────────────────────────── */

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

    /* ── Render: Heatmap ─────────────────────────────────── */

    function renderHeatmap(dashboard) {
        var rows = dashboard.campaign_rows || dashboard.recent_campaigns || [];
        var ageSegments = ["JOVEN", "ADULTO", "SENIOR"];
        var channels = ["email", "sms", "push"];

        var grid = {};
        ageSegments.forEach(function (a) {
            channels.forEach(function (c) { grid[a + "|" + c] = { sum: 0, count: 0 }; });
        });
        rows.forEach(function (r) {
            var key = r.age_segment + "|" + r.channel;
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

    /* ── Render: Breakdowns ──────────────────────────────── */

    function renderBreakdown(container, items) {
        var html = '<div class="breakdown-list">';
        items.forEach(function (item) {
            var pct = Math.max(8, Math.round(item.avg_engagement_index * 100));
            html += '<div class="breakdown-item"><div class="breakdown-meta"><span class="breakdown-name">' + esc(item.label) + '</span><span class="breakdown-stats">' + fmtPct(item.avg_engagement_index) + ' · ' + item.count + ' campañas</span></div><div class="meter"><div class="meter-fill" style="width:' + pct + '%"></div></div></div>';
        });
        html += '</div>';
        container.innerHTML = html;
    }

    /* ── Render: Segments ────────────────────────────────── */

    function renderSegments(cards) {
        refs.segmentGrid.innerHTML = cards.map(function (c) {
            return '<article class="segment-card"><h3>' + esc(c.segment_label) + '</h3><div class="segment-meta">Canal: ' + esc(c.dominant_channel) + ' · Momento: ' + esc(c.dominant_moment) + '</div><div class="segment-meta" style="margin-top:8px">' + c.users + ' usuarios · ' + c.campaigns + ' campañas · ' + fmtPct(c.avg_engagement_index) + ' índice · ' + Math.round(c.avg_adr) + '€ ADR</div></article>';
        }).join("");
        if (refs.audienceCount) refs.audienceCount.textContent = cards.length + " segmentos activos";
    }

    /* ── Render: Country Stats ───────────────────────────── */

    function renderCountryStats(dashboard) {
        var rows = dashboard.campaign_rows || dashboard.recent_campaigns || [];
        var countries = {};
        rows.forEach(function (r) {
            var seg = r.age_segment || "";
            // We don't have country directly on campaign_rows, but we can infer from segment_cards
        });
        // Use segment_cards which have user counts, but aggregate by looking at campaign data
        // Since we don't have country per campaign, let's show a simplified version
        var flags = { ES: "🇪🇸", PT: "🇵🇹", IT: "🇮🇹" };
        var names = { ES: "España", PT: "Portugal", IT: "Italia" };
        // We need to count from the segments data — use a rough estimate from the dashboard
        var segs = dashboard.segment_cards || [];
        var totalUsers = segs.reduce(function (s, c) { return s + c.users; }, 0);

        var html = "";
        ["ES", "PT", "IT"].forEach(function (code) {
            var count = Math.round(totalUsers * (code === "ES" ? 0.45 : code === "PT" ? 0.28 : 0.27));
            html += '<div class="country-card"><div class="country-name">' + (names[code] || code) + '</div><div class="country-count">' + count + '</div><div class="country-detail">usuarios activos</div></div>';
        });
        refs.countryRow.innerHTML = html;
    }

    /* ── Render: Campaign Counters ───────────────────────── */

    function renderCampaignCounters(rows) {
        var counts = { pre_arrival: 0, post_stay: 0, checkin_report: 0 };
        rows.forEach(function (r) {
            if (counts[r.campaign_type] !== undefined) counts[r.campaign_type]++;
        });
        var items = [
            { label: "Pre-Arrival", count: counts.pre_arrival, cls: "pre_arrival" },
            { label: "Post-Stay", count: counts.post_stay, cls: "post_stay" },
            { label: "Check-in", count: counts.checkin_report, cls: "checkin_report" },
        ];
        refs.campaignCounters.innerHTML = items.map(function (i) {
            return '<div class="counter-card"><div class="counter-value">' + i.count + '</div><div class="counter-label">' + i.label + '</div></div>';
        }).join("");
    }

    /* ── Render: Campaigns ───────────────────────────────── */

    function renderCampaigns(rows, filter) {
        var filtered = rows;
        if (filter && filter !== "all") {
            filtered = rows.filter(function (r) { return r.campaign_type === filter; });
        }
        refs.campaignTableBody.innerHTML = filtered.map(function (r) {
            return '<tr><td>' + esc(fmtDate(r.timestamp)) + '</td><td>' + typeLabel(r.campaign_type) + '</td><td><span class="table-segment">' + esc(r.age_segment) + '</span><span class="table-sub">' + esc(r.travel_profile) + '</span></td><td>' + esc(r.channel) + '<span class="table-sub">' + esc(r.channel_alignment) + '</span></td><td>' + esc(r.hotel || "Sin asignar") + '</td><td>' + fmtPct(r.engagement_index) + '</td></tr>';
        }).join("");
        if (refs.campaignCount) refs.campaignCount.textContent = filtered.length + " de " + rows.length + " campañas";
    }

    /* ── Render: Actions ─────────────────────────────────── */

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

    /* ── Render: Config Form ─────────────────────────────── */

    function fillForm(ctx) {
        refs.strategicPriority.value = ctx.strategic_priority || "";
        refs.managerNotes.value = (ctx.manager_notes || []).join("\n");
        refs.receptionNotes.value = (ctx.reception_notes || []).join("\n");
        refs.externalSignals.value = (ctx.external_signals || []).join("\n");
    }

    /* ── Render: Full Dashboard ──────────────────────────── */

    function renderDashboard(dashboard) {
        currentDashboard = dashboard;
        renderKpis(dashboard.kpis);
        renderOpportunities(dashboard);
        renderFocus(dashboard);

        // Donut: profile distribution
        var profileData = (dashboard.performance_by_profile || []).map(function (p) {
            return { label: p.label, value: p.count };
        });
        renderDonut(refs.donutProfile, profileData);

        // Heatmap
        renderHeatmap(dashboard);

        // Breakdowns
        renderBreakdown(refs.ageBreakdown, dashboard.performance_by_age);
        renderBreakdown(refs.profileBreakdown, dashboard.performance_by_profile);
        renderBreakdown(refs.valueBreakdown, dashboard.performance_by_value);
        renderBreakdown(refs.momentBreakdown, dashboard.performance_by_moment);

        // Audience
        var valueData = (dashboard.performance_by_value || []).map(function (v) {
            return { label: v.label, value: v.count };
        });
        renderDonut(refs.donutValue, valueData);
        renderCountryStats(dashboard);
        renderSegments(dashboard.segment_cards);

        // Campaigns
        renderCampaignCounters(dashboard.campaign_rows || dashboard.recent_campaigns || []);
        renderCampaigns(dashboard.campaign_rows || dashboard.recent_campaigns || [], activeCampaignFilter);

        // Actions
        renderActions(dashboard.recommendations);

        // Config
        fillForm(dashboard.context);

        setStatus("Dashboard listo. Última lectura: " + fmtDate(dashboard.generated_at));
    }

    /* ── Campaign Filters ────────────────────────────────── */

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
        statusDot: document.getElementById("autoStatusDot"),
        statusText: document.getElementById("autoStatusText"),
        statusModel: document.getElementById("autoStatusModel"),
        feedSub: document.getElementById("autoFeedSub"),
        metricOracle: document.getElementById("autoMetricOracle"),
        metricCandidates: document.getElementById("autoMetricCandidates"),
        metricCampaigns: document.getElementById("autoMetricCampaigns"),
        metricBlocked: document.getElementById("autoMetricBlocked"),
        oracleList: document.getElementById("autoOracleList"),
        campaignList: document.getElementById("autoCampaignList"),
        log: document.getElementById("autoLog"),
    };

    var autoRunState = {
        controller: null,
        running: false,
        counts: { oracle: 0, candidates: 0, campaigns: 0, blocked: 0 },
        pauseTimer: null,
    };

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

    function autoClearPauseCountdown() {
        if (autoRunState.pauseTimer) {
            clearInterval(autoRunState.pauseTimer);
            autoRunState.pauseTimer = null;
        }
        var node = document.getElementById("autoPauseCard");
        if (node) node.remove();
    }

    function autoShowPauseCountdown(seconds) {
        autoClearPauseCountdown();
        if (!seconds || seconds <= 0) return;

        var el = document.createElement("div");
        el.id = "autoPauseCard";
        el.className = "auto-pause-card";
        el.innerHTML =
            '<div class="auto-pause-icon"><span class="auto-dot"></span></div>' +
            '<div class="auto-pause-text">Pausa antes de la siguiente recomendación · ' +
            '<span id="autoPauseSeconds">' + seconds + '</span>s</div>';
        if (autoEls.campaignList.querySelector("p.form-help")) {
            autoEls.campaignList.innerHTML = "";
        }
        autoEls.campaignList.appendChild(el);
        autoScrollFeedBottom();

        var remaining = seconds;
        autoRunState.pauseTimer = setInterval(function () {
            remaining -= 1;
            var span = document.getElementById("autoPauseSeconds");
            if (span) span.textContent = Math.max(0, remaining);
            if (remaining <= 0) autoClearPauseCountdown();
        }, 1000);
    }

    function autoResetUI() {
        autoRunState.counts = { oracle: 0, candidates: 0, campaigns: 0, blocked: 0 };
        autoEls.metricOracle.textContent = "—";
        autoEls.metricCandidates.textContent = "—";
        autoEls.metricCampaigns.textContent = "—";
        autoEls.metricBlocked.textContent = "—";
        autoEls.oracleList.innerHTML = '<p class="form-help">Consultando al Oráculo…</p>';
        autoEls.campaignList.innerHTML = '<p class="form-help">En espera de candidatos…</p>';
        if (autoEls.feedSub) autoEls.feedSub.textContent = "en espera";
        autoEls.log.textContent = "";
        autoClearPauseCountdown();
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
        autoClearPauseCountdown();
        var el = document.createElement("div");
        el.className = "auto-card auto-campaign-card pending";
        el.id = "auto-campaign-" + ev.guest_id;
        el.innerHTML =
            '<div class="auto-card-head">' +
            '<span class="auto-badge pending">Generando</span>' +
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

    function renderCampaignDone(ev) {
        var existing = document.getElementById("auto-campaign-" + ev.guest_id);
        var seg = ev.segment || {};
        var hotel = ev.hotel || {};
        var copy = ev.copy || {};
        var matched = ev.matched_events || [];

        var paragraphs = (copy.body_paragraphs || []).map(function (p) {
            return '<p>' + esc(p) + '</p>';
        }).join("");

        var content =
            '<div class="auto-card-head">' +
            '<span class="auto-guest">guest ' + esc(ev.guest_id) + '</span>' +
            '<span class="auto-tag">' + esc(seg.age_segment || "—") + '</span>' +
            '<span class="auto-tag">' + esc(seg.travel_profile || "—") + '</span>' +
            '<span class="auto-tag">' + esc(seg.client_value || "—") + '</span>' +
            '</div>' +
            '<div class="auto-card-hotel">' + esc(hotel.name || "") +
            ' · ' + esc(hotel.city || "") + ' (' + (hotel.stars || "—") + '★)</div>' +
            '<div class="auto-card-subject">' + esc(copy.subject || "") + '</div>' +
            '<div class="auto-card-preheader">' + esc(copy.preheader || "") + '</div>' +
            '<div class="auto-card-headline">' + esc(copy.headline || "") + '</div>' +
            (copy.subheadline ? '<div class="auto-card-subheadline">' + esc(copy.subheadline) + '</div>' : '') +
            '<div class="auto-card-body">' + paragraphs + '</div>' +
            '<div class="auto-card-cta"><span>CTA:</span> ' + esc(copy.cta_text || "") + '</div>' +
            (copy.ps_line ? '<div class="auto-card-ps">' + esc(copy.ps_line) + '</div>' : '') +
            renderMatchedEventsChips(matched);

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
                if (autoEls.feedSub && ev.config) {
                    autoEls.feedSub.textContent =
                        "cap " + (ev.config.max_recommendations || "?") +
                        " · pausa " + (ev.config.delay_between_seconds || 0) + "s";
                }
                break;

            case "oracle_start":
                autoSetStatus("running", "Consultando al Oráculo…");
                break;

            case "oracle_entry":
                autoRunState.counts.oracle++;
                autoEls.metricOracle.textContent = autoRunState.counts.oracle;
                renderOracleEntry(ev.entry || {});
                break;

            case "oracle_done":
                autoRunState.counts.blocked = (ev.blocked || []).length;
                autoEls.metricBlocked.textContent = autoRunState.counts.blocked;
                autoSetStatus("running", "Oráculo listo: " + (ev.count || 0) + " señales · " +
                    autoRunState.counts.blocked + " destinos bloqueados");
                break;

            case "candidates_start":
                autoSetStatus("running", "Calculando candidatos…");
                break;

            case "candidate":
                autoRunState.counts.candidates++;
                autoEls.metricCandidates.textContent = autoRunState.counts.candidates;
                break;

            case "candidates_done":
                autoSetStatus("running", (ev.count || 0) + " candidatos en cola");
                if (ev.count === 0) {
                    autoEls.campaignList.innerHTML =
                        '<p class="form-help">No hay candidatos en esta ventana de envío.</p>';
                }
                break;

            case "feed_start":
                autoSetStatus("running", "Feed autónomo en marcha…");
                if (autoEls.feedSub) {
                    autoEls.feedSub.textContent =
                        (ev.total_candidates || 0) + " candidatos · pausa " +
                        (ev.delay_between_seconds || 0) + "s entre envíos";
                }
                break;

            case "campaign_start":
                renderCampaignStart(ev);
                autoSetStatus("running",
                    "Generando recomendación para guest " + ev.guest_id + "…");
                break;

            case "campaign_done":
                autoRunState.counts.campaigns++;
                autoEls.metricCampaigns.textContent = autoRunState.counts.campaigns;
                renderCampaignDone(ev);
                autoSetStatus("running", "Recomendación entregada · pausa antes de la siguiente…");
                break;

            case "campaign_skipped":
                renderCampaignSkipped(ev);
                break;

            case "pause":
                autoShowPauseCountdown(ev.delay_seconds || 0);
                if (autoEls.feedSub) {
                    autoEls.feedSub.textContent =
                        "pausa " + (ev.delay_seconds || 0) + "s · " +
                        (ev.remaining_candidates || 0) + " candidatos en cola";
                }
                break;

            case "feed_done":
                autoClearPauseCountdown();
                if (autoEls.feedSub) {
                    autoEls.feedSub.textContent =
                        ev.total_recommendations + " recomendaciones emitidas · " +
                        (ev.reason === "max_reached" ? "cap alcanzado" : "cola agotada");
                }
                break;

            case "error":
                autoSetStatus("error", "Error en " + (ev.stage || "?") + ": " + (ev.message || ""));
                break;

            case "tick_done":
                var sum = ev.summary || {};
                autoSetStatus("done", "Sesión cerrada en " + ev.duration_seconds + "s · " +
                    (sum.recommendations_generated || 0) + " recomendaciones");
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
        autoStreamTick({
            forceMock: autoEls.forceMock ? autoEls.forceMock.checked : false,
        });
    }

    function autoStopRun(abort) {
        if (abort && autoRunState.controller) {
            try { autoRunState.controller.abort(); } catch (_) { }
        }
        autoRunState.running = false;
        autoRunState.controller = null;
        autoClearPauseCountdown();
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

    /* ── Init ────────────────────────────────────────────── */

    refreshDashboard();
})();
