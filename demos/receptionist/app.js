/* ═══════════════════════════════════════════════════════════
   Eurostars · Recepción Inteligente — Lógica de aplicación
   ═══════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ── Referencias DOM ─────────────────────────────────
    const searchInput = document.getElementById('searchInput') || document.getElementById('globalSearch');
    const scanBtn = document.getElementById('scanBtn');
    const guestList = document.getElementById('guestList');
    const guestCount = document.getElementById('guestCount');
    const quickFilters = document.getElementById('quickFilters');
    const emptyState = document.getElementById('emptyState');
    const reportViewer = document.getElementById('reportViewer');
    const reportFrame = document.getElementById('reportFrame');
    const toolbarTitle = document.getElementById('toolbarTitle');
    const backBtn = document.getElementById('backBtn');
    const printBtn = document.getElementById('printBtn');
    const checkinBtn = document.getElementById('checkinBtn');
    const checkinOverlay = document.getElementById('checkinOverlay');
    const successGuestName = document.getElementById('successGuestName');
    const successCloseBtn = document.getElementById('successCloseBtn');
    const clockEl = document.getElementById('clock');

    // ── Estado ──────────────────────────────────────────
    let allGuests = [];
    let filteredGuests = [];
    let activeGuestId = null;
    let activeFilter = '';

    // ── Reloj ────────────────────────────────────────────
    const clockDateEl = document.getElementById('clockDate');

    function updateClock() {
        if (!clockEl) return;
        const now = new Date();
        const h = String(now.getHours()).padStart(2, '0');
        const m = String(now.getMinutes()).padStart(2, '0');
        const s = String(now.getSeconds()).padStart(2, '0');
        clockEl.textContent = `${h}:${m}:${s}`;
        if (clockDateEl) {
            clockDateEl.textContent = now.toLocaleDateString('es-ES', {
                weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'
            });
        }
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ── Cargar huéspedes ────────────────────────────────
    async function fetchGuests(query = '') {
        const url = query
            ? `/api/guests?q=${encodeURIComponent(query)}`
            : '/api/guests';
        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error('No se pudo cargar la lista');
            return await res.json();
        } catch (err) {
            console.error('Error al cargar los huéspedes:', err);
            return [];
        }
    }

    // ── Pintar lista de huéspedes ───────────────────────
    function renderGuestList(guests) {
        filteredGuests = guests;
        if (guestCount) {
            guestCount.textContent = `${guests.length} huéspedes`;
        }

        if (guests.length === 0) {
            guestList.innerHTML = `
                <li class="guest-card" style="justify-content:center; cursor:default; padding:40px 14px;">
                    <p style="font-size:13px; color:var(--text-muted); text-align:center;">
                        No se encontraron huéspedes
                    </p>
                </li>`;
            return;
        }

        guestList.innerHTML = guests.map(g => {
            const tagClass = getValueTagClass(g.value);
            const tagLabel = g.value || 'ESTANDAR';
            const meta = [g.gender, g.age_range, g.country]
                .filter(Boolean).join(' · ');
            const isActive = g.id === activeGuestId;
            const displayName = g.name || `Huésped ${g.id.toString().slice(-4)}`;
            const subMeta = [meta, g.profile, g.email || `ID ${g.id}`]
                .filter(Boolean)
                .join(' · ');

            return `
                <li class="guest-card ${isActive ? 'active' : ''}"
                    data-id="${g.id}"
                    onclick="window.__selectGuest('${g.id}')">
                    <div style="flex: 1;">
                        <div class="guest-id">#${g.id}</div>
                        <div class="guest-name">${displayName}</div>
                        <div class="guest-meta">${subMeta}</div>
                    </div>
                </li>`;
        }).join('');
    }

    function getInitials(guest) {
        if (guest.name) {
            const parts = guest.name.trim().split(/\s+/).filter(Boolean);
            return parts.slice(0, 2).map(p => p[0].toUpperCase()).join('');
        }
        const p = (guest.profile || 'G')[0];
        const c = (guest.country || 'X')[0];
        return p + c;
    }

    function getValueTagClass(value) {
        if (!value) return 'tag-low';
        const v = value.toLowerCase();
        if (v.includes('high')) return 'tag-high';
        if (v.includes('mid')) return 'tag-mid';
        if (v.includes('vip')) return 'tag-vip';
        if (v.includes('premium')) return 'tag-high';
        if (v.includes('confort')) return 'tag-mid';
        return 'tag-low';
    }

    // ── Seleccionar huésped ─────────────────────────────
    window.__selectGuest = async function (id) {
        activeGuestId = id;

        // Actualizar el estado activo de la barra lateral
        document.querySelectorAll('.guest-card').forEach(el => {
            el.classList.toggle('active', el.dataset.id === id);
        });

        const guest = allGuests.find(g => g.id === id);
        const displayName = guest && guest.name ? guest.name : `Huésped #${id}`;
        if (toolbarTitle) {
            toolbarTitle.textContent = `Informe de Recepción — ${displayName}`;
        }

        try {
            const res = await fetch(`/api/report/${id}`);
            if (!res.ok) throw new Error('No encontrado');
            const html = await res.text();
            reportFrame.srcdoc = html;
        } catch (err) {
            reportFrame.srcdoc = `
                <html><body style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#666;">
                    <p>Error cargando el informe del huésped</p>
                </body></html>`;
        }

        showView('report');
    };

    // ── Gestión de vistas ───────────────────────────────
    function showView(view) {
        emptyState.classList.toggle('hidden', view !== 'empty');
        reportViewer.classList.toggle('hidden', view !== 'report');
    }

    // ── Gestión de búsqueda ─────────────────────────────
    let searchTimeout;
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(async () => {
                const query = searchInput.value.trim();
                let results;
                if (query) {
                    results = allGuests.filter(g =>
                        matchGuest(g, query.toLowerCase())
                    );
                } else {
                    results = applyActiveFilter(allGuests);
                }
                renderGuestList(results);
            }, 200);
        });
    }

    function matchGuest(g, q) {
        return (
            (g.id && g.id.toLowerCase().includes(q)) ||
            (g.guest_number && g.guest_number.toLowerCase().includes(q)) ||
            (g.name && g.name.toLowerCase().includes(q)) ||
            (g.email && g.email.toLowerCase().includes(q)) ||
            (g.first_name && g.first_name.toLowerCase().includes(q)) ||
            (g.last_name && g.last_name.toLowerCase().includes(q)) ||
            (g.profile && g.profile.toLowerCase().includes(q)) ||
            (g.country && g.country.toLowerCase().includes(q)) ||
            (g.value && g.value.toLowerCase().includes(q)) ||
            (g.gender && g.gender.toLowerCase().includes(q)) ||
            (g.last_hotel && g.last_hotel.toLowerCase().includes(q)) ||
            (g.hotels && g.hotels.some(h => h.toLowerCase().includes(q)))
        );
    }

    // ── Chips de filtro ─────────────────────────────────
    if (quickFilters) {
        quickFilters.addEventListener('click', (e) => {
            const chip = e.target.closest('.filter-chip');
            if (!chip) return;

            quickFilters.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');

            activeFilter = chip.dataset.filter || '';
            const results = applyActiveFilter(allGuests);
            renderGuestList(results);
        });
    }

    function applyActiveFilter(guests) {
        if (!activeFilter) return guests;
        return guests.filter(g => {
            const v = (g.value || '').toLowerCase();
            if (activeFilter === 'high') return v.includes('high');
            if (activeFilter === 'mid') return v.includes('mid');
            if (activeFilter === 'vip') return v.includes('vip');
            return true;
        });
    }

    // ── Botón de escaneo (huésped aleatorio simulado) ──
    if (scanBtn) {
        scanBtn.addEventListener('click', async () => {
            scanBtn.style.transform = 'scale(0.9)';
            setTimeout(() => scanBtn.style.transform = '', 200);

            if (allGuests.length === 0) return;

            const randomGuest = allGuests[randomInt(0, allGuests.length - 1)];

            if (searchInput) {
                searchInput.value = randomGuest.name || randomGuest.id;
            }
            const results = allGuests.filter(g => g.id === randomGuest.id);
            renderGuestList(results);

            window.__selectGuest(randomGuest.id);
        });
    }

    // ── Botones de la barra de herramientas ─────────────
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            activeGuestId = null;
            showView('empty');
            if (searchInput) {
                searchInput.value = '';
            }
            renderGuestList(applyActiveFilter(allGuests));
        });
    }

    if (printBtn) {
        printBtn.addEventListener('click', () => {
            if (reportFrame.contentWindow) {
                reportFrame.contentWindow.print();
            }
        });
    }

    // ── Confirmación de check-in ────────────────────────
    if (checkinBtn) {
        checkinBtn.addEventListener('click', () => {
            if (!activeGuestId) return;
            const guest = allGuests.find(g => g.id === activeGuestId);
            successGuestName.textContent = guest && guest.name ? guest.name : `Huésped #${activeGuestId}`;
            checkinOverlay.classList.remove('hidden');
        });
    }

    if (successCloseBtn) {
        successCloseBtn.addEventListener('click', () => {
            checkinOverlay.classList.add('hidden');
            activeGuestId = null;
            showView('empty');
            if (searchInput) {
                searchInput.value = '';
            }
            renderGuestList(applyActiveFilter(allGuests));
        });
    }

    // Cerrar la capa al hacer clic en el fondo
    checkinOverlay.addEventListener('click', (e) => {
        if (e.target === checkinOverlay) {
            checkinOverlay.classList.add('hidden');
        }
    });

    // ── Atajos de teclado ───────────────────────────────
    document.addEventListener('keydown', (e) => {
        // Escape para volver
        if (e.key === 'Escape') {
            if (!checkinOverlay.classList.contains('hidden')) {
                checkinOverlay.classList.add('hidden');
            } else if (!reportViewer.classList.contains('hidden')) {
                if (backBtn) {
                    backBtn.click();
                }
            }
        }
        // Ctrl+K para enfocar la búsqueda
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (searchInput) {
                searchInput.focus();
            }
        }
    });

    // ── Utilidades ──────────────────────────────────────
    function randomInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    // ── Inicialización ──────────────────────────────────
    async function init() {
        allGuests = await fetchGuests();
        renderGuestList(allGuests);
        showView('empty');
    }

    init();

})();
