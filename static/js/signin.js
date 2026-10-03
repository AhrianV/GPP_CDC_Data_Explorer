document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("signin-form");
    const identifierInput = document.getElementById("identifier");
    const rememberInput = document.getElementById("remember");
    const storageKey = "cdcDataExplorer.rememberedIdentifier";

    if (!form || !identifierInput || !rememberInput) {
        return;
    }

    try {
        const savedIdentifier = localStorage.getItem(storageKey);
        if (savedIdentifier) {
            identifierInput.value = savedIdentifier;
            rememberInput.checked = true;
        }

        rememberInput.addEventListener("change", () => {
            if (!rememberInput.checked) {
                localStorage.removeItem(storageKey);
            }
        });

        form.addEventListener("submit", () => {
            if (rememberInput.checked) {
                localStorage.setItem(storageKey, identifierInput.value.trim());
            } else {
                localStorage.removeItem(storageKey);
            }
        });
    } catch (error) {
        // Sign-in should continue to work if browser storage is unavailable.
    }
});
