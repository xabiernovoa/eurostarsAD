/* ═══════════════════════════════════════════════════════════
   Eurostars · Recepción Inteligente — Application Logic
   ═══════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ── DOM references ──────────────────────────────────
    const searchInput   = document.getElementById('searchInput');
    const scanBtn       = document.getElementById('scanBtn');
    const guestList     = document.getElementById('guestList');
    const guestCount    = document.getElementById('guestCount');
    const quickFilters  = document.getElementById('quickFilters');
    const emptyState    = document.getElementById('emptyState');
    const loadingState  = document.getElementById('loadingState');
    const reportViewer  = document.getElementById('reportViewer');
    const reportFrame   = document.getElementById('reportFrame');
    const toolbarTitle  = document.getElementById('toolbarTitle');
    const backBtn       = document.getElementById('backBtn');
    const printBtn      = document.getElementById('printBtn');
    const checkinBtn    = document.getElementById('checkinBtn');
    const checkinOverlay = document.getElementById('checkinOverlay');
    const successGuestName = document.getElementById('successGuestName');
    const successCloseBtn  = document.getElementById('successCloseBtn');
    const clockEl       = document.getElementById('clock');

    // ── State ───────────────────────────────────────────
    let allGuests = [];
    let filteredGuests = [];
    let activeGuestId = null;
    let activeFilter = '';

    // ── Clock ───────────────────────────────────────────
    function updateClock() {
        const now = new Date();
        const h = String(now.getHours()).padStart(2, '0');
        const m = String(now.getMinutes()).padStart(2, '0');
        const s = String(now.getSeconds()).padStart(2, '0');
        const day = now.toLocaleDateString('es-ES', {
            weekday: 'short', day: 'numeric', month: 'short'
        });
        clockEl.textContent = `${day} · ${h}:${m}:${s}`;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ── Fetch guests ────────────────────────────────────
    async function fetchGuests(query = '') {
        const url = query
            ? `/api/guests?q=${encodeURIComponent(query)}`
            : '/api/guests';
        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error('Failed to fetch');
            return await res.json();
        } catch (err) {
            console.error('Error fetching guests:', err);
            return [];
        }
    }

    // ── Render guest list ───────────────────────────────
    function renderGuestList(guests) {
        filteredGuests = guests;
        guestCount.textContent = `${guests.length} huéspedes`;

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
            const initials = getInitials(g);
            const tagClass = getValueTagClass(g.value);
            const tagLabel = g.value || 'STANDARD';
            const meta = [g.gender, g.age_range, g.country]
                .filter(Boolean).join(' · ');
            const isActive = g.id === activeGuestId;

            return `
                <li class="guest-card ${isActive ? 'active' : ''}"
                    data-id="${g.id}"
                    onclick="window.__selectGuest('${g.id}')">
                    <div class="guest-avatar">${initials}</div>
                    <div class="guest-info">
                        <div class="guest-id">Guest #${g.id}</div>
                        <div class="guest-meta">${meta}${g.profile ? ' · ' + g.profile : ''}</div>
                    </div>
                    <span class="guest-value-tag ${tagClass}">${tagLabel}</span>
                </li>`;
        }).join('');
    }

    function getInitials(guest) {
        // Use profile first letter + country
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
        return 'tag-low';
    }

    // ── Select guest ────────────────────────────────────
    window.__selectGuest = async function(id) {
        activeGuestId = id;

        // Update sidebar active state
        document.querySelectorAll('.guest-card').forEach(el => {
            el.classList.toggle('active', el.dataset.id === id);
        });

        // Show loading
        showView('loading');

        // Simulate scanning delay for demo effect
        await sleep(randomInt(800, 1600));

        // Load the report
        const guest = allGuests.find(g => g.id === id);
        toolbarTitle.textContent = `Informe de Recepción — Guest #${id}`;

        reportFrame.srcdoc = '';
        try {
            const res = await fetch(`/api/report/${id}`);
            if (!res.ok) throw new Error('Not found');
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

    // ── View management ─────────────────────────────────
    function showView(view) {
        emptyState.classList.toggle('hidden', view !== 'empty');
        loadingState.classList.toggle('hidden', view !== 'loading');
        reportViewer.classList.toggle('hidden', view !== 'report');
    }

    // ── Search handling ─────────────────────────────────
    let searchTimeout;
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

    function matchGuest(g, q) {
        return (
            (g.id && g.id.toLowerCase().includes(q)) ||
            (g.profile && g.profile.toLowerCase().includes(q)) ||
            (g.country && g.country.toLowerCase().includes(q)) ||
            (g.value && g.value.toLowerCase().includes(q)) ||
            (g.gender && g.gender.toLowerCase().includes(q)) ||
            (g.last_hotel && g.last_hotel.toLowerCase().includes(q)) ||
            (g.hotels && g.hotels.some(h => h.toLowerCase().includes(q)))
        );
    }

    // ── Filter chips ────────────────────────────────────
    quickFilters.addEventListener('click', (e) => {
        const chip = e.target.closest('.filter-chip');
        if (!chip) return;

        quickFilters.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');

        activeFilter = chip.dataset.filter || '';
        const results = applyActiveFilter(allGuests);
        renderGuestList(results);
    });

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

    // ── Scan button (simulated random guest) ────────────
    scanBtn.addEventListener('click', async () => {
        // Visual feedback
        scanBtn.style.transform = 'scale(0.9)';
        setTimeout(() => scanBtn.style.transform = '', 200);

        if (allGuests.length === 0) return;

        // Pick a random guest to simulate scanning
        const randomGuest = allGuests[randomInt(0, allGuests.length - 1)];

        // Focus the search
        searchInput.value = randomGuest.id;
        const results = allGuests.filter(g => g.id === randomGuest.id);
        renderGuestList(results);

        // Auto-select
        await sleep(300);
        window.__selectGuest(randomGuest.id);
    });

    // ── Toolbar buttons ─────────────────────────────────
    backBtn.addEventListener('click', () => {
        activeGuestId = null;
        showView('empty');
        searchInput.value = '';
        renderGuestList(applyActiveFilter(allGuests));
    });

    printBtn.addEventListener('click', () => {
        if (reportFrame.contentWindow) {
            reportFrame.contentWindow.print();
        }
    });

    // ── Check-in confirmation ───────────────────────────
    checkinBtn.addEventListener('click', () => {
        if (!activeGuestId) return;
        successGuestName.textContent = `Guest #${activeGuestId}`;
        checkinOverlay.classList.remove('hidden');
    });

    successCloseBtn.addEventListener('click', () => {
        checkinOverlay.classList.add('hidden');
        activeGuestId = null;
        showView('empty');
        searchInput.value = '';
        renderGuestList(applyActiveFilter(allGuests));
    });

    // Close overlay on backdrop click
    checkinOverlay.addEventListener('click', (e) => {
        if (e.target === checkinOverlay) {
            checkinOverlay.classList.add('hidden');
        }
    });

    // ── Keyboard shortcut ───────────────────────────────
    document.addEventListener('keydown', (e) => {
        // Escape to go back
        if (e.key === 'Escape') {
            if (!checkinOverlay.classList.contains('hidden')) {
                checkinOverlay.classList.add('hidden');
            } else if (!reportViewer.classList.contains('hidden')) {
                backBtn.click();
            }
        }
        // Ctrl+K to focus search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            searchInput.focus();
        }
    });

    // ── Helpers ──────────────────────────────────────────
    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }
    function randomInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    // ── Initialize ──────────────────────────────────────
    async function init() {
        allGuests = await fetchGuests();
        renderGuestList(allGuests);
        showView('empty');
    }

    init();

})();
