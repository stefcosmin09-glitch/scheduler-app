"""Checks for the iCalendar feed.

The failure mode here is silent: a feed that is 99% right shows up as a
calendar that quietly refuses to sync, so these assert the RFC 5545 details
rather than just "it produced a string".
"""
from datetime import datetime

from app.ics import (DEFAULT_DURATION, build_feed, escape_text, fold,
                     format_utc, format_wall, jobs_in_window)

STAMP = datetime(2026, 9, 26, 9, 0, 0)


def unfold(text):
    """Undo RFC 5545 folding the way a client would."""
    return text.replace('\r\n ', '').replace('\r\n', '\n')


class FakeJob:
    """Stands in for the model so the generator can be tested on its own."""

    def __init__(self, id=1, client_name='Client', address='Adresa',
                 date=None, description=None, activity_type='other',
                 status='pending', duration_minutes=60):
        self.id = id
        self.client_name = client_name
        self.address = address
        self.date = date or datetime(2026, 9, 26, 10, 0, 0)
        self.description = description
        self.activity_type = activity_type
        self.status = status
        self.duration_minutes = duration_minutes


def test_escaping():
    assert escape_text('a\\b') == 'a\\\\b', 'backslashes'
    assert escape_text('a;b') == 'a\\;b', 'semicolons'
    assert escape_text('a,b') == 'a\\,b', 'commas'
    assert escape_text('a\\;b') == 'a\\\\\\;b', 'backslash before semicolon'
    assert escape_text('a\nb') == 'a\\nb', 'newlines'
    assert escape_text('a\r\nb') == 'a\\nb', 'crlf'
    assert escape_text(None) == '', 'None'
    assert escape_text('Șos. Ștefan cel Mare') == 'Șos. Ștefan cel Mare', 'diacritics'


def test_folding():
    short = 'SUMMARY:short'
    assert fold(short) == short, 'short line stays put'

    folded = fold('SUMMARY:' + 'x' * 200)
    assert len(folded.split('\r\n')[0].encode('utf-8')) == 75, 'first line is 75 octets'
    assert all(p.startswith(' ') for p in folded.split('\r\n')[1:]), 'continuations start with a space'
    assert all(len(p.encode('utf-8')) <= 75 for p in folded.split('\r\n')), 'no line over 75 octets'
    assert unfold(folded) == 'SUMMARY:' + 'x' * 200, 'unfolds to the original'


def test_folding_diacritics():
    """Romanian letters are two bytes in UTF-8.

    A character-count fold would cut one in half and produce mojibake or a
    decode error on the client, so the limit is counted in octets.
    """
    text = 'SUMMARY:' + 'Șos. Ștefan ' * 12
    folded = fold(text)
    assert all(len(p.encode('utf-8')) <= 75 for p in folded.split('\r\n')), \
        'no line over 75 octets'
    assert unfold(folded) == text, 'round-trips without mangling'


def test_formats():
    assert format_utc(datetime(2026, 9, 26, 14, 5, 9)) == '20260926T140509Z', 'UTC'
    assert format_wall(datetime(2026, 9, 26, 14, 5, 9)) == '20260926T140509', 'floating'
    assert 'TZID' not in format_wall(datetime(2026, 9, 26, 14, 5, 9)), 'no TZID'


def test_feed_structure():
    feed = build_feed(
        [FakeJob(id=7, client_name='Popescu; Ion, Jr.\\X',
                 address='Strada Ștefan cel Mare, nr. 5',
                 description='Linia 1\nLinia 2',
                 activity_type='plumbing')],
        ' firma SRL', stamp=STAMP)

    assert feed.startswith('BEGIN:VCALENDAR\r\n'), 'opens with BEGIN:VCALENDAR'
    assert feed.rstrip('\r\n').endswith('END:VCALENDAR'), 'closes with END:VCALENDAR'
    assert 'VERSION:2.0\r\n' in feed, 'version 2.0'
    assert 'PRODID:-//TradeScheduler//' in feed, 'prodid'
    assert feed.count('BEGIN:VEVENT') == 1, 'one event'
    assert 'REFRESH-INTERVAL;VALUE=DURATION:PT1H\r\n' in feed, 'refresh interval'
    assert 'UID:job-7@tradescheduler\r\n' in feed, 'stable uid'
    assert 'STATUS:TENTATIVE\r\n' in feed, 'pending is tentative'


