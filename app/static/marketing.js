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
