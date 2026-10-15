"""Every class a template uses must exist somewhere in the stylesheets.

app/static/tailwind.css is a *prebuilt, purged* Tailwind 2.2.19 file: it only
contains the utilities that were in use when it was generated, and Node is not
installed here so it cannot be regenerated. A class that looks perfectly valid
can therefore be a silent no-op. That is exactly how a responsive row written
with sm:flex-col / sm:items-start / sm:ml-4 / sm:gap-0 would quietly do nothing
while looking correct in the template.

This test fails when a template starts using a class no stylesheet defines, so
the fix is to shim it in app.css (as the ts-* classes do) instead of assuming
it is there.

KNOWN_MISSING lists classes that were already unresolved before this test
existed. They are a separate, pre-existing styling gap (the amber and emerald
shades never made it into the purged build; the rest are hooks for JS or for
markup that is not styled yet) and fixing them is not this test's job. The
assertion is a subset check, so removing them from the allow-list can only ever
make it stricter.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = [os.path.join(ROOT, 'app', 'templates', name)
             for name in ('dashboard.html', 'base.html')]
STYLESHEETS = [os.path.join(ROOT, 'app', 'static', name)
               for name in ('tailwind.css', 'app.css', 'marketing.css')]

KNOWN_MISSING = {
    'bg-amber-50', 'border-amber-200', 'text-amber-900',
    'bg-emerald-600', 'hover:bg-emerald-700',
    'scroll-mt-4', 'timer-live',
    'group', 'install-btn', 'ts-scroll-top', 'ts-toast-stack',
}


def stylesheets():
    text = []
    for path in STYLESHEETS:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text.append(handle.read())
    return '\n'.join(text)


def is_defined(css, token):
    """True when the CSS holds a rule whose selector is exactly this class.

    Tailwind escapes variants, so sm:flex-col appears as .sm\\:flex-col, and the
    trailing boundary stops .grid-cols-1 being satisfied by .grid-cols-10.
    """
    escaped = re.sub(r'([:./\[\]!%#(),])', r'\\\1', token)
    return re.search(r'\.' + re.escape(escaped) + r'(?![\w-])', css) is not None


def classes_used(path):
    with open(path, encoding='utf-8') as handle:
        html = handle.read()
    used = set()
    for attr in re.findall(r'class="([^"]*)"', html):
        # Drop the template expressions, keep the literal class names around them.
        attr = re.sub(r'\{[%{].*?[%}]\}', ' ', attr)
        for token in attr.split():
            if re.search(r'[<>{}"\'=&]', token):
                continue
            used.add(token)
    return used


def test_no_template_class_is_missing_from_the_stylesheets():
    css = stylesheets()
    unresolved = set()
    for path in TEMPLATES:
        for token in classes_used(path):
            if not is_defined(css, token):
                unresolved.add(token)
    new = sorted(unresolved - KNOWN_MISSING)
    assert not new, (
        'these classes are not defined by tailwind.css (a purged build), '
        'app.css or marketing.css, so they do nothing: %s' % new)
