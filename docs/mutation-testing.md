# Pruebas de mutación

La cobertura dice qué líneas ejecutan los tests, no si fallarían ante un bug. mutmut lo mide: cambia el código de a
un detalle por vez (un `or` por `and`, un `>` por `>=`, un texto por otro) y corre los tests. Si ningún test falla,
el mutante "sobrevive" y hay un caso sin probar.

## Qué se muta

`[tool.mutmut]` en `pyproject.toml`:

| Módulo | Por qué |
|---|---|
| `auth.py` | Sesiones, CSRF y tokens de la extensión |
| `accounts.py` | Registro, login, administrador, bloqueo de cuentas |
| `rate_limit.py` | Límites de pedidos por cuenta, IP y página |
| `job_dedup.py` | Unificación de ofertas repetidas entre portales |

Solo corren los tests de `tests_dir`. Todo lo que esos tests importan y no se muta va en `also_copy`, porque mutmut
corre desde `mutants/`. `tests/test_mutmut_config.py` falla si un módulo nuevo de la raíz no está en esa lista.

## Resultado actual

| Módulo | Detectados | Sobreviven | Sin tests | Puntaje |
|---|---|---|---|---|
| `accounts.py` | 341 | 92 | 23 | 74,8 % |
| `auth.py` | 214 | 42 | 27 | 75,6 % |
| `job_dedup.py` | 307 | 30 | 0 | 91,1 % |
| `rate_limit.py` | 126 | 31 | 0 | 80,3 % |
| **Total** | 988 | 195 | 50 | 80,1 % |

"Sin tests" son funciones que ningún test de `tests_dir` ejecuta, por ejemplo las de passkeys y WebAuthn de
`auth.py`, que se prueban en integración.

## Correrlo

```bash
pip install --require-hashes -r requirements.txt -r requirements-mutation.txt
mutmut run                        # unos 25 minutos
python scripts/mutation_report.py # tabla por módulo
mutmut results                    # mutantes que sobreviven
mutmut show accounts.x_register__mutmut_12
```

En GitHub corre los lunes y a mano (Actions → Pruebas de mutación). El reporte queda en el resumen del workflow y
como artefacto. No frena PRs: es una guía para saber qué tests faltan.

## Cómo leer los sobrevivientes

No todos son tests faltantes. Algunos son equivalentes: el cambio no altera el comportamiento, por ejemplo el texto
de un `logger.warning` o el valor por defecto de un `get` que nunca se usa. Esos se ignoran. Los que importan son los
que cambian una condición, un límite o un mensaje que ve el usuario.
