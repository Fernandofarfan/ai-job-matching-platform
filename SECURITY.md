# Política de seguridad

## Cómo reportar una vulnerabilidad

**No abras un issue público.** Reportala en privado desde GitHub: pestaña **Security** del repositorio → **Report a vulnerability** ([formulario directo](https://github.com/Fernandofarfan/ai-job-matching-platform/security/advisories/new)). Solo lo ven los mantenedores.

Incluí, si podés:

- qué parte afecta (ruta, página, scraper, worker, extensión de Chrome o Terraform) y la versión (`VERSION` o `/api/health`);
- pasos para reproducirla y qué se puede lograr con ella;
- si la probaste contra una instalación propia. No pruebes contra cuentas o datos de otras personas.

## Qué esperar

| Paso | Plazo |
|---|---|
| Acuse de recibo | 3 días hábiles |
| Primera evaluación (si se confirma y qué gravedad tiene) | 10 días hábiles |
| Corrección de una vulnerabilidad crítica o alta | 30 días desde que se confirma |

Te avisamos cuando salga la corrección y, si querés, te damos crédito en el advisory y en el CHANGELOG. Pedimos no publicar detalles hasta que haya una versión corregida o pasen 90 días desde el reporte, lo que ocurra primero.

## Versiones con soporte

Solo la última versión publicada (tag `vX.Y.Z`, ver [docs/releases.md](docs/releases.md)) y `main` reciben correcciones de seguridad.

## Qué entra

- La app web y la API (`main.py`, `routers/`, `services/`), las sesiones, el login, el segundo factor y las passkeys.
- El worker de Celery, los scrapers y el manejo de CVs (cifrado, retención y borrado).
- La extensión de Chrome (`chrome_extension/`).
- La infraestructura de `terraform/` y los workflows de `.github/workflows/`.

No entran: vulnerabilidades de los portales de empleo o de Gemini, ataques que requieren acceso físico al equipo o una cuenta de administrador, ni reportes automáticos sin una prueba de impacto.

## Qué ya se revisa en cada PR

Bandit, pip-audit, gitleaks, Trivy sobre la imagen, OWASP ZAP sobre la app levantada y Schemathesis sobre la API. Qué hacer ante un incidente: [docs/runbook.md](docs/runbook.md#sospecha-de-incidente-de-seguridad).
