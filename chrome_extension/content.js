/**
 * content.js — EmpleoIA Saver Content Script
 * Extrae datos de la oferta de trabajo en la página actual.
 */

// El menú contextual puede volver a inyectar este script: sin la guarda, redeclarar las funciones rompe
if (!window.__empleoiaSaverLoaded) {
window.__empleoiaSaverLoaded = true;

/**
 * Detecta qué plataforma es la página actual
 */
function detectPlatform() {
  const url = window.location.href;
  if (url.includes('linkedin.com')) return 'linkedin';
  if (url.includes('indeed.com')) return 'indeed';
  if (url.includes('bumeran.com')) return 'bumeran';
  if (url.includes('computrabajo.com')) return 'computrabajo';
  if (url.includes('zonajobs.com')) return 'bumeran';
  if (url.includes('getonbrd.com')) return 'getonbrd';
  return 'unknown';
}

/**
 * Extractores por plataforma — cada uno devuelve { title, company, location, salary, description, apply_url }
 */
const extractors = {

  linkedin: () => {
    const title = document.querySelector('h1.job-details-jobs-unified-top-card__job-title, h1.t-24, .job-view-layout h1')?.innerText?.trim() || '';
    const company = document.querySelector('.job-details-jobs-unified-top-card__company-name a, .job-details-jobs-unified-top-card__company-name')?.innerText?.trim() || '';
    const location = document.querySelector('.job-details-jobs-unified-top-card__bullet, .tvm__text--low-emphasis')?.innerText?.trim() || '';
    const description = document.querySelector('.jobs-description__content, .job-view-layout .description__text')?.innerText?.trim() || '';
    const salary = document.querySelector('.compensation__salary, .salary-main-rail__salary-info')?.innerText?.trim() || '';

    return { title, company, location, salary, description, apply_url: window.location.href };
  },

  indeed: () => {
    const title = document.querySelector('h1.jobsearch-JobInfoHeader-title, [data-testid="jobsearch-JobInfoHeader-title"]')?.innerText?.trim() || '';
    const company = document.querySelector('.icl-u-lg-mr--sm.icl-u-xs-mr--xs, [data-testid="inlineHeader-companyName"] a')?.innerText?.trim() || '';
    const location = document.querySelector('.icl-IconFunctional--location, [data-testid="job-location"]')?.innerText?.trim() ||
                     document.querySelector('[data-testid="inlineHeader-jobLocation"]')?.innerText?.trim() || '';
    const salary = document.querySelector('.salary-snippet-container, [data-testid="attribute_snippet_testid"]')?.innerText?.trim() || '';
    const description = document.querySelector('#jobDescriptionText, .jobsearch-jobDescriptionText')?.innerText?.trim() || '';

    return { title, company, location, salary, description, apply_url: window.location.href };
  },

  bumeran: () => {
    const title = document.querySelector('h1.sc-8b37c55e-0, .PostingDescription__title, [data-qa="posting-name"]')?.innerText?.trim() || 
                  document.querySelector('h1')?.innerText?.trim() || '';
    const company = document.querySelector('[data-qa="posting-company-name"], .PostingDescription__company')?.innerText?.trim() || '';
    const location = document.querySelector('[data-qa="posting-location"], .PostingDescription__location')?.innerText?.trim() || '';
    const salary = document.querySelector('[data-qa="posting-salary"], .PostingDescription__salary')?.innerText?.trim() || '';
    const description = document.querySelector('[data-qa="rich-description-container"], .PostingDescription__description')?.innerText?.trim() || '';

    return { title, company, location, salary, description, apply_url: window.location.href };
  },

  computrabajo: () => {
    const title = document.querySelector('h1.fc-heading, h1[class*="title"]')?.innerText?.trim() ||
                  document.querySelector('h1')?.innerText?.trim() || '';
    const company = document.querySelector('.dFrmLink, [class*="company"]')?.innerText?.trim() || '';
    const location = document.querySelector('.mr-8[class*="location"], span[class*="location"]')?.innerText?.trim() || '';
    const salary = document.querySelector('span[class*="salary"], [class*="sueldo"]')?.innerText?.trim() || '';
    const description = document.querySelector('[class*="description"], .jobDescription')?.innerText?.trim() || '';

    return { title, company, location, salary, description, apply_url: window.location.href };
  },

  getonbrd: () => {
    const title = document.querySelector('h1 [itemprop="title"], h1')?.innerText?.trim() || '';
    const company = document.querySelector('[itemprop="hiringOrganization"] [itemprop="name"], [itemprop="hiringOrganization"]')?.innerText?.trim() || '';
    const location = document.querySelector('[itemprop="jobLocation"], .location')?.innerText?.trim() || '';
    const salary = document.querySelector('[itemprop="baseSalary"]')?.innerText?.trim() || '';
    const description = document.querySelector('[itemprop="description"], #job-body')?.innerText?.trim() || '';
    return { title, company, location, salary, description, apply_url: window.location.href };
  },

  unknown: () => {
    // Fallback genérico: intenta heurísticas básicas
    const headings = document.querySelectorAll('h1, h2');
    const title = headings[0]?.innerText?.trim() || document.title || '';
    const description = document.querySelector('[class*="desc"], [id*="desc"], main')?.innerText?.trim().slice(0, 2000) || '';
    return { title, company: '', location: '', salary: '', description, apply_url: window.location.href };
  }
};

/**
 * Completa los campos vacíos con el JobPosting de schema.org (JSON-LD), que casi todos los portales publican.
 */
function jobPostingFromJsonLd() {
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const nodes = [].concat(JSON.parse(script.textContent));
      for (const node of nodes.flatMap(n => (n && n['@graph']) || [n])) {
        if (node && [].concat(node['@type']).includes('JobPosting')) return node;
      }
    } catch (e) { /* JSON-LD inválido: se ignora */ }
  }
  return null;
}

