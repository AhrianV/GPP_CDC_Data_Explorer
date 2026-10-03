(() => {
    'use strict';
    const root = document.getElementById('public-data-page');
    if (!root) return;
    const status = document.getElementById('data-loading-status');
    const notice = document.getElementById('data-fallback-notice');
    const message = document.getElementById('data-fallback-message');
    const savedButton = document.getElementById('load-saved-data');
    const retryButton = document.getElementById('retry-recent-data');
    const plots = [...root.querySelectorAll('[data-chart-id]')];
    const analysisForms = [...root.querySelectorAll('[data-live-analysis]')];
    const snapshot = window.CDC_DEMO_DATA?.[root.dataset.page];
    // Deferred scripts run while readyState is "interactive", before later
    // deferred scripts (including the local Plotly bundle) have executed.
    const plotlyReady = window.Plotly || document.readyState === 'complete'
        ? Promise.resolve()
        : new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve, {once: true}));
    let attempt = 0;
    let controller;
    let timer;
    let usingSaved = false;

    function offerSavedData() {
        status.textContent = 'Recent CDC data could not be loaded.';
        notice.hidden = false;
        savedButton.hidden = false;
        savedButton.disabled = !snapshot;
        message.textContent = usingSaved
            ? 'Recent CDC data still could not be loaded. The saved demo data remains on screen.'
            : "We weren't able to load recent CDC data. Select “Load without recent data” to view the saved demo data.";
        analysisForms.forEach(form => { form.hidden = true; });
    }

    async function draw(payload, id) {
        await plotlyReady;
        if (id !== attempt) return false;
        if (!window.Plotly) throw new Error('The chart library could not be loaded. Please reload this page.');
        if (!payload?.charts || plots.some(plot => !Array.isArray(payload.charts[plot.dataset.chartId]?.data))) {
            throw new Error('The chart data is incomplete.');
        }
        await Promise.all(plots.map(plot => {
            // Plotly may mutate figures; keep the bundled snapshot reusable.
            const figure = JSON.parse(JSON.stringify(payload.charts[plot.dataset.chartId]));
            return window.Plotly.react(plot, figure.data, figure.layout, {
                responsive: true, displaylogo: false, topojsonURL: root.dataset.topojsonUrl,
            });
        }));
        if (id !== attempt) return false;
        const target = document.getElementById(window.location.hash.slice(1));
        if (target) target.scrollIntoView({block: 'start'});
        return true;
    }

    async function loadRecent() {
        const id = ++attempt;
        controller?.abort();
        clearTimeout(timer);
        controller = new AbortController();
        retryButton.disabled = true;
        status.textContent = 'Loading CDC data…';
        if (!usingSaved) notice.hidden = true;
        timer = setTimeout(() => {
            if (id !== attempt) return;
            ++attempt; // Ignore even a late response that disregards AbortSignal.
            controller.abort();
            retryButton.disabled = false;
            offerSavedData();
        }, 10000);
        try {
            const response = await fetch(root.dataset.liveUrl, {
                signal: controller.signal, headers: {Accept: 'application/json'}, cache: 'no-store',
            });
            if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
                throw new Error('Recent data is unavailable.');
            }
            const payload = await response.json();
            if (id !== attempt) return;
            if (!await draw(payload, id)) return;
            usingSaved = false;
            notice.hidden = true;
            savedButton.hidden = false;
            status.textContent = `CDC data loaded. Latest reporting period: ${payload.latest_reporting_period}.`;
            analysisForms.forEach(form => { form.hidden = false; });
        } catch (error) {
            if (id !== attempt) return;
            offerSavedData();
        } finally {
            if (id === attempt) {
                clearTimeout(timer);
                retryButton.disabled = false;
            }
        }
    }

    async function loadSaved() {
        const id = ++attempt;
        controller?.abort();
        clearTimeout(timer);
        savedButton.disabled = true;
        retryButton.disabled = false;
        notice.hidden = false;
        analysisForms.forEach(form => { form.hidden = true; });
        try {
            if (!await draw(snapshot, id)) return;
            usingSaved = true;
            status.textContent = 'Showing saved demo data.';
            message.textContent = `Recent CDC data was not loaded. Showing a saved snapshot captured ${snapshot.captured_at.slice(0, 10)} (UTC). Latest reporting period: ${snapshot.latest_reporting_period}. AI analysis is available after loading recent data.`;
            savedButton.hidden = true;
        } catch (error) {
            if (id === attempt) message.textContent = error.message || 'Saved charts could not be drawn. Please reload this page.';
        } finally {
            if (id === attempt) savedButton.disabled = false;
        }
    }

    savedButton.addEventListener('click', loadSaved);
    retryButton.addEventListener('click', loadRecent);
    if (new URLSearchParams(window.location.search).get('demo') === '1') loadSaved();
    else loadRecent();
})();
