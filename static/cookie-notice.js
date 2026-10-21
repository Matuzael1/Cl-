(() => {
    const notice = document.querySelector('#cookie-notice');
    const dismissButton = document.querySelector('#cookie-notice-dismiss');
    if (!notice || !dismissButton) return;

    try {
        if (window.sessionStorage.getItem('bw-cookie-notice-dismissed') === '1') return;
    } catch {
        // Storage may be disabled; the notice can still be dismissed for this page.
    }

    notice.hidden = false;
    dismissButton.addEventListener('click', () => {
        notice.hidden = true;
        try {
            window.sessionStorage.setItem('bw-cookie-notice-dismissed', '1');
        } catch {
            // Keep the dismissal for the current page when storage is unavailable.
        }
    });
})();