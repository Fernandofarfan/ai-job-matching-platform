# Publicar EmpleoIA Saver en el Chrome Web Store

La publicación la hace el dueño de la cuenta de desarrollador (pago único de USD 5 en el [Developer Dashboard](https://chrome.google.com/webstore/devconsole)).

1. Subí `version` en `chrome_extension/manifest.json` (el Store rechaza versiones repetidas).
2. `python scripts/package_extension.py` → `dist/empleoia-saver-<versión>.zip` (también queda como artefacto `chrome-extension` en el job de integración del CI).
3. En el dashboard: **Nuevo elemento** → subí el zip.
4. Completá la ficha con los textos de abajo, 1 captura de 1280×800 del popup y el ícono `chrome_extension/icons/icon128.png`.
5. Enviá a revisión (suele tardar de 1 a 3 días).

## Ficha

- **Nombre:** EmpleoIA Saver
- **Resumen:** Guardá ofertas de LinkedIn, Indeed, Bumeran, ZonaJobs, Computrabajo y GetOnBoard en tu EmpleoIA con 1 click.
- **Categoría:** Productividad
- **Idioma:** Español

## Prácticas de privacidad

- **Propósito único:** guardar la oferta de trabajo que el usuario está viendo en su propio tracker de EmpleoIA.
- **Datos que maneja:** título, empresa, ubicación, salario, descripción y URL de la oferta abierta. Se envían solo al servidor que el usuario configura (por defecto `http://localhost:5000`); no hay servidores de terceros ni analítica.
- **Justificación de permisos:**
  - `activeTab` y `scripting`: leer la oferta de la pestaña actual cuando el usuario usa el menú contextual.
  - `storage`: guardar la URL del servidor y el token de la extensión.
  - `contextMenus`: entrada "Guardar en EmpleoIA" del click derecho.
  - Host `localhost:5000`: enviar la oferta a la instancia local.
  - Host opcional `https://*/*`: se pide solo para el origen exacto del servidor que el usuario configura (por ejemplo su Cloud Run).
- **Código remoto:** no usa.
- Política de privacidad: publicá una página con el texto de "Datos que maneja" (por ejemplo en GitHub Pages) y pegá su URL.