def test_feed_uses_floating_local_time():
    """The whole point: a Z on DTSTART shifts every event by the reader's offset.

    A 10:00 job would land at 13:00 for a reader in Romania.
    """
    feed = build_feed([FakeJob(id=7)], 'x', stamp=STAMP)
    assert 'DTSTART:20260926T100000\r\n' in feed, 'floating DTSTART'
    assert 'DTEND:20260926T110000\r\n' in feed, 'floating DTEND'
    assert 'DTSTAMP:20260926T090000Z\r\n' in feed, 'DTSTAMP is UTC'
    assert 'DTSTART:20260926T100000Z' not in feed, 'no Z on DTSTART'
    assert 'DTEND:20260926T110000Z' not in feed, 'no Z on DTEND'


def test_feed_escaping():
    feed = build_feed(
        [FakeJob(id=7, client_name='Popescu; Ion, Jr.\\X',
                 address='Strada Ștefan cel Mare, nr. 5',
                 description='Linia 1\nLinia 2',
                 activity_type='plumbing')],
        ' firma SRL', stamp=STAMP)
    flat = unfold(feed)

    assert 'LOCATION:Strada Ștefan cel Mare\\, nr. 5' in flat, 'location escaped'
    assert 'Popescu\\; Ion\\, Jr.\\\\X' in flat, 'name escaped'
    assert 'Linia 1\\nLinia 2' in flat, 'description escaped'
    assert 'SUMMARY:Job: Popescu\\; Ion\\, Jr.\\\\X (plumbing)' in flat, 'activity in summary'


def test_feed_line_endings():
    feed = build_feed([FakeJob(id=7, client_name='x' * 300)], 'x', stamp=STAMP)
    assert feed.replace('\r\n', '').count('\n') == 0, 'CRLF only, no bare LF'
    assert all(len(p.encode('utf-8')) <= 75 for p in feed.split('\r\n') if p), \
        'every line within the octet limit'


def test_feed_is_deterministic():
    """Same job twice must give the same UID, or clients duplicate it."""
    args = (dict(id=7, client_name='Popescu; Ion, Jr.\\X',
                 address='Strada Ștefan cel Mare, nr. 5',
                 description='Linia 1\nLinia 2',
                 activity_type='plumbing'),)
    first = build_feed([FakeJob(**args[0])], ' firma SRL', stamp=STAMP)
    second = build_feed([FakeJob(**args[0])], ' firma SRL', stamp=STAMP)
    assert first == second, 'identical input gives an identical feed'


def test_durations():
    def end_for(minutes):
        return build_feed([FakeJob(duration_minutes=minutes)], 'x', stamp=STAMP)

    assert 'DTEND:20260926T110000\r\n' in end_for(0), 'zero falls back to the default'
    assert 'DTEND:20260926T110000\r\n' in end_for(None), 'None falls back to the default'
    assert 'DTEND:20260926T113000\r\n' in end_for(90), 'ninety minutes'
    assert DEFAULT_DURATION == 60, 'default is an hour'


def test_completed_job_is_confirmed():
    feed = build_feed([FakeJob(status='done')], 'x', stamp=STAMP)
    assert 'STATUS:CONFIRMED\r\n' in feed, 'done is confirmed'


def test_window_keeps_the_relevant_soon():
    now = datetime(2026, 9, 26, 12, 0, 0)
    jobs = [
        FakeJob(id=1, date=datetime(2020, 1, 1, 9, 0)),
        FakeJob(id=2, date=datetime(2026, 9, 25, 9, 0)),
        FakeJob(id=3, date=datetime(2027, 3, 1, 9, 0)),
        FakeJob(id=4, date=datetime(2035, 1, 1, 9, 0)),
    ]
    kept = [j.id for j in jobs_in_window(jobs, now=now)]
    assert 1 not in kept, 'long-past excluded'
    assert 2 in kept, 'recent past kept'
    assert 3 in kept, 'near future kept'
    assert 4 not in kept, 'far future excluded'
