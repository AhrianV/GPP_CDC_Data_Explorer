const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../static/js/public-data.js'), 'utf8');
const snapshotSource = fs.readFileSync(path.join(__dirname, '../static/js/cdc-demo-data.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup({page = 'diseases', search = '', failDraw = false, deferPlotly = false} = {}) {
    const snapshotContext = {window: {}};
    vm.runInNewContext(snapshotSource, snapshotContext);
    const snapshots = snapshotContext.window.CDC_DEMO_DATA;
    function element(extra = {}) {
        return {hidden: false, disabled: false, textContent: '', dataset: {}, handlers: {},
            addEventListener(name, callback) { this.handlers[name] = callback; }, ...extra};
    }
    const plots = Object.keys(snapshots[page].charts).map(chartId => element({dataset: {chartId}}));
    const forms = plots.map(() => element({hidden: true}));
    const elements = Object.fromEntries(['data-loading-status', 'data-fallback-notice',
        'data-fallback-message', 'load-saved-data', 'retry-recent-data'].map(id => [id, element()]));
    const root = element({dataset: {page, liveUrl: '/api/public-charts/' + page, topojsonUrl: '/static/vendor/'},
        querySelectorAll: selector => selector === '[data-chart-id]' ? plots : forms});
    elements['public-data-page'] = root;
    const timers = new Map();
    const requests = [];
    const draws = [];
    let nextTimer = 0;
    let domReady;
    const context = {
        document: {readyState: deferPlotly ? 'interactive' : 'complete', getElementById: id => elements[id],
            addEventListener(name, callback) { if (name === 'DOMContentLoaded') domReady = callback; }},
        window: {...snapshotContext.window, location: {search, hash: ''}, Plotly: {
            react: async (plot, data, layout, config) => {
                if (failDraw) throw new Error('Simulated plot failure');
                draws.push({id: plot.dataset.chartId, data, layout, config});
            },
        }},
        AbortController, URLSearchParams,
        setTimeout(fn, delay) { timers.set(++nextTimer, {fn, delay}); return nextTimer; },
        clearTimeout(id) { timers.delete(id); },
        fetch(url, options) { return new Promise((resolve, reject) => requests.push({url, options, resolve, reject})); },
    };
    const plotly = context.window.Plotly;
    if (deferPlotly) delete context.window.Plotly;
    vm.runInNewContext(source, context);
    const success = (index = 0) => requests[index].resolve({ok: true, headers: {get: () => 'application/json'},
        json: async () => snapshots[page]});
    return {elements, requests, draws, timers, success, forms,
        finishScripts: () => { context.window.Plotly = plotly; domReady(); },
        saved: () => elements['load-saved-data'].handlers.click(),
        retry: () => elements['retry-recent-data'].handlers.click()};
}

for (const page of ['diseases', 'vaccinations']) {
    test(`${page}: at 10 seconds offer saved charts, ignore late responses, make no fallback request`, async () => {
        const ui = setup({page});
        const timer = [...ui.timers.values()][0];
        assert.equal(timer.delay, 10000);
        timer.fn();
        assert.equal(ui.requests[0].options.signal.aborted, true);
        assert.equal(ui.elements['data-fallback-notice'].hidden, false);
        assert.equal(ui.draws.length, 0); // Explicit user choice, no silent data substitution.
        await ui.saved();
        const count = page === 'diseases' ? 2 : 3;
        assert.equal(ui.draws.length, count);
        assert.equal(ui.requests.length, 1);
        assert.match(ui.elements['data-fallback-message'].textContent, /saved snapshot captured/);
        assert.equal(ui.draws[0].config.topojsonURL, '/static/vendor/');
        ui.success(); // Deliberately emulate a server ignoring the browser's abort.
        await tick();
        assert.equal(ui.draws.length, count);
        assert.equal(ui.forms.every(form => form.hidden), true);
    });

    test(`${page}: demo=1 immediately renders bundled charts without fetching recent data`, async () => {
        const ui = setup({page, search: '?demo=1'});
        await tick();
        assert.equal(ui.requests.length, 0);
        assert.equal(ui.draws.length, page === 'diseases' ? 2 : 3);
        assert.match(ui.elements['data-fallback-message'].textContent, /Latest reporting period:/);
    });
}

test('a successful recent load clears the timer and enables analysis', async () => {
    const ui = setup();
    ui.success();
    await tick();
    assert.equal(ui.timers.size, 0);
    assert.equal(ui.elements['data-fallback-notice'].hidden, true);
    assert.equal(ui.draws.length, 2);
    assert.equal(ui.forms.every(form => !form.hidden), true);
});

test('HTTP errors immediately offer the saved-data button; retry can restore live mode', async () => {
    const ui = setup();
    ui.requests[0].resolve({ok: false, headers: {get: () => 'text/html'}});
    await tick();
    assert.equal(ui.elements['data-fallback-notice'].hidden, false);
    await ui.saved();
    const retried = ui.retry();
    ui.success(1);
    await retried;
    assert.equal(ui.elements['data-fallback-notice'].hidden, true);
    assert.match(ui.elements['data-loading-status'].textContent, /CDC data loaded/);
});

test('a stalled JSON body still hits the 10-second deadline', async () => {
    const ui = setup();
    ui.requests[0].resolve({ok: true, headers: {get: () => 'application/json'}, json: () => new Promise(() => {})});
    await tick();
    [...ui.timers.values()][0].fn();
    assert.equal(ui.elements['data-fallback-notice'].hidden, false);
    await ui.saved();
    assert.equal(ui.draws.length, 2);
});

test('chart rendering errors do not leave the fallback button stuck', async () => {
    const ui = setup({failDraw: true});
    [...ui.timers.values()][0].fn();
    await ui.saved();
    assert.equal(ui.elements['load-saved-data'].disabled, false);
    assert.match(ui.elements['data-fallback-message'].textContent, /Simulated plot failure/);
});

test('demo mode waits for the deferred local Plotly bundle before rendering', async () => {
    const ui = setup({search: '?demo=1', deferPlotly: true});
    await tick();
    assert.equal(ui.draws.length, 0);
    ui.finishScripts();
    await tick();
    assert.equal(ui.draws.length, 2);
    assert.equal(ui.requests.length, 0);
    assert.match(ui.elements['data-loading-status'].textContent, /Showing saved demo data/);
});
