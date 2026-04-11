(function () {
    "use strict";

    const refs = {
        refreshBtn: document.getElementById("refreshBtn"),
        saveBtn: document.getElementById("saveBtn"),
        statusLine: document.getElementById("statusLine"),
        generatedAt: document.getElementById("generatedAt"),
        kpiGrid: document.getElementById("kpiGrid"),
        priorityText: document.getElementById("priorityText"),
        cityList: document.getElementById("cityList"),
        ageBreakdown: document.getElementById("ageBreakdown"),
        profileBreakdown: document.getElementById("profileBreakdown"),
        valueBreakdown: document.getElementById("valueBreakdown"),
        momentBreakdown: document.getElementById("momentBreakdown"),
        recommendationGrid: document.getElementById("recommendationGrid"),
        recSource: document.getElementById("recSource"),
        segmentGrid: document.getElementById("segmentGrid"),
        campaignTableBody: document.getElementById("campaignTableBody"),
        contextForm: document.getElementById("contextForm"),
        strategicPriority: document.getElementById("strategicPriority"),
        managerNotes: document.getElementById("managerNotes"),
        receptionNotes: document.getElementById("receptionNotes"),
        externalSignals: document.getElementById("externalSignals"),
    };

    let currentDashboard = null;

    function setStatus(message) {
        refs.statusLine.textContent = message;
    }

    async function fetchDashboard() {
        const response = await fetch("/api/dashboard");
        if (!response.ok) {
            throw new Error("No se pudo cargar el dashboard");
        }
        return response.json();
    }

    async function saveContext() {
        const payload = {
            strategic_priority: refs.strategicPriority.value.trim(),
            manager_notes: linesFromTextarea(refs.managerNotes),
            reception_notes: linesFromTextarea(refs.receptionNotes),
            external_signals: linesFromTextarea(refs.externalSignals),
        };
        const response = await fetch("/api/context", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error("No se pudo guardar el contexto");
        }
        return response.json();
    }

    function linesFromTextarea(textarea) {
        return textarea.value
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean);
    }

    function formatDate(value) {
        if (!value) return "Sin fecha";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return new Intl.DateTimeFormat("es-ES", {
            day: "2-digit",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    function formatPct(value) {
        return `${Math.round((value || 0) * 100)}%`;
    }

    function renderKpis(kpis) {
        const items = [
            ["Campañas", kpis.total_campaigns, "Campañas deduplicadas analizadas"],
            ["Audiencia", kpis.audience_size, "Usuarios segmentados en la base"],
            ["Segmentos activos", kpis.active_segments, "Cruces edad y perfil con actividad"],
            ["Índice medio", formatPct(kpis.avg_engagement_index), "Lectura estimada de tracción"],
            ["Presión estratégica", `${kpis.priority_pressure}/100`, "Intensidad de señales y prioridades"],
        ];

        refs.kpiGrid.innerHTML = items.map(([label, value, footnote]) => `
            <article class="kpi-card">
                <div class="kpi-label">${label}</div>
                <div class="kpi-value">${value}</div>
                <div class="kpi-footnote">${footnote}</div>
            </article>
        `).join("");
    }

    function renderFocus(dashboard) {
        refs.generatedAt.textContent = `Actualizado ${formatDate(dashboard.generated_at)}`;
        refs.priorityText.textContent = dashboard.context.strategic_priority || "Sin prioridad definida.";
        refs.cityList.innerHTML = (dashboard.focus_cities || []).map((city) => `
            <span class="city-pill">${escapeHtml(city)}</span>
        `).join("");
    }

    function renderBreakdown(container, items) {
        container.innerHTML = `
            <div class="breakdown-list">
                ${items.map((item) => `
                    <div class="breakdown-item">
                        <div class="breakdown-row">
                            <span class="breakdown-name">${escapeHtml(item.label)}</span>
                            <span class="breakdown-stats">${formatPct(item.avg_engagement_index)} · ${item.count} campañas</span>
                        </div>
                        <div class="meter">
                            <div class="meter-fill" style="width:${Math.max(8, Math.round(item.avg_engagement_index * 100))}%"></div>
                        </div>
                    </div>
                `).join("")}
            </div>
        `;
    }

    function renderRecommendations(recommendations) {
        const sourceLabel = recommendations.source === "anthropic" ? "Anthropic" : "Motor heurístico";
        refs.recSource.textContent = sourceLabel;

        const cards = [
            ["RRSS", recommendations.rrss],
            ["Dentro del hotel", recommendations.hotel],
            ["Publicidad externa", recommendations.ads],
        ];

        refs.recommendationGrid.innerHTML = cards.map(([title, block]) => `
            <article class="recommendation-card">
                <h3>${title}</h3>
                <p class="recommendation-summary">${escapeHtml(block.summary)}</p>
                <ul>
                    ${block.actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}
                </ul>
            </article>
        `).join("");
    }

    function renderSegments(cards) {
        refs.segmentGrid.innerHTML = cards.map((card) => `
            <article class="segment-card">
                <div>
                    <h3>${escapeHtml(card.segment_label)}</h3>
                    <div class="segment-meta">Canal dominante: ${escapeHtml(card.dominant_channel)} · Momento dominante: ${escapeHtml(card.dominant_moment)}</div>
                </div>
                <div class="segment-stats">
                    <span class="segment-chip">${card.users} usuarios</span>
                    <span class="segment-chip">${card.campaigns} campañas</span>
                    <span class="segment-chip">${formatPct(card.avg_engagement_index)} índice</span>
                    <span class="segment-chip">${Math.round(card.avg_adr)}€ ADR medio</span>
                </div>
            </article>
        `).join("");
    }

    function renderCampaigns(rows) {
        refs.campaignTableBody.innerHTML = rows.map((row) => `
            <tr>
                <td>${escapeHtml(formatDate(row.timestamp))}</td>
                <td>${escapeHtml(row.campaign_type)}</td>
                <td>
                    <span class="table-segment">${escapeHtml(row.age_segment)}</span>
                    <span class="table-sub">${escapeHtml(row.travel_profile)}</span>
                </td>
                <td>
                    <span>${escapeHtml(row.channel)}</span>
                    <span class="table-sub">${escapeHtml(row.channel_alignment)}</span>
                </td>
                <td>${escapeHtml(row.hotel || "Sin asignar")}</td>
                <td><span class="index-badge">${formatPct(row.engagement_index)}</span></td>
            </tr>
        `).join("");
    }

    function fillForm(context) {
        refs.strategicPriority.value = context.strategic_priority || "";
        refs.managerNotes.value = (context.manager_notes || []).join("\n");
        refs.receptionNotes.value = (context.reception_notes || []).join("\n");
        refs.externalSignals.value = (context.external_signals || []).join("\n");
    }

    function renderDashboard(dashboard) {
        currentDashboard = dashboard;
        renderKpis(dashboard.kpis);
        renderFocus(dashboard);
        renderBreakdown(refs.ageBreakdown, dashboard.performance_by_age);
        renderBreakdown(refs.profileBreakdown, dashboard.performance_by_profile);
        renderBreakdown(refs.valueBreakdown, dashboard.performance_by_value);
        renderBreakdown(refs.momentBreakdown, dashboard.performance_by_moment);
        renderRecommendations(dashboard.recommendations);
        renderSegments(dashboard.segment_cards);
        renderCampaigns(dashboard.recent_campaigns);
        fillForm(dashboard.context);
        setStatus("Dashboard listo. Puedes ajustar el contexto y recalcular.");
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    async function refreshDashboard() {
        setStatus("Actualizando lectura de marketing…");
        try {
            const dashboard = await fetchDashboard();
            renderDashboard(dashboard);
        } catch (error) {
            setStatus(error.message);
        }
    }

    refs.refreshBtn.addEventListener("click", refreshDashboard);
    refs.saveBtn.addEventListener("click", async () => {
        refs.contextForm.requestSubmit();
    });

    refs.contextForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        setStatus("Guardando contexto y recalculando recomendaciones…");
        try {
            const response = await saveContext();
            renderDashboard(response.dashboard);
            setStatus("Contexto guardado. Recomendaciones recalculadas.");
        } catch (error) {
            setStatus(error.message);
        }
    });

    refreshDashboard();
})();
