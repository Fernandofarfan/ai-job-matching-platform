"""Ciclo de vida de las cuentas: resumen semanal, actividad, aviso por inactividad y borrado."""
import os
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

import accounts
from accounts import User


def set_weekly_digest(user_id: int, enabled: bool) -> None:
    """Prende o apaga el resumen semanal por email de la cuenta."""
    with accounts._sessions()() as session:
        user = session.get(User, user_id)
        if user is not None:
            user.weekly_digest_off_at = None if enabled else datetime.now()
            session.commit()


def claim_weekly_digest(user_id: int, previous: Optional[datetime], when: datetime) -> bool:
    """Toma el resumen de la cuenta: anota `when` solo si el último envío sigue siendo `previous`.
    Si dos ejecuciones se pisan, solo una gana y manda el email."""
    last = User.weekly_digest_sent_at
    with accounts._sessions()() as session:
        result = session.execute(update(User).where(User.id == user_id, last.is_(None) if previous is None
                                                    else last == previous).values(
            weekly_digest_sent_at=when, weekly_digest_claimed_at=when, weekly_digest_claimed_from=previous))
        session.commit()
        return bool(getattr(result, 'rowcount', 0))


def mark_weekly_digest(user_id: int, when: Optional[datetime]) -> None:
    """Anota hasta cuándo cubrió el último resumen semanal de la cuenta (el próximo arranca ahí)."""
    with accounts._sessions()() as session:
        user = session.get(User, user_id)
        if user is not None:
            user.weekly_digest_sent_at = when
            user.weekly_digest_claimed_at = user.weekly_digest_claimed_from = None
            session.commit()


def confirm_weekly_digest(user_id: int, when: datetime) -> None:
    """El resumen tomado en `when` ya salió: deja de poder recuperarse."""
    with accounts._sessions()() as session:
        session.execute(update(User).where(User.id == user_id, User.weekly_digest_claimed_at == when).values(
            weekly_digest_claimed_at=None, weekly_digest_claimed_from=None))
        session.commit()


def recover_weekly_digest(user_id: int, older_than: datetime) -> bool:
    """Un resumen tomado antes de `older_than` y nunca confirmado (el worker murió) vuelve a estar pendiente."""
    with accounts._sessions()() as session:
        user = session.get(User, user_id)
        claimed = user.weekly_digest_claimed_at if user is not None else None
        if claimed is None or claimed >= older_than:
            return False
        result = session.execute(update(User).where(User.id == user_id, User.weekly_digest_claimed_at == claimed)
                                 .values(weekly_digest_sent_at=User.weekly_digest_claimed_from,
                                         weekly_digest_claimed_at=None, weekly_digest_claimed_from=None))
        session.commit()
        return bool(getattr(result, 'rowcount', 0))


def mark_active(user_id: int, session: Optional[Session] = None) -> None:
    """Anota que la cuenta usó la web y anula el aviso de borrado por inactividad."""
    query = update(User).where(User.id == user_id).values(last_active_at=datetime.now(), inactivity_notice_at=None,
                                                   inactivity_notice_sent=False)
    if session is not None:
        session.execute(query)
        return
    with accounts._sessions()() as own:
        own.execute(query)
        own.commit()


def inactive_accounts(since: datetime) -> list[dict[str, Any]]:
    """Cuentas sin actividad desde `since` (las nunca usadas cuentan desde el alta), con el estado del aviso."""
    last = func.coalesce(User.last_active_at, User.created_at)
    with accounts._sessions()() as session:
        rows = session.execute(select(User.id, User.email, User.inactivity_notice_at, User.inactivity_notice_sent)
                               .where(last < since).order_by(User.id))
        return [{'id': uid, 'email': email, 'notice_at': notice, 'notice_sent': bool(sent)}
                for uid, email, notice, sent in rows]


def set_inactivity_notice(user_id: int, when: datetime, previous: Optional[datetime] = None) -> bool:
    """Reserva el aviso de borrado (todavía sin enviar); False si la cuenta volvió a entrar u otro worker lo tomó.

    `previous` retoma una reserva que quedó sin enviar (el worker se cortó antes de mandar el email).
    """
    pending = (User.inactivity_notice_at.is_(None) if previous is None else
               (User.inactivity_notice_at == previous) & User.inactivity_notice_sent.is_(False))
    with accounts._sessions()() as session:
        result = session.execute(update(User).where(User.id == user_id, pending)
                                 .values(inactivity_notice_at=when, inactivity_notice_sent=False))
        session.commit()
        return bool(accounts.rowcount(result))


def confirm_inactivity_notice(user_id: int, when: datetime) -> bool:
    """Marca como enviado el aviso reservado en `when`; desde ahí corre el plazo para borrar."""
    with accounts._sessions()() as session:
        result = session.execute(update(User).where(User.id == user_id, User.inactivity_notice_at == when)
                                 .values(inactivity_notice_sent=True))
        session.commit()
        return bool(accounts.rowcount(result))


def clear_inactivity_notice(user_id: int, when: datetime) -> None:
    """Deshace el aviso reservado en `when` (el email no salió): se vuelve a intentar en la próxima corrida."""
    with accounts._sessions()() as session:
        session.execute(update(User).where(User.id == user_id, User.inactivity_notice_at == when,
                                           User.inactivity_notice_sent.is_(False))
                        .values(inactivity_notice_at=None))
        session.commit()


def delete_account(user_id: int, notice_at: Optional[datetime] = None) -> bool:
    """Borra la cuenta, todas sus filas y sus carpetas de resultados (los CVs los borra quien llama).

    Con `notice_at`, solo si la cuenta sigue con ese aviso de inactividad enviado: la fila queda bloqueada
    hasta el commit, así un login que llega a la vez (que anula el aviso) espera y no se pierde. False si no borró.
    """
    import shutil
    from sqlalchemy import delete, inspect, text
    with accounts._sessions()() as session:
        if notice_at is not None and session.execute(
                select(User.id).where(User.id == user_id, User.inactivity_notice_at == notice_at,
                                      User.inactivity_notice_sent.is_(True)).with_for_update()).first() is None:
            session.rollback()
            return False
        for table in accounts._owned_tables(inspect(session.get_bind())):
            session.execute(text(f'DELETE FROM {table} WHERE user_id = :uid'), {'uid': user_id})
        session.execute(delete(User).where(User.id == user_id))
        session.commit()
    shutil.rmtree(os.path.join(accounts.RESULTS_ROOT, f'u{user_id}'), ignore_errors=True)
    shutil.rmtree(os.path.join(os.getenv('GENERATED_DIR', 'temp'), f'u{user_id}'), ignore_errors=True)
    return True
