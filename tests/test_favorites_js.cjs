const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../static/js/favorites.js'), 'utf8');

function setup(fetchResponse) {
    let submit;
    const actionInput = {value: 'save'};
    const icon = {className: 'bi bi-heart'};
    const label = {textContent: 'Save chart'};
    const status = {textContent: ''};
    const attributes = {};
    const button = {
        disabled: false,
        classList: {toggle: (name, value) => { attributes[name] = value; }},
        setAttribute: (name, value) => { attributes[name] = value; },
        querySelector: selector => selector === 'i' ? icon : label,
    };
    const form = {
        // Real forms expose named inputs as properties, including "action".
        action: actionInput,
        dataset: {chartTitle: 'Vaccination trends'},
        getAttribute: name => name === 'action' ? '/charts/vaccination-trends/favorite' : null,
        addEventListener: (name, handler) => { if (name === 'submit') submit = handler; },
        setAttribute() {},
        removeAttribute() {},
        querySelector: selector => ({
            'button': button, '.favorite-status': status, '[name="action"]': actionInput,
        })[selector],
    };
    const requests = [];
    vm.runInNewContext(source, {
        document: {querySelectorAll: () => [form]},
        window: {addEventListener() {}},
        FormData: class { constructor() { this.action = actionInput.value; } },
        fetch: async (url, options) => {
            requests.push({url, options});
            return fetchResponse(options);
        },
    });
    return {submit: () => submit({preventDefault() {}}), requests, button, actionInput, attributes, label, status};
}

test('favorites use the endpoint attribute despite the action input, then support removal', async () => {
    const ui = setup(options => ({
        ok: true, headers: {get: () => 'application/json'},
        json: async () => ({saved: options.body.action === 'save'}),
    }));
    await ui.submit();
    assert.equal(ui.requests[0].url, '/charts/vaccination-trends/favorite');
    assert.equal(ui.requests[0].options.method, 'POST');
    assert.equal(ui.requests[0].options.body.action, 'save');
    assert.equal(ui.attributes['aria-pressed'], 'true');
    assert.equal(ui.label.textContent, 'Saved');
    assert.equal(ui.actionInput.value, 'remove');
    assert.equal(ui.button.disabled, false);
    await ui.submit();
    assert.equal(ui.requests[1].url, '/charts/vaccination-trends/favorite');
    assert.equal(ui.requests[1].options.body.action, 'remove');
    assert.equal(ui.attributes['aria-pressed'], 'false');
    assert.equal(ui.actionInput.value, 'save');
    assert.equal(ui.label.textContent, 'Save chart');
});

test('a failed request preserves the unsaved state and allows retry', async () => {
    const ui = setup(() => ({ok: false, headers: {get: () => 'text/html'}}));
    await ui.submit();
    assert.equal(ui.actionInput.value, 'save');
    assert.equal(ui.label.textContent, 'Save chart');
    assert.equal(ui.button.disabled, false);
    assert.match(ui.status.textContent, /Could not update/);
});

test('CSRF failures show the server recovery message', async () => {
    const ui = setup(() => ({
        ok: false, headers: {get: () => 'application/json'},
        json: async () => ({error: 'This form expired or could not be verified. Reload the page and try again.'}),
    }));
    await ui.submit();
    assert.match(ui.status.textContent, /This form expired/);
    assert.equal(ui.actionInput.value, 'save');
    assert.equal(ui.button.disabled, false);
});
