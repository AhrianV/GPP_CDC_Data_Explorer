document.querySelectorAll('.workspace-action').forEach(form => {
    form.addEventListener('submit', event => {
        if (form.getAttribute('aria-busy') === 'true') {
            event.preventDefault();
            return;
        }
        const file = form.querySelector('input[type="file"]');
        if (file && file.files[0] && file.files[0].size > 5 * 1024 * 1024) {
            event.preventDefault();
            form.querySelector('.action-status').textContent = 'Choose a file of 5 MB or less.';
            return;
        }
        const button = form.querySelector('button[type="submit"]');
        button.dataset.originalText = button.textContent;
        button.textContent = button.dataset.loading;
        button.disabled = true;
        form.setAttribute('aria-busy', 'true');
        form.querySelector('.action-status').textContent = 'This may take up to a minute. Your results will appear here.';
    });
});
window.addEventListener('pageshow', event => {
    if (event.persisted) {
        window.location.reload();
        return;
    }
    document.querySelectorAll('.workspace-action').forEach(form => {
        form.removeAttribute('aria-busy');
        const button = form.querySelector('button[type="submit"]');
        button.disabled = false;
        if (button.dataset.originalText) button.textContent = button.dataset.originalText;
        form.querySelector('.action-status').textContent = '';
    });
});
