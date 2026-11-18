"""Crea la cuenta de administrador (ADMIN_EMAIL) ya verificada, sin pasar por el email.

Uso: ADMIN_EMAIL=vos@ejemplo.com python scripts/create_admin.py
La contraseña se pide por teclado (o por stdin con --password-stdin) y nunca va en la línea de comandos.
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv: list[str] | None = None) -> int:
    """Crea la primera cuenta con ADMIN_EMAIL; devuelve 0 si la creó."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--password-stdin', action='store_true', help='leer la contraseña de stdin')
    args = parser.parse_args(argv)
    import accounts
    email = accounts.normalize_email(os.getenv('ADMIN_EMAIL', ''))
    if not email:
        print('Definí ADMIN_EMAIL', file=sys.stderr)
        return 1
    if accounts.count_users() > 0:
        print('Ya hay cuentas: la del administrador se recupera con "Olvidé mi contraseña"', file=sys.stderr)
        return 1
    if args.password_stdin:
        password = sys.stdin.readline().rstrip('\n')
    else:
        password = getpass.getpass('Contraseña: ')
        if password != getpass.getpass('Repetila: '):
            print('Las contraseñas no coinciden', file=sys.stderr)
            return 1
    try:
        user_id = accounts.register(email, password, terms_accepted=True, verified=True)
    except accounts.AccountError as e:
        print(e, file=sys.stderr)
        return 1
    print(f'Cuenta de administrador creada: {email} (id {user_id})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
