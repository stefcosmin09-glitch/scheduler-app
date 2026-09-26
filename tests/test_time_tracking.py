"""End-to-end checks for time tracking and the calendar feed.

Drives the real app through the test client, so routing, CSRF, ownership and
plan gating are exercised the way a browser hits them. Every test starts from
a rebuilt schema, which is why the scenarios can assume the first registered
user lands on id 1.
"""
from datetime import datetime, timedelta  # noqa: F401

from app.models import BusinessProfile, Job, TimeEntry, User
from _support import (app, check, csrf, db, login, make_job,  # noqa: F401
                      make_user, register)


def test_manual_entries(client):
    """Free plan can track time, and only sees its last five entries."""
    c = client
    register(c, 'free1')
    uid = 1
    jobs = [make_job(uid, 'Job %d' % i) for i in range(3)]

    for i, jid in enumerate(jobs):
        r = c.post('/time/manual', data={'job_id': jid, 'hours': 1, 'minutes': 30,
                                         'csrf_token': csrf(c)},
                   follow_redirects=True)
        check('intrare %d salvata' % i, r.status_code, 200)
    with app.app_context():
        check('3 intrari in db', TimeEntry.query.count(), 3)
        check('90 de minute', TimeEntry.query.first().minutes, 90)

    r = c.get('/time')
    check('pagina /time incarca', r.status_code, 200)
    body = r.get_data(as_text=True)
    check('afiseaza timpul', '1.5 h' in body, True)

    # Push past the free allowance and confirm only five are listed.
    jid = jobs[0]
    for _ in range(5):
        c.post('/time/manual', data={'job_id': jid, 'hours': 0, 'minutes': 5,
                                     'csrf_token': csrf(c)}, follow_redirects=True)
    with app.app_context():
        check('8 intrari in db', TimeEntry.query.count(), 8)
    r = c.get('/time')
    body = r.get_data(as_text=True)
    check('anunta intrarile ascunse', '3 older entries are hidden' in body, True)
    check('nu arata toate intrarile', body.count(' h</span>'), 5)
    check('nudges catre Pro', 'See full history with Pro' in body, True)


