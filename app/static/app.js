/* TradeScheduler - additive micro-interactions (blue topbar untouched).
   Everything is progressive-enhancement / guarded: if any API/markup is
   missing it silently does nothing. No layout is modified. */
(function () {
    'use strict';

    function ts(fn) { if (document.readyState !== 'loading') { fn(); } else { document.addEventListener('DOMContentLoaded', fn); } }

    function createNode(html) {
        var t = document.createElement('template');
        t.innerHTML = html.trim();
        return t.content.firstChild;
    }

    /* ============ 1) Toasts (from flash, or API) ============ */
    function buildToastStack() {
        var stack = document.getElementById('ts-toast-stack');
        if (stack) { return stack; }
        stack = createNode('<div id="ts-toast-stack" class="ts-toast-stack" aria-live="polite"></div>');
        document.body.appendChild(stack);
        return stack;
    }
    window.tsToast = function (message, type) {
        var stack = buildToastStack();
        var kind = type === 'error' ? 'ts-toast--error' : type === 'success' ? 'ts-toast--success' : '';
        var el = createNode(
            '<div class="ts-toast ' + kind + '" role="status">' +
            '<span class="ts-toast__msg"></span>' +
            '<button type="button" class="ts-toast__close" aria-label="close">&times;</button>' +
            '</div>'
        );
        stack.appendChild(el);
        el.querySelector('.ts-toast__msg').textContent = String(message);
        var t;
        function dismiss() {
            if (!el || !el.parentNode) { return; }
            clearTimeout(t);
            el.classList.add('ts-toast--out');
            setTimeout(function () { if (el.parentNode) { el.parentNode.removeChild(el); } }, 200);
        }
        el.querySelector('.ts-toast__close').addEventListener('click', dismiss);
        t = setTimeout(dismiss, 4800);
    };
    ts(function () {
        var msgs = document.querySelectorAll('[data-flash]');
        for (var i = 0; i < msgs.length; i++) {
            var type = msgs[i].getAttribute('data-flash') || '';
            if (type !== 'error' && type !== 'success' && type !== 'warning') { type = ''; }
            window.tsToast(msgs[i].textContent, type);
        }
        if (msgs.length) {
            var host = document.getElementById('ts-flash-host');
            if (host) { host.style.display = 'none'; }
        }
    });

    /* ============ 2) Confirmation modal (replaces confirm()) ============ */
    var modal = null;
    function ensureModal() {
        if (modal) { return modal; }
        modal = createNode(
            '<div id="ts-modal" class="ts-modal-overlay" aria-hidden="true">' +
            '<div class="ts-modal" role="dialog" aria-modal="true" aria-labelledby="ts-modal-title">' +
            '<h3 id="ts-modal-title" class="ts-modal__title"></h3>' +
            '<p class="ts-modal__body"></p>' +
            '<div class="ts-modal__actions">' +
            '<button type="button" data-role="cancel" class="px-4 py-2 rounded bg-gray-200 text-gray-700 text-sm hover:bg-gray-300"></button>' +
            '<button type="button" data-role="ok" class="px-4 py-2 rounded bg-blue-600 text-white text-sm hover:bg-blue-700"></button>' +
            '</div></div></div>'
        );
        document.body.appendChild(modal);
        return modal;
    }
    function closest(node, sel) {
        while (node) { if (node.matches && node.matches(sel)) { return node; } node = node.parentNode; }
        return null;
    }
    ts(function () {
        document.addEventListener('click', function (e) {
            var trigger = closest(e.target, '[data-confirm]');
            if (!trigger) { return; }
            e.preventDefault();
            e.stopPropagation();
            var text = trigger.getAttribute('data-confirm') || 'Are you sure?';
            var title = trigger.getAttribute('data-confirm-title') || 'Please confirm';
            var okLabel = trigger.getAttribute('data-confirm-ok') || 'Confirm';
            var form = closest(trigger, 'form');
            var isSubmit = /submit|button/i.test((trigger.getAttribute('type') || 'submit'));
            ensureModal();
            modal.querySelector('.ts-modal__title').textContent = title;
            modal.querySelector('.ts-modal__body').textContent = text;
            modal.querySelector('[data-role="ok"]').textContent = okLabel;
            modal.querySelector('[data-role="cancel"]').textContent = 'Cancel';
            modal.setAttribute('aria-hidden', 'false');
            function close() {
                modal.setAttribute('aria-hidden', 'true');
                modal.querySelector('[data-role="ok"]').onclick = null;
                modal.querySelector('[data-role="cancel"]').onclick = null;
            }
            modal.querySelector('[data-role="cancel"]').onclick = close;
            modal.querySelector('[data-role="ok"]').onclick = function () {
                close();
                if (form) { form.submit(); }
                else if (trigger.href) { window.location.href = trigger.href; }
            };
        });
    });

    /* ============ 3) Count-up numbers ============ */
    ts(function () {
        var items = document.querySelectorAll('[data-count]');
        if (!items.length || !('IntersectionObserver' in window)) { return; }
        function animate(el, target) {
            var dur = 650;
            var start = null;
            function step(tsn) {
                if (start === null) { start = tsn; }
                var p = Math.min((tsn - start) / dur, 1);
                var eased = 1 - Math.pow(1 - p, 3);
                var val = eased * target;
                var dec = parseInt(el.getAttribute('data-decimals') || '0', 10);
                el.textContent = val.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
                if (p < 1) { window.requestAnimationFrame(step); }
                else { el.textContent = target.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec }); }
            }
            window.requestAnimationFrame(step);
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) {
                    var el = en.target;
                    animate(el, parseFloat(el.getAttribute('data-count')) || 0);
                    io.unobserve(el);
                }
            });
        }, { threshold: 0.4 });
        for (var i = 0; i < items.length; i++) { io.observe(items[i]); }
    });

    /* ============ 4) Reveal on scroll ============ */
    ts(function () {
        var els = document.querySelectorAll('[data-reveal]');
        if (!els.length || !('IntersectionObserver' in window)) { return; }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) {
                    en.target.classList.add('ts-reveal--in');
                    io.unobserve(en.target);
                }
            });
        }, { threshold: 0.12 });
        for (var i = 0; i < els.length; i++) { els[i].classList.add('ts-reveal'); io.observe(els[i]); }
    });
})();