function textFromHtml(html) {
  return new DOMParser().parseFromString(String(html || ''), 'text/html').body.textContent.trim();
}

function withJsonLd(data) {
  const posting = jobPostingFromJsonLd();
  if (!posting) return data;
  const address = [].concat(posting.jobLocation || [])[0]?.address || {};
  const fromLd = {
    title: posting.title,
    company: posting.hiringOrganization?.name,
    location: [address.addressLocality, address.addressRegion, address.addressCountry?.name || address.addressCountry]
      .filter(v => typeof v === 'string' && v).join(', '),
    description: textFromHtml(posting.description),
  };
  for (const [key, value] of Object.entries(fromLd)) {
    if (!data[key] && value) data[key] = String(value).trim();
  }
  return data;
}

/**
 * Mensaje listener: popup pide extraer datos
 */
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractJobData') {
    const platform = detectPlatform();
    const extractor = extractors[platform] || extractors.unknown;

    try {
      const data = withJsonLd(extractor());
      data.platform = platform;
      data.page_url = window.location.href;
      data.extracted_at = new Date().toISOString();
      sendResponse({ success: true, data });
    } catch (error) {
      sendResponse({ success: false, error: error.message });
    }
  }

  if (request.action === 'showSavedIndicator') {
    showSavedToast(request.jobTitle || 'Trabajo');
    sendResponse({ success: true });
  }

  // Las respuestas son síncronas: devolver true dejaba el canal abierto y el emisor fallaba sin respuesta
  return false;
});

/**
 * Muestra un toast en la página indicando que el trabajo fue guardado
 */
function showSavedToast(jobTitle) {
  const existing = document.getElementById('empleoia-saved-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'empleoia-saved-toast';
  // El título viene de la página: va como texto, nunca como HTML
  toast.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="font-size:1.3rem;" aria-hidden="true">🤖</span>
      <div><strong>¡Guardado en EmpleoIA!</strong><br><small style="opacity:0.85;"></small></div>
    </div>`;
  toast.setAttribute('role', 'status');
  toast.querySelector('small').textContent = String(jobTitle).slice(0, 50);
  
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 999999;
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    padding: 14px 20px;
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.5);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 14px;
    animation: empleoia-slideIn 0.3s ease;
    min-width: 260px;
  `;

  const style = document.createElement('style');
  style.textContent = `
    @keyframes empleoia-slideIn {
      from { transform: translateX(110%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }`;
  document.head.appendChild(style);
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'none';
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
}