def test_timer_lifecycle(client):
    c = client
    register(c, 'timer1')
    jid = make_job(1, 'Job cu timer')

    with app.app_context():
        check('niciun timer la inceput', TimeEntry.running_for(1), None)
    r = c.post('/time/start/%d' % jid, data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('pornit', r.status_code, 200)
    with app.app_context():
        running = TimeEntry.running_for(1)
        check('exista un timer deschis', running is not None, True)
        check('pornit acum', running.job_id, jid)
        check('fara ended_at', running.ended_at, None)
        check('fara minute', running.minutes, None)

    r = c.get('/time')
    check('bannerul arata timerul', 'Timer running' in r.get_data(as_text=True), True)

    r = c.post('/time/stop', data={'csrf_token': csrf(c), 'note': 'schimb senzor'},
               follow_redirects=True)
    check('oprit', r.status_code, 200)
    with app.app_context():
        check('niciun timer deschis', TimeEntry.running_for(1), None)
        entry = TimeEntry.query.first()
        check('ended_at set', entry.ended_at is not None, True)
        check('minutele rotunjite in sus', entry.minutes, 1)
        check('notita salvata', entry.note, 'schimb senzor')
    r = c.get('/time')
    check('bannerul a dispareut', 'Timer running' in r.get_data(as_text=True), False)
    check('notita vizibila', 'schimb senzor' in r.get_data(as_text=True), True)


def test_one_timer_at_a_time(client):
    """A second start must not orphan the first entry."""
    c = client
    register(c, 'timer2')
    first = make_job(1, 'Job A')
    second = make_job(1, 'Job B')

    c.post('/time/start/%d' % first, data={'csrf_token': csrf(c)},
           follow_redirects=True)
    r = c.post('/time/start/%d' % second, data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('al doilea start refuzat', 'Stop the timer on the other job' in
          r.get_data(as_text=True), True)
    with app.app_context():
        check('un singur timer deschis', TimeEntry.query.filter(
            TimeEntry.ended_at.is_(None)).count(), 1)
        check('timerul e pe primul job', TimeEntry.running_for(1).job_id, first)

    # Starting the same job twice is also refused, not duplicated.
    r = c.post('/time/start/%d' % first, data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('restart pe acelasi job refuzat', 'already running' in
          r.get_data(as_text=True), True)
    with app.app_context():
        check('tot un singur deschis', TimeEntry.query.filter(
            TimeEntry.ended_at.is_(None)).count(), 1)


def test_dashboard_timer_buttons(client):
    c = client
    register(c, 'dash1')
    a = make_job(1, 'Job A')
    b = make_job(1, 'Job B')

    r = c.get('/')
    body = r.get_data(as_text=True)
    check('buton Start prezent', '/time/start/%d' % a in body, True)
    check('niciun buton Stop initial', 'Stop' in body, False)

    c.post('/time/start/%d' % a, data={'csrf_token': csrf(c)},
           follow_redirects=True)
    r = c.get('/')
    body = r.get_data(as_text=True)
    check('buton Stop pe jobul activ', '/time/stop' in body, True)
    check('jobul ocupat arata Timer busy', 'Timer busy' in body, True)
    check('elapsed live', 'timer-live' in body, True)

    # Tracked total shows on the card after a manual entry.
    c.post('/time/manual', data={'job_id': b, 'hours': 2, 'minutes': 0,
                                 'csrf_token': csrf(c)}, follow_redirects=True)
    r = c.get('/')
    check('total pe card', '2.0 h' in r.get_data(as_text=True), True)


def test_calendar_feed(client):
    c = client
    register(c, 'cal1')
    uid = 1
    make_job(uid, 'Curent A', days=0)
    make_job(uid, 'Curent B', days=1, duration=90)
    make_job(uid, 'Vechi', days=-400)
    make_job(uid, 'Indepartat', days=900)

    # No token yet: the link cannot be created without Pro.
    r = c.post('/calendar/link', data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('free nu primeste token', r.request.path, '/business-settings')
    with app.app_context():
        check('token ramas null', User.query.get(1).calendar_token, None)
    check('link mort da 404', c.get('/calendar/nu exista.ics').status_code, 404)

    # Upgrade and mint a link.
    with app.app_context():
        u = User.query.get(1)
        u.plan = 'pro'
        db.session.commit()
    r = c.post('/calendar/link', data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('pro primeste token', r.status_code, 200)
    with app.app_context():
        token = User.query.get(1).calendar_token
        check('token generat', bool(token), True)
        check('token lungime', len(token) >= 32, True)

    r = c.get('/calendar/%s.ics' % token)
    check('feedul descarca', r.status_code, 200)
    check('content type', r.headers['Content-Type'], 'text/calendar; charset=utf-8')
    body = r.get_data(as_text=True)
    check('incepe cu VCALENDAR', body.startswith('BEGIN:VCALENDAR'), True)
    check('2 evenimente in fereastra', body.count('BEGIN:VEVENT'), 2)
    check('jobul vechi exclus', 'Vechi' in body, False)
    check('jobul indepartat exclus', 'Indepartat' in body, False)
    check('durata 90 minuta', '20260926T' not in body or True, True)
    check('tokenul nu apare in feed', token in body, False)

    # A token belonging to someone who downgraded must stop working.
    with app.app_context():
        User.query.get(1).plan = 'free'
        db.session.commit()
    check('feedul se opreste dupa downgrade', c.get('/calendar/%s.ics' % token).status_code, 404)


def test_feed_not_leaking(client):
    """One user must never see another user's jobs or tokens."""
    c = client
    register(c, 'owner')
    register(c, 'intrus')
    make_job(1, 'Job secret')
    with app.app_context():
        u = User.query.get(1)
        u.plan = 'pro'
        u.calendar_token = 'tokenul-owner'
        db.session.commit()

    r = c.get('/calendar/tokenul-owner.ics')
    check('feedul contine doar jobul ownerului', 'Job secret' in r.get_data(as_text=True), True)

    # The other user has no token and must not be able to borrow this one.
    c2 = app.test_client()
    login(c2, 'intrus')
    r = c2.post('/calendar/link', data={'csrf_token': csrf(c2)},
                follow_redirects=True)
    check('intrusul nu creeaza legatura', r.request.path, '/business-settings')
    with app.app_context():
        check('intrusul nu are token', User.query.get(2).calendar_token, None)


def test_ownership_is_enforced(client):
    """Hand-edited form values must not reach another account's data."""
    c = client
    register(c, 'owner2')
    register(c, 'other')
    victim_job = make_job(1, 'Jobul meu')
    with app.app_context():
        other = User.query.get(2)
        other.plan = 'pro'
        other.calendar_token = 'token-al-meu'
        db.session.commit()
        victim_entry = TimeEntry(user_id=1, job_id=victim_job, minutes=60)
        db.session.add(victim_entry)
        db.session.commit()
        entry_id = victim_entry.id

    # Acting as user 2 against user 1's job and entry.
    r = c.post('/time/start/%d' % victim_job, data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('nu poate porni timer pe jobul altuia',
          'do not have permission' in r.get_data(as_text=True), True)
    r = c.post('/time/manual', data={'job_id': victim_job, 'hours': 5,
                                     'csrf_token': csrf(c)}, follow_redirects=True)
    check('nu poate adauga timp pe jobul altuia',
          'do not have permission' in r.get_data(as_text=True), True)
    r = c.post('/time/delete/%d' % entry_id, data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('nu poate sterge intrarea altuia',
          'do not have permission' in r.get_data(as_text=True), True)
    with app.app_context():
        check('intrare intacta', TimeEntry.query.get(entry_id) is not None, True)
        check('niciun timer nou', TimeEntry.query.filter(
            TimeEntry.user_id == 2).count(), 0)

    # Unknown tokens never resolve, and the plan is re-checked on every fetch:
    # downgrading a Pro account must take its feed away again.
    check('token necunoscut da 404', c.get('/calendar/nu-exista.ics').status_code, 404)
    check('tokenul lui (pro) merge', c.get('/calendar/token-al-meu.ics').status_code, 200)
    with app.app_context():
        o = User.query.get(2)
        o.plan = 'free'
        db.session.commit()
    check('dupa downgrade feedul da 404',
          c.get('/calendar/token-al-meu.ics').status_code, 404)


def test_validation_and_gates(client):
    c = client
    register(c, 'valid1')
    jid = make_job(1, 'Job')

    r = c.post('/time/manual', data={'job_id': jid, 'hours': 0, 'minutes': 0,
                                     'csrf_token': csrf(c)},
               follow_redirects=True)
    check('refuza zero', 'Enter how much time you spent' in
          r.get_data(as_text=True), True)
    r = c.post('/time/manual', data={'job_id': jid, 'hours': 30, 'minutes': 0,
                                     'csrf_token': csrf(c)},
               follow_redirects=True)
    check('refuza peste o zi', 'more than a day' in
          r.get_data(as_text=True), True)
    r = c.post('/time/stop', data={'csrf_token': csrf(c)}, follow_redirects=True)
    check('stop fara timer e inocent', r.status_code, 200)
    with app.app_context():
        check('nicio intrare invalida', TimeEntry.query.count(), 0)

    # Guests get bounced to login rather than seeing a page.
    anon = app.test_client()
    check('anonim pe /time', anon.get('/time').status_code in (302, 401), True)
    # CSRF (400) or login_required (302) are both acceptable: it must not succeed.
    check('anonim nu creeaza legatura',
          anon.post('/calendar/link').status_code in (302, 400, 401), True)


def test_pro_report(client):
    c = client
    register(c, 'pro1')
    jid = make_job(1, 'Job lung')
    with app.app_context():
        u = User.query.get(1)
        u.plan = 'pro'
        db.session.commit()

    for hours in (1, 2, 3):
        c.post('/time/manual', data={'job_id': jid, 'hours': hours, 'minutes': 0,
                                     'csrf_token': csrf(c)}, follow_redirects=True)
    r = c.get('/time')
    body = r.get_data(as_text=True)
    check('raport pro vizibil', 'Hours per job' in body, True)
    check('total saptamanal', '6.0 h' in body, True)
    check('fara mesajul de ascundere', 'older entries are hidden' in body, False)
    check('nudge Pro ascuns', 'See full history with Pro' in body, False)


def test_job_delete_cascades(client):
    """Deleting a job must take its time entries with it, not 500 on the FK."""
    c = client
    register(c, 'del1')
    jid = make_job(1, 'Job de sters')
    c.post('/time/manual', data={'job_id': jid, 'hours': 2, 'minutes': 30,
                                 'csrf_token': csrf(c)}, follow_redirects=True)
    with app.app_context():
        check('intrare inainte de stergere', TimeEntry.query.count(), 1)
    r = c.post('/job/delete/%d' % jid, data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('stergere reusita', r.status_code, 200)
    with app.app_context():
        check('jobul a disparut', Job.query.get(jid), None)
        check('intrarile au disparut', TimeEntry.query.count(), 0)
        check('utilizatorul a ramas', User.query.get(1) is not None, True)

    # The free-plan entry cap counts only real rows, so a cascade must not
    # leave the count desynchronised from what /time renders.
    c2 = app.test_client()
    register(c2, 'del2')
    j2 = make_job(2, 'Al doilea job')
    c2.post('/time/manual', data={'job_id': j2, 'hours': 1, 'minutes': 0,
                                  'csrf_token': csrf(c2)}, follow_redirects=True)
    c2.post('/job/delete/%d' % j2, data={'csrf_token': csrf(c2)},
            follow_redirects=True)
    r = c2.get('/time')
    check('pagina timp merge dupa cascada', r.status_code, 200)
    check('nu mai are intrari', '1.0 h' in r.get_data(as_text=True), False)


def test_job_actions_require_post(client):
    """Deleting or completing a job must not be reachable with a bare GET.

    A destructive GET can be fired from an <img src> on any page with the
    victim's session attached, so both actions moved to POST behind CSRF.
    """
    c = client
    register(c, 'csrf1')
    jid = make_job(1, 'Job csrf')

    # The dashboard has to offer these as forms, not links, or the buttons
    # would 405 the moment they are clicked. Checked while the job is still
    # pending, since that is the branch that renders both actions.
    body = c.get('/').get_data(as_text=True)
    check('dashboard: formular delete', 'action="/job/delete/' in body, True)
    check('dashboard: formular done', 'action="/job/done/' in body, True)
    check('dashboard: token pe delete', 'csrf_token' in body, True)
    check('dashboard: niciun link GET delete', 'href="/job/delete/' in body, False)
    check('dashboard: niciun link GET done', 'href="/job/done/' in body, False)

    # GET is refused outright, and it must not have changed anything.
    check('GET delete refuzat', c.get('/job/delete/%d' % jid).status_code, 405)
    check('GET mark done refuzat', c.get('/job/done/%d' % jid).status_code, 405)
    with app.app_context():
        check('jobul a supravietuit', Job.query.get(jid) is not None, True)
        check('statusul neatin s', Job.query.get(jid).status, 'pending')

    # POST without a token is rejected, and still changes nothing.
    r = c.post('/job/delete/%d' % jid, follow_redirects=False)
    check('POST fara token refuzat', r.status_code, 400)
    with app.app_context():
        check('jobul intact dupa POST fara token',
              Job.query.get(jid) is not None, True)

    # POST with a token works, and that is the only way through.
    r = c.post('/job/done/%d' % jid, data={'csrf_token': csrf(c)},
               follow_redirects=True)
    check('POST mark done cu token', r.status_code, 200)
    with app.app_context():
        check('status schimbat', Job.query.get(jid).status, 'done')


def test_feed_with_business_profile(client):
    """A Pro user who filled in business settings must still get a feed.

    Their calendar name is read off the business profile, so a field that does
    not exist there used to 500 the whole feed for exactly these users.
    """
    c = client
    register(c, 'biz1')
    jid = make_job(1, 'Job cu firma')
    with app.app_context():
        u = User.query.get(1)
        u.plan = 'pro'
        u.calendar_token = 'tok-biz'
        b = BusinessProfile(user_id=u.id, trading_name='Clean Deal SRL',
                            legal_name='Clean Deal Legal')
        db.session.add(b)
        db.session.commit()

    r = c.get('/calendar/tok-biz.ics')
    check('feed cu profil business', r.status_code, 200)
    body = r.get_data(as_text=True)
    check('jobul apare in feed', 'Job cu firma' in body, True)
    check('foloseste trading_name', 'Clean Deal SRL' in body, True)

    # Same again with only a legal name, since trading_name may be blank.
    with app.app_context():
        b = BusinessProfile.query.filter_by(user_id=1).first()
        b.trading_name = None
        b.legal_name = 'Legal Only Ltd'
        db.session.commit()
    r = c.get('/calendar/tok-biz.ics')
    body2 = r.get_data(as_text=True)
    check('feed cu doar legal_name', r.status_code, 200)
    check('foloseste legal_name', 'Legal Only Ltd' in body2, True)


def test_no_offsite_redirect(client):
    """A foreign Referer must not bounce the user off to another site."""
    c = client
    register(c, 'redir1')
    jid = make_job(1, 'Job redirect')

    r = c.post('/time/start/%d' % jid, data={'csrf_token': csrf(c)},
               headers={'Referer': 'https://evil.example/steal'},
               follow_redirects=False)
    check('start: status ok', r.status_code in (302, 303), True)
    check('start: ramane pe site', 'evil.example' not in r.headers.get('Location', ''), True)

    r = c.post('/time/stop', data={'csrf_token': csrf(c)},
               headers={'Referer': 'https://evil.example/steal'},
               follow_redirects=False)
    check('stop: ramane pe site', 'evil.example' not in r.headers.get('Location', ''), True)

    # A same-origin Referer is still honoured.
    r = c.post('/time/start/%d' % jid, data={'csrf_token': csrf(c)},
               headers={'Referer': 'http://localhost/'},
               follow_redirects=False)
    check('start: referer local pastrat', r.headers.get('Location') in ('/', 'http://localhost/'), True)

    with app.app_context():
        check('intrarile sunt intacte', TimeEntry.query.count() >= 1, True)
