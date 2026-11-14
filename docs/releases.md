# Versiones y releases

La versión vive en `VERSION` (semver). La lee la app (`version.py`): sale en `/api/health`, en la documentación
de la API y en Sentry (`empleoia@X.Y.Z+<commit>`). El commit lo pone el build con `APP_COMMIT`.

| Cambio | Ejemplo | Versión |
|---|---|---|
| Rompe algo para quien actualiza: variable nueva obligatoria, migración que no se puede revertir, API que cambia | `REDIS_PASSWORD` obligatoria | Mayor (`4.0.0`) |
| Función nueva, compatible | una página o una API nueva | Menor (`3.1.0`) |
| Solo correcciones | un bug | Parche (`3.0.1`) |

Cada PR agrega su entrada `## [Sin publicar] - Título` arriba del `CHANGELOG.md`.

## Sacar una versión

1. Desde `main` actualizado:
   ```bash
   python scripts/release.py prepare 4.0.0
   ```
   Sube `VERSION` y junta todas las entradas "Sin publicar" bajo `## [4.0.0] - <fecha>`. Revisá el texto
   y anotá arriba de la sección lo que hay que hacer al actualizar (variables nuevas, migraciones).
2. PR con ese cambio y merge a `main`. El push a `main` despliega en staging (`deploy.yml`).
3. Probá staging: `/api/health` tiene que mostrar la versión y el commit nuevos, y `/api/ready` dar 200.
4. Tag sobre el commit mergeado:
   ```bash
   git tag -a v4.0.0 -m "EmpleoIA 4.0.0" <commit> && git push origin v4.0.0
   ```
   `release.yml` verifica que el tag coincida con `VERSION`, publica la imagen en `ghcr.io` (`4.0.0` y
   `sha-<commit>`) y crea el release de GitHub con la sección del CHANGELOG.
5. Producción: Actions → "Deploy a GCP" → Run workflow, con `environment=prod` y el tag `v4.0.0` en
   "Use workflow from". Desde una rama, el deploy a producción se corta.

## Volver a la versión anterior

- **Automático, en cada deploy:** la revisión nueva entra sin tráfico, con la etiqueta `candidate`. El workflow
  prueba `/api/ready` en su URL y recién ahí le pasa el tráfico; si `/api/ready` falla después, lo devuelve a la
  revisión anterior. No aplica al primer deploy ni al servicio privado, donde no hay smoke test HTTP.
- **Rápido (sin rebuild):** Actions → "Deploy a GCP" con `environment=prod` y el tag anterior. La imagen de ese
  commit ya está en Artifact Registry, así que no se reconstruye; Terraform apunta Cloud Run a ella.
- **Inmediato, desde la consola:** `gcloud run services update-traffic empleoia-web-prod --region <región>
  --to-revisions <revisión anterior>=100`. Sirve mientras se corre lo anterior; el próximo deploy parte de esa revisión.
- **Base de datos:** el deploy corre `alembic upgrade head`, y volver la imagen atrás no revierte migraciones.
  Por eso las migraciones tienen que ser compatibles con la versión anterior (agregar columnas con default,
  borrar recién en la versión siguiente). Si una no lo es, va en una versión mayor y su nota dice cómo revertirla
  (`alembic downgrade <revisión>`, después de un backup: ver `docs/backup-restore.md`).
