document.querySelectorAll('.chart-favorite').forEach(form => {
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const button = form.querySelector('button');
        if (button.disabled) return;
        const status = form.querySelector('.favorite-status');
        button.disabled = true;
        form.setAttribute('aria-busy', 'true');
        status.textContent = '';
        try {
            // The hidden input named "action" shadows the form.action property.
            const response = await fetch(form.getAttribute('action'), {
                method: 'POST', body: new FormData(form), headers: {'Accept': 'application/json'}
            });
            const isJson = response.headers.get('content-type')?.includes('application/json');
            if (!response.ok || !isJson) {
                const error = isJson ? await response.json() : null;
                throw new Error(error?.error || 'Could not update this chart. Reload the page and try again.');
            }
            const {saved} = await response.json();
            form.querySelector('[name="action"]').value = saved ? 'remove' : 'save';
            button.classList.toggle('is-saved', saved);
            button.setAttribute('aria-pressed', String(saved));
            button.setAttribute('aria-label', `${saved ? 'Remove saved chart' : 'Save chart'}: ${form.dataset.chartTitle}`);
            button.querySelector('i').className = `bi ${saved ? 'bi-heart-fill' : 'bi-heart'}`;
            button.querySelector('span').textContent = saved ? 'Saved' : 'Save chart';
            status.textContent = saved ? 'Added to Saved charts on your dashboard.' : 'Removed from Saved charts.';
        } catch (error) {
            status.textContent = error.message || 'Could not update this chart. Reload the page and try again.';
        } finally {
            button.disabled = false;
            form.removeAttribute('aria-busy');
        }
    });
});
// Restore the server's saved state after returning through browser history.
window.addEventListener('pageshow', event => {
    if (event.persisted) window.location.reload();
});
