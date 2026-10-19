"""Вспомогательные декораторы ролевой модели доступа (RBAC, ТЗ п.4.1.5)."""
from functools import wraps

from flask import abort
from flask_login import current_user
from sqlalchemy import false

from app.constants import ROLE_SUPERADMIN, STAFF_ROLES


def roles_required(*roles):
    """Ограничивает доступ к view только указанными ролями сотрудников.

    Fail-closed: сотрудник (кроме суперадмина) без назначенного филиала не получает доступа
    ни к одной служебной странице — иначе фильтры «по своему филиалу» превратились бы в
    «без фильтра» и он увидел бы данные всей сети.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            if (current_user.role in STAFF_ROLES and current_user.role != ROLE_SUPERADMIN
                    and not current_user.branch_id):
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def staff_required(view_func):
    return roles_required(*STAFF_ROLES)(view_func)


def branch_scoped_query(query, branch_column):
    """Ограничивает queryset филиалом текущего пользователя (суперадмин видит всё).

    Fail-closed: для не-суперадмина без филиала (и для анонима) возвращается пустая выборка.
    """
    if not current_user.is_authenticated:
        return query.filter(false())
    if current_user.role == ROLE_SUPERADMIN:
        return query
    if not current_user.branch_id:
        return query.filter(false())
    return query.filter(branch_column == current_user.branch_id)
