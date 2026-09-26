"""iCalendar feed for a user's jobs.

Hand-rolled rather than pulled from a library, because a calendar feed is the
sort of thing that only shows up as broken once a phone refuses to parse it.
The parts of RFC 5545 that actually bite:

  * Lines are separated by CRLF, never a bare LF.
  * Lines longer than 75 *octets* are folded, with continuations starting with a
    single space. Bytes, not characters: Romanian names carry 2-byte letters, so
    folding on character count produces invalid UTF-8 halfway through a name.
  * TEXT values escape backslash, semicolon and comma, and turn newlines into
    a literal \n.
  * DTSTART/DTEND are floating local times, with neither a trailing Z nor a
    TZID. Job times come from a datetime-local form field, so the stored value
    is the wall-clock time the user typed rather than an instant; stamping it
    as UTC would shift every event by the reader's offset. DTSTAMP stays UTC
    because RFC 5545 requires it. No VTIMEZONE is needed for floating times.

A consequence worth knowing: a job set for 10:00 shows at 10:00 in the
reader's timezone, so it moves if they travel far enough. For one tradesperson
reading their own job list that is the behaviour you want, and it avoids
storing a timezone we would then have to ask everyone to set.
"""
from datetime import datetime, timedelta

PRODID = '-//TradeScheduler//Job calendar//EN'
LINE_LIMIT = 75
DEFAULT_DURATION = 60
HISTORY_DAYS = 30
FUTURE_DAYS = 365


def escape_text(value):
    """Escape a value for an iCalendar TEXT property."""
    if value is None:
        return ''
    out = str(value)
    out = out.replace('\\', '\\\\')
    out = out.replace(';', '\\;')
    out = out.replace(',', '\\,')
    out = out.replace('\r\n', '\\n').replace('\r', '\\n').replace('\n', '\\n')
    return out


def fold(line):
    """Fold one content line to LINE_LIMIT octets, continuations start with a space."""
    lines = []
    current = ''
    used = 0
    budget = LINE_LIMIT
    for char in line:
        size = len(char.encode('utf-8'))
        if used + size > budget:
            lines.append(current)
            current = char
            used = size
            # A continuation line spends one octet on the leading space.
            budget = LINE_LIMIT - 1
        else:
            current += char
            used += size
    lines.append(current)
    return '\r\n'.join([lines[0]] + [' ' + part for part in lines[1:]])


def format_utc(value):
    """RFC 5545 UTC form. Only valid where the spec demands UTC, i.e. DTSTAMP."""
    return value.strftime('%Y%m%dT%H%M%SZ')


def format_wall(value):
    """Floating local form: no trailing Z and no TZID.

    Job times come from a datetime-local input, so what is stored is the
    wall-clock time the user typed, not an instant. Labelling it with a Z
    would claim it is UTC and every client would shift it by its own offset,
    putting a 10:00 job at 13:00 for anyone east of Greenwich. Floating time
    is read in the viewer's own timezone instead, so the event lands at the
    hour that was typed.
    """
    return value.strftime('%Y%m%dT%H%M%S')


def event_lines(job, stamp):
    start = job.date
    minutes = job.duration_minutes or DEFAULT_DURATION
    if minutes <= 0:
        minutes = DEFAULT_DURATION
    end = start + timedelta(minutes=minutes)

    summary = 'Job: %s' % (job.client_name or 'Untitled')
    activity = getattr(job, 'activity_type', None)
    if activity and activity != 'other':
        summary = '%s (%s)' % (summary, activity)

    lines = [
        'BEGIN:VEVENT',
        # Stable across edits so a client updates the existing event instead of
        # duplicating it on every refresh.
        'UID:job-%d@tradescheduler' % job.id,
        # DTSTAMP has to be UTC per the spec, but DTSTART/DTEND are floating:
        # see format_wall for why the job time is not an instant.
        'DTSTAMP:%s' % format_utc(stamp),
        'DTSTART:%s' % format_wall(start),
        'DTEND:%s' % format_wall(end),
        'SUMMARY:%s' % escape_text(summary),
    ]
    if job.address:
        lines.append('LOCATION:%s' % escape_text(job.address))
    if job.client_name:
        description = 'Client: %s' % job.client_name
        if job.description:
            description += '\n%s' % job.description
        lines.append('DESCRIPTION:%s' % escape_text(description))
    if job.status:
        lines.append('STATUS:%s' % ('CONFIRMED' if job.status == 'done'
                                    else 'TENTATIVE'))
    lines.append('END:VEVENT')
    return lines


def build_feed(jobs, calendar_name, stamp=None):
    """Render a complete VCALENDAR for the given jobs."""
    stamp = stamp or datetime.utcnow()
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:%s' % PRODID,
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:%s' % escape_text(calendar_name or 'TradeScheduler Jobs'),
        'X-WR-CALDESC:%s' % escape_text(
            'Your TradeScheduler jobs. Refreshes automatically.'),
        # Without these, most clients poll once a day and a rescheduled job
        # shows up stale for a whole day.
        'REFRESH-INTERVAL;VALUE=DURATION:PT1H',
        'X-PUBLISHED-TTL:PT1H',
    ]
    for job in jobs:
        lines.extend(event_lines(job, stamp))
    lines.append('END:VCALENDAR')
    return ''.join(fold(line) + '\r\n' for line in lines)


def jobs_in_window(jobs, now=None):
    """Keep recent history and the near future, drop the distant past.

    A subscription is refetched forever, so sending every job since signup
    would grow without limit for no benefit.
    """
    now = now or datetime.utcnow()
    start = now - timedelta(days=HISTORY_DAYS)
    end = now + timedelta(days=FUTURE_DAYS)
    return [job for job in jobs if job.date and start <= job.date <= end]
