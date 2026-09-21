/* TradeScheduler — micro-interactions (v2) */
(function () {
    'use strict';

    function el(tag, className, html) {
        var e = document.createElement(tag);
        if (className) e.className = className;
        if (html !== undefined) e.innerHTML = html;
        return e;
    }

    /* ---------- Toasts ---------- */
    var toastStack = document.getElementById('toast-stack');
    if (!toastStack) {
        toastStack = el('div', '');
        toastStack.id = 'toast-stack';
        document.body.appendChild(toastStack);
    }
    function showToast(text) {
        var t = el('div', 'toast fade-in');
        var span = el('span', '', '');
        span.textContent = text;
        var close = el('button', 't-close', '&times;');
        close.setAttribute('aria-label', 'Close');
        t.appendChild(span);
        t.appendChild(close);
        toastStack.appendChild(t);
        function remove() {
            t.classList.add('out');
            setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 220);
        }
        close.addEventListener('click', remove);
        setTimeout(remove, 5000);
    }
    window.showToast = showToast;
    Array.prototype.slice.call(document.querySelectorAll('.flash-item')).forEach(function (item) {
        showToast(item.getAttribute('data-message') || item.textContent.trim());
        item.parentNode.removeChild(item);
    });

    /* ---------- Confirm modal ---------- */
    var confirmOk = null;
    var modalOverlay = el('div', 'modal-overlay');
    modalOverlay.innerHTML =
        '<div class="modal" role="alertdialog" aria-modal="true">' +
        '<p class="page-title mb-1" style="font-size:1.05rem;" data-confirm-title>Are you sure?</p>' +
        '<p class="text-sm text-gray-500" data-confirm-body></p>' +
        '<div class="mt-5 flex gap-3">' +
        '<button type="button" class="btn btn-primary flex-1" data-confirm-ok>Confirm</button>' +
        '<button type="button" class="btn btn-ghost flex-1" data-confirm-cancel>Cancel</button>' +
        '</div></div>';
    document.body.appendChild(modalOverlay);
    var mTitle = modalOverlay.querySelector('[data-confirm-title]');
    var mBody = modalOverlay.querySelector('[data-confirm-body]');
    var mOk = modalOverlay.querySelector('[data-confirm-ok]');
    var mCancel = modalOverlay.querySelector('[data-confirm-cancel]');

    function closeModal() {
        modalOverlay.classList.remove('open');
        confirmOk = null;
    }
    function openConfirm(message, okLabel, cancelLabel) {
        if (message) mBody.textContent = message;
        if (okLabel) mOk.textContent = okLabel;
        if (cancelLabel) mCancel.textContent = cancelLabel;
        modalOverlay.classList.add('open');
    }
    mOk.addEventListener('click', function () {
        closeModal();
        if (confirmOk) confirmOk();
    });
    mCancel.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', function (e) {
        if (e.target === modalOverlay) closeModal();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modalOverlay.classList.contains('open')) closeModal();
    });
    function handleConfirm(formOrLink, event) {
        var message = formOrLink.getAttribute('data-confirm');
        var ok = formOrLink.getAttribute('data-confirm-ok');
        var cancel = formOrLink.getAttribute('data-confirm-cancel');
        event.preventDefault();
        confirmOk = function () {
            if (formOrLink.tagName === 'FORM') {
                formOrLink.submit();
            } else {
                var href = formOrLink.getAttribute('href');
                if (href) window.location.href = href;
                else formOrLink.click();
            }
        };
        openConfirm(message, ok, cancel);
    }
    document.addEventListener('click', function (e) {
        var t = e.target.closest ? e.target.closest('[data-confirm]') : null;
        if (t && t.tagName !== 'FORM') handleConfirm(t, e);
    }, true);
    document.addEventListener('submit', function (e) {
        var f = e.target;
        if (f && f.tagName === 'FORM' && f.getAttribute('data-confirm')) {
            handleConfirm(f, e);
        }
    }, true);

    /* ---------- Fade on scroll ---------- */
    var things = Array.prototype.slice.call(document.querySelectorAll('[data-fade]'));
    function reveal() {
        things.forEach(function (n) { n.classList.add('in-view'); });
        things = [];
    }
    if ('IntersectionObserver' in window && things.length) {
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) {
                    var n = en.target;
                    var d = parseInt(n.getAttribute('data-delay') || '0', 10);
                    setTimeout(function () { n.classList.add('in-view'); }, d);
                    io.unobserve(n);
                }
            });
        }, { threshold: 0.12 });
        things.forEach(function (n) { io.observe(n); });
    } else {
        reveal();
    }

    /* ---------- Count up ---------- */
    function animateCount(node) {
        var target = parseFloat(node.getAttribute('data-count'));
        if (isNaN(target)) return;
        var prefix = node.getAttribute('data-prefix') || '';
        var decimals = parseInt(node.getAttribute('data-decimals') || '0', 10);
        var dur = 900, start = null;
        function fmt(v) { return prefix + v.toFixed(decimals); }
        node.textContent = fmt(0);
        function step(ts) {
            if (!start) start = ts;
            var p = Math.min((ts - start) / dur, 1);
            var eased = 1 - Math.pow(1 - p, 3);
            node.textContent = fmt(target * eased);
            if (p < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }
    var counters = Array.prototype.slice.call(document.querySelectorAll('[data-count]'));
    if ('IntersectionObserver' in window && counters.length) {
        var cio = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) {
                    animateCount(en.target);
                    cio.unobserve(en.target);
                }
            });
        }, { threshold: 0.4 });
        counters.forEach(function (n) { cio.observe(n); });
    } else {
        counters.forEach(function (n) {
            var prefix = n.getAttribute('data-prefix') || '';
            n.textContent = prefix + n.getAttribute('data-count');
        });
    }

    /* ---------- Tabs ---------- */
    Array.prototype.slice.call(document.querySelectorAll('[data-tabs]')).forEach(function (wrap) {
        var btns = Array.prototype.slice.call(wrap.querySelectorAll('[data-tab-btn]'));
        var panels = Array.prototype.slice.call(document.querySelectorAll('[data-tab-panel]'));
        function sync(name) {
            btns.forEach(function (b) {
                var active = b.getAttribute('data-tab-btn') === name;
                b.classList.toggle('tab-active', active);
                b.classList.toggle('bg-gray-100', active);
                b.classList.toggle('text-gray-900', active);
                b.classList.toggle('bg-white', !active);
            });
            panels.forEach(function (p) {
                var is = p.getAttribute('data-tab-panel') === name;
                p.style.display = is ? '' : 'none';
                p.classList.toggle('hidden', !is);
            });
        }
        btns.forEach(function (b) {
            b.addEventListener('click', function () { sync(b.getAttribute('data-tab-btn')); });
        });
        var first = btns[0];
        if (first) sync(first.getAttribute('data-tab-btn'));
    });

    /* ---------- Live filter ---------- */
    function initFilter(list) {
        var input = list.querySelector('[data-filter-input]') ||
            document.querySelector('[data-filter-input="' + (list.getAttribute('data-filter-list') || '') + '"]');
        if (!input) return;
        var rows = Array.prototype.slice.call(list.querySelectorAll('[data-filter-row]'));
        var empty = list.querySelector('[data-filter-empty]');
        if (!rows.length) return;
        input.addEventListener('input', function () {
            var q = (input.value || '').toLowerCase().trim();
            var shown = 0;
            rows.forEach(function (r) {
                var hay = (r.getAttribute('data-search') || r.textContent).toLowerCase();
                var vis = q === '' || hay.indexOf(q) !== -1;
                r.style.display = vis ? '' : 'none';
                if (vis) shown++;
            });
            if (empty) empty.style.display = shown === 0 ? '' : 'none';
        });
    }
    Array.prototype.slice.call(document.querySelectorAll('[data-filter-list]')).forEach(initFilter);

    /* ---------- Collapse ---------- */
    Array.prototype.slice.call(document.querySelectorAll('[data-collapse-toggle]')).forEach(function (btn) {
        var target = document.querySelector(btn.getAttribute('data-collapse-target'));
        if (!target) return;
        function doToggle() {
            var open = target.getAttribute('hidden') !== null && target.getAttribute('hidden') !== 'false';
            if (btn.classList.contains('expanded')) {
                target.setAttribute('hidden', '');
                btn.classList.remove('expanded');
            } else {
                target.removeAttribute('hidden');
                btn.classList.add('expanded');
            }
            var caret = btn.querySelector('.caret');
            if (caret) caret.style.transform = (open ? '' : 'rotate(180deg)');
        }
        btn.addEventListener('click', doToggle);
    });

    /* ---------- Form loading states ---------- */
    document.addEventListener('submit', function (e) {
        var f = e.target;
        if (!f || f.tagName !== 'FORM') return;
        if (f.getAttribute('data-confirm')) return;
        if (f.getAttribute('data-loading') === 'false') return;
        var submits = Array.prototype.slice.call(f.querySelectorAll('[type="submit"]'));
        submits.forEach(function (s) {
            if (s.disabled) return;
            s.disabled = true;
            s.classList.add('is-loading');
            var sp = el('span', 'spinner');
            sp.setAttribute('aria-hidden', 'true');
            s.insertBefore(sp, s.firstChild);
        });
    });

    /* ---------- Mobile drawer ---------- */
    var toggle = document.getElementById('menu-toggle');
    var drawer = document.getElementById('mobile-drawer');
    var overlay = document.getElementById('drawer-overlay');
    if (toggle && drawer) {
        var closeDrawer = function () {
            drawer.style.transform = 'translateX(-100%)';
            if (overlay) overlay.classList.add('hidden');
        };
        toggle.addEventListener('click', function () {
            drawer.style.transform = 'translateX(0)';
            if (overlay) overlay.classList.remove('hidden');
        });
        if (overlay) overlay.addEventListener('click', closeDrawer);
        Array.prototype.slice.call(drawer.querySelectorAll('a,button')).forEach(function (n) {
            n.addEventListener('click', function () {
                setTimeout(closeDrawer, 80);
            });
        });
    }

    /* ---------- Password visibility toggle ---------- */
    Array.prototype.slice.call(document.querySelectorAll('[data-pw-toggle]')).forEach(function (btn) {
        var input = document.getElementById(btn.getAttribute('data-pw-toggle'));
        if (!input) return;
        btn.addEventListener('click', function () {
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.textContent = show ? btn.getAttribute('data-hide') || 'Hide' : btn.getAttribute('data-show') || 'Show';
        });
    });
})();