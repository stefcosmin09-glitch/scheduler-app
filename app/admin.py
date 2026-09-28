"""The owner-only view over the user list.

Every route here is behind login_required and is_admin, and the decorator sits
in this file rather than being applied per route so that a new route added later
cannot forget it. is_admin is false for every account by default and is never
written by any request, so there is no sign-up, no login, and no form that can
set it: turning it on is a deliberate edit in the database.

Read-only on purpose. The question this answers is "has anybody signed up, and
who", and nothing here can change a row. A page that can delete a customer is a
page that eventually will, usually by accident, and there is no feature on this
side of the app that needs it.
"""
from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.models import User

admin = Blueprint('admin', __name__)

# Big enough to see a spike without paging, small enough that the query stays a
# single index scan once the search box is empty.
PER_PAGE = 50


def _wants_admin():
    return bool(getattr(current_user, 'is_admin', False))


def admin_required(view):
    """Login, then permission.

    Ordered so an anonymous visitor is bounced to the login page rather than
    told that /admin exists. login_required runs first, which is also why
    current_user is safe to read here.
    """

    @login_required
    @_require_admin
    def wrapped(*args, **kwargs):
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


def _require_admin(view):
    def wrapped(*args, **kwargs):
        if not _wants_admin():
            # 404 rather than 403: there is nothing to gain from confirming that
            # an admin area exists to someone who cannot use it.
            abort(404)
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


@admin.route('/admin/users')
@admin_required
def users():
    """Everyone who has an account, newest first, with a search box."""
    search = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1

    query = User.query
    if search:
        # ilike, not like, and both sides: people type the beginning of the
        # address more often than the middle, and an email search that misses
        # the start of the string is worse than no search.
        pattern = '%%%s%%' % search
        query = query.filter(or_(User.email.ilike(pattern),
                                 User.username.ilike(pattern)))
    query = query.order_by(User.created_at.desc().nullslast(),
                           User.id.desc())

    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)
    total = User.query.count()

    return render_template(
        'admin_users.html',
        pagination=pagination,
        users=pagination.items,
        search=search,
        total=total,
        matched=len(pagination.items) if search else 0)


@admin.route('/admin/users/<int:user_id>')
@admin_required
def user_detail(user_id):
    """One account, with enough history to recognise it."""
    account = db.session.get(User, user_id)
    if account is None:
        abort(404)
    return render_template('admin_user.html', account=account)
