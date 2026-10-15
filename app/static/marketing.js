/* Scroll reveal for the marketing pages.

   Progressive by design: the hidden starting state (.ts-anim on <html>) is
   only applied once we know IntersectionObserver is available and there is
   something to reveal. If this file never loads, the page simply renders
   normally instead of staying blank. */
(function () {
    var reduce = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !('IntersectionObserver' in window)) return;

    var nodes = Array.prototype.slice.call(document.querySelectorAll('.ts-reveal'));
    if (!nodes.length) return;

    document.documentElement.classList.add('ts-anim');

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('ts-in');
                observer.unobserve(entry.target);
            }
        });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });

    nodes.forEach(function (node) { observer.observe(node); });
})();

/* Sticky mobile call to action.

   Appears once the visitor has scrolled past the top of the page, so the free
   trial is always within reach on a phone. marketing.css hides the bar from
   768px up, and the visitor can dismiss it. */
(function () {
    var bar = document.getElementById('ts-mobile-cta');
    if (!bar) return;

    var dismissed = false;
    var shown = false;

    function update() {
        var y = window.pageYOffset || document.documentElement.scrollTop || 0;
        var next = !dismissed && y > 480;
        if (next !== shown) {
            shown = next;
            bar.classList.toggle('ts-show', shown);
        }
    }

    var close = document.getElementById('ts-mobile-cta-close');
    if (close) {
        close.addEventListener('click', function () {
            dismissed = true;
            update();
        });
    }

    window.addEventListener('scroll', update, { passive: true });
    update();
})();
