// Auto-dismiss flash-style alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.alert-dismissible').forEach(function (el) {
        setTimeout(function () {
            if (el && el.parentNode) {
                el.classList.remove('show');
                setTimeout(function () {
                    el.remove();
                }, 300);
            }
        }, 5000);
    });
});

// Confirm helper — used inline via onclick="return confirm(...)" in templates
window.confirmAction = function (message) {
    return window.confirm(message || 'Are you sure?');
};

// Simple fetch wrapper that logs errors to console
window.api = {
    get: function (url) {
        return fetch(url, { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            });
    }
};
