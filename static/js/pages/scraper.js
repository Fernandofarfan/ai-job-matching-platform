document.addEventListener('DOMContentLoaded', function () {
  // Add search row buttons
  document.getElementById('add-indeed-search').addEventListener('click', function () {
    addSearchRow('indeed-search-params');
  });

  document.getElementById('add-linkedin-search').addEventListener('click', function () {
    addSearchRow('linkedin-search-params');
  });

  document.getElementById('add-computrabajo-search').addEventListener('click', function () {
    addSearchRow('computrabajo-search-params');
  });

  document.getElementById('add-bumeran-search').addEventListener('click', function () {
    addSearchRow('bumeran-search-params');
  });

  // Handle remove search buttons
  document.addEventListener('click', function (e) {
    if (e.target.closest('.remove-search')) {
      const row = e.target.closest('.search-row');
      if (row && row.parentElement.querySelectorAll('.search-row').length > 1) {
        row.remove();
      }
    }
  });

  // Start polling for status updates
  pollStatus();
});

function addSearchRow(containerId) {
  const container = document.getElementById(containerId);
  const newRow = container.querySelector('.search-row').cloneNode(true);

  // Clear inputs
  newRow.querySelectorAll('input').forEach(input => {
    input.value = '';
  });

  container.appendChild(newRow);
}

function toggleFilters(filterId) {
  const filterDiv = document.getElementById(filterId);
  const buttonId = 'toggle-' + filterId;
  const button = document.getElementById(buttonId);

  if (getComputedStyle(filterDiv).display === 'none') {
    filterDiv.style.display = 'block';
    if (button) button.textContent = t("Ocultar Configuración");
  } else {
    filterDiv.style.display = 'none';
    if (button) button.textContent = t("Configuración Avanzada");
  }
}

function pollStatus() {
  fetch('/status')
    .then(response => response.json())
    .then(data => {
      updateStatusUI('indeed', data.indeed_scraping);
      updateStatusUI('linkedin', data.linkedin_scraping);
      updateStatusUI('computrabajo', data.computrabajo_scraping);
      updateStatusUI('bumeran', data.bumeran_scraping);

      updateUniversalStatusUI(data.universal_scraping);

      // Poll again in 2 seconds
      setTimeout(pollStatus, 2000);
    })
    .catch(error => {
      console.error('Error polling status:', error);
      setTimeout(pollStatus, 5000);  // Try again after 5 seconds
    });
}

function updateStatusUI(prefix, jobData) {
  const statusElem = document.getElementById(`${prefix}-status`);
  const progressElem = document.getElementById(`${prefix}-progress`);
  const messageElem = document.getElementById(`${prefix}-message`);

  if (!statusElem || !jobData) return;

  // Update status text and color
  const statusTranslations = {
    'idle': t("Inactivo"),
    'running': t("Ejecutando"),
    'completed': t("Completado"),
    'failed': t("Falló")
  };
  const statusText = statusTranslations[jobData.status] || jobData.status;

  statusElem.textContent = statusText.charAt(0).toUpperCase() + statusText.slice(1);

  // Reset classes
  statusElem.className = 'badge border';
  progressElem.className = 'progress-bar';
  if (prefix === 'linkedin') progressElem.classList.add('bg-info');
  else if (prefix === 'computrabajo') progressElem.classList.add('bg-danger');
  else if (prefix === 'bumeran') progressElem.classList.add('bg-success');

  if (jobData.status === 'running') {
    statusElem.classList.add('bg-primary', 'text-white', 'border-primary', 'animate-pulse');
    progressElem.classList.add('progress-bar-striped', 'progress-bar-animated');
  } else if (jobData.status === 'completed') {
    statusElem.classList.add('bg-success', 'text-white', 'border-success');
    progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
  } else if (jobData.status === 'failed') {
    statusElem.classList.add('bg-danger', 'text-white', 'border-danger');
    progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
  } else {
    // Idle
    statusElem.classList.add('bg-light', 'text-dark');
    progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
  }

  // Update progress bar
  progressElem.style.width = `${jobData.progress}%`;
  progressElem.setAttribute('aria-valuenow', jobData.progress);

  // Update message
  messageElem.textContent = jobData.message;
}

function updateUniversalStatusUI(jobData) {
  if (!jobData) return;

  const statusElem = document.getElementById('universal-status');
  const progressElem = document.getElementById('universal-progress');
  const messageElem = document.getElementById('universal-message');
  const progressTextElem = document.getElementById('universal-progress-text');

  if (!statusElem) return;

  // Update status text and color
  const statusTranslations = {
    'idle': t("Inactivo"),
    'running': t("Ejecutando"),
    'completed': t("Completado"),
    'failed': t("Falló")
  };
  const statusText = statusTranslations[jobData.status] || jobData.status;

  statusElem.textContent = statusText.charAt(0).toUpperCase() + statusText.slice(1);
  statusElem.className = 'badge';

  if (jobData.status === 'running') {
    statusElem.classList.add('bg-primary', 'animate-pulse');
    progressElem.classList.add('progress-bar-striped', 'progress-bar-animated');
  } else if (jobData.status === 'completed') {
    statusElem.classList.add('bg-success');
    progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
  } else if (jobData.status === 'failed') {
    statusElem.classList.add('bg-danger');
    progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
  } else {
    statusElem.classList.add('bg-secondary');
    progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
  }

  // Update progress bar
  progressElem.style.width = `${jobData.progress}%`;
  progressElem.setAttribute('aria-valuenow', jobData.progress);
  if (progressTextElem) progressTextElem.textContent = `${jobData.progress}%`;

  // Update message
  messageElem.textContent = jobData.message;

  // Update individual scraper statuses
  if (jobData.scrapers) {
    for (const [name, scraperData] of Object.entries(jobData.scrapers)) {
      const badgeElem = document.getElementById(`universal-${name}-status`);
      const cardElem = document.getElementById(`card-universal-${name}`);

      if (badgeElem) {
        badgeElem.className = 'badge border';
        if (cardElem) cardElem.className = 'mini-card';

        if (scraperData.status === 'running') {
          badgeElem.classList.add('bg-primary', 'text-white', 'border-primary', 'animate-pulse');
          badgeElem.textContent = t("Ejecutando...");
          if (cardElem) cardElem.classList.add('active');
        } else if (scraperData.status === 'completed') {
          badgeElem.classList.add('bg-success', 'text-white', 'border-success');
          badgeElem.textContent = t("✓ Completado");
          if (cardElem) cardElem.classList.add('completed');
        } else if (scraperData.status === 'failed') {
          badgeElem.classList.add('bg-danger', 'text-white', 'border-danger');
          badgeElem.textContent = '✗ Error';
        } else if (scraperData.status === 'skipped') {
          badgeElem.classList.add('bg-warning', 'text-dark', 'border-warning');
          badgeElem.textContent = t("Omitido");
        } else {
          badgeElem.classList.add('bg-light', 'text-dark');
          badgeElem.textContent = t("Esperando");
        }
      }
    }
  }
}
