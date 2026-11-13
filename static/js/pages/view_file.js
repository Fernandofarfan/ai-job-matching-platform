const VIEW_FILE = JSON.parse(document.getElementById('viewFileData').textContent);

let appliedJobs = {};
const feedbackData = JSON.parse(document.getElementById('feedbackData').textContent);
const feedbackTexts = JSON.parse(document.getElementById('feedbackTexts').textContent);

// Datos de la oferta de una fila, leídos de las celdas por nombre de columna
function rowJob(row) {
  const headers = Array.from(document.querySelectorAll('#jobTable thead th')).map(th => th.textContent.trim());
  const cells = row.querySelectorAll('td');
  const cell = (name) => { const i = headers.indexOf(name); return i !== -1 && cells[i] ? cells[i] : null; };
  // Indeed y LinkedIn traen 'Enlace' (botón); Computrabajo, Bumeran, ZonaJobs y GetOnBoard, 'URL' (texto)
  const linkCell = cell('Enlace') || cell('URL');
  const link = linkCell ? linkCell.querySelector('a') : null;
  const linkText = linkCell ? linkCell.textContent.trim() : '';
  return {
    title: cell('Título') ? cell('Título').textContent.trim() : '',
    company: cell('Empresa') ? cell('Empresa').textContent.trim() : '',
    location: cell('Ubicación') ? cell('Ubicación').textContent.trim() : '',
    job_link: link ? link.href : (/^https?:\/\//.test(linkText) ? linkText : ''),
  };
}

function showFeedback(row, buttons, interested) {
  buttons.yes.setAttribute('aria-pressed', interested === true ? 'true' : 'false');
  buttons.no.setAttribute('aria-pressed', interested === false ? 'true' : 'false');
  buttons.yes.className = 'btn btn-sm ' + (interested === true ? 'btn-success' : 'btn-outline-success');
  buttons.no.className = 'btn btn-sm ' + (interested === false ? 'btn-danger' : 'btn-outline-danger');
  row.classList.toggle('table-secondary', interested === false);
}

async function sendFeedback(index, row, buttons, value) {
  const current = buttons.yes.getAttribute('aria-pressed') === 'true' ? true
    : buttons.no.getAttribute('aria-pressed') === 'true' ? false : null;
  const interested = current === value ? null : value;  // tocar la marca activa la quita
  const info = feedbackData[index] || {};
  try {
    const response = await fetch('/api/job_feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job: rowJob(row), interested: interested, match_score: info.match,
                             file: VIEW_FILE.filename }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error);
    showFeedback(row, buttons, interested);
  } catch (e) {
    alert(feedbackTexts.error);
  }
}

function feedbackButtons(index, row) {
  const make = (value, icon, label) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.title = label;
    button.setAttribute('aria-label', label);
    button.innerHTML = `<i class="bi ${icon}"></i>`;
    return button;
  };
  const buttons = { yes: make(true, 'bi-hand-thumbs-up', feedbackTexts.yes),
                    no: make(false, 'bi-hand-thumbs-down', feedbackTexts.no) };
  buttons.yes.classList.add('feedback-yes');
  buttons.no.classList.add('feedback-no');
  buttons.yes.addEventListener('click', () => sendFeedback(index, row, buttons, true));
  buttons.no.addEventListener('click', () => sendFeedback(index, row, buttons, false));
  showFeedback(row, buttons, (feedbackData[index] || {}).interested ?? null);
  buttons.yes.id = `feedback_yes_${index}`;
  buttons.no.id = `feedback_no_${index}`;
  return buttons;
}

document.addEventListener('DOMContentLoaded', function () {
  modifyTable();
});

function modifyTable() {
  const table = document.getElementById('jobTable');
  if (!table) return;

  const headerRow = table.querySelector('thead tr');
  const bodyRows = table.querySelectorAll('tbody tr');

  // Find column indices
  const headers = Array.from(headerRow.querySelectorAll('th'));
  let jobLinkIndex = -1;
  let applyUrlIndex = -1;

  headers.forEach((header, index) => {
    const text = header.textContent.trim();
    if (text.includes('Enlace') || text === 'URL') jobLinkIndex = index;
    if (text === 'Apply_URL') applyUrlIndex = index;
  });

  // Insert Track button header
  const trackHeader = document.createElement('th');
  trackHeader.innerHTML = 'Acciones';
  trackHeader.style.width = '180px'; // Wider for two buttons

  // Insert Applied header
  const appliedHeader = document.createElement('th');
  appliedHeader.innerHTML = 'Aplicado';
  appliedHeader.style.width = '80px';

  // Insert headers after Job_Link
  const insertIndex = jobLinkIndex !== -1 ? jobLinkIndex + 1 : headers.length;

  if (insertIndex < headers.length) {
    headerRow.insertBefore(trackHeader, headers[insertIndex]);
    headerRow.insertBefore(appliedHeader, headers[insertIndex + 1]);
  } else {
    headerRow.appendChild(trackHeader);
    headerRow.appendChild(appliedHeader);
  }

  // Hide Apply_URL column header if it exists (we'll use it for the button)
  if (applyUrlIndex !== -1) {
    headers[applyUrlIndex].style.display = 'none';
  }

  // Process each row
  bodyRows.forEach((row, index) => {
    const cells = row.querySelectorAll('td');

    // Get Apply URL if available
    let applyUrl = '#';
    if (applyUrlIndex !== -1 && cells[applyUrlIndex]) {
      applyUrl = cells[applyUrlIndex].textContent.trim();
      cells[applyUrlIndex].style.display = 'none'; // Hide the raw URL cell
    } else if (jobLinkIndex !== -1 && cells[jobLinkIndex]) {
      // Fallback to job link
      const link = cells[jobLinkIndex].querySelector('a');
      applyUrl = link ? link.href : '#';
    }

    // Create Actions cell (Super Button)
    const actionsCell = document.createElement('td');

    // Determine if we have a valid URL
    const hasUrl = /^https?:\/\//i.test(applyUrl || '');

    // Celdas armadas con el DOM: la URL viene del CSV y no se mete en HTML ni en un handler inline
    const applyBtn = document.createElement('button');
    applyBtn.className = 'btn btn-sm btn-primary fw-bold';
    applyBtn.title = 'Postular, Seguir y Marcar como Aplicado';
    applyBtn.disabled = !hasUrl;
    applyBtn.innerHTML = '<i class="bi bi-rocket-takeoff"></i> Postular y Seguir';
    applyBtn.addEventListener('click', (event) => applyAndTrack(index, hasUrl ? applyUrl : '', event));
    const actionsWrap = document.createElement('div');
    actionsWrap.className = 'd-flex gap-2';
    actionsWrap.appendChild(applyBtn);
    const feedback = feedbackButtons(index, row);
    actionsWrap.appendChild(feedback.yes);
    actionsWrap.appendChild(feedback.no);
    actionsCell.appendChild(actionsWrap);

    // Create toggle cell
    const toggleCell = document.createElement('td');
    const toggleWrap = document.createElement('div');
    toggleWrap.className = 'form-check form-switch';
    const toggle = document.createElement('input');
    toggle.className = 'form-check-input';
    toggle.type = 'checkbox';
    toggle.id = `applied_${index}`;
    toggle.setAttribute('aria-label', 'Aplicado');
    toggle.addEventListener('change', () => toggleApplied(index, toggle));
    toggleWrap.appendChild(toggle);
    toggleCell.appendChild(toggleWrap);

    // Insert cells
    if (insertIndex < cells.length) {
      row.insertBefore(actionsCell, cells[insertIndex]);
      row.insertBefore(toggleCell, cells[insertIndex + 1]);
    } else {
      row.appendChild(actionsCell);
      row.appendChild(toggleCell);
    }
  });
}

function applyAndTrack(index, url, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  if (!url) {
    alert('No hay enlace de postulación disponible para este trabajo.');
    return;
  }

  // 1. Open URL in new tab
  window.open(url, '_blank');

  // 2. Mark as Applied (visually and in data)
  const toggle = document.getElementById(`applied_${index}`);
  if (toggle && !toggle.checked) {
    toggle.checked = true;
    toggleApplied(index, toggle); // Updates appliedJobs and row style
  }

  // 3. Add to Tracker (as applied)
  addJobToTracker(index, event);
}

function toggleApplied(index, checkbox) {
  const row = checkbox.closest('tr');
  const cells = row.querySelectorAll('td');

  // Find column indices dynamically to be safe
  const table = document.getElementById('jobTable');
  const headerRow = table.querySelector('thead tr');
  const headers = Array.from(headerRow.querySelectorAll('th')).map(th => th.textContent.trim());

  const titleIdx = headers.indexOf('Título');
  const companyIdx = headers.indexOf('Empresa');
  const locationIdx = headers.indexOf('Ubicación');
  const jobLinkIdx = headers.indexOf('Enlace');

  if (checkbox.checked) {
    // Extract job data from row
    const jobData = {
      title: titleIdx !== -1 && cells[titleIdx] ? cells[titleIdx].textContent.trim() : 'Not specified',
      company: companyIdx !== -1 && cells[companyIdx] ? cells[companyIdx].textContent.trim() : 'Not specified',
      location: locationIdx !== -1 && cells[locationIdx] ? cells[locationIdx].textContent.trim() : 'Not specified',
      job_link: jobLinkIdx !== -1 && cells[jobLinkIdx] ? cells[jobLinkIdx].querySelector('a')?.href || '' : 'Not specified',
      job_type: 'Not specified',
      description: '',
      applied_date: new Date().toISOString()
    };

    appliedJobs[index] = jobData;
    row.classList.add('table-success');
  } else {
    delete appliedJobs[index];
    row.classList.remove('table-success');
  }
}

function saveApplicationStatus() {
  const appliedCount = Object.keys(appliedJobs).length;

  if (appliedCount === 0) {
    alert('Por favor marca al menos un trabajo como aplicado antes de guardar.');
    return;
  }

  fetch('/api/save_applications', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      filename: VIEW_FILE.filename,
      applied_jobs: appliedJobs,
      total_jobs: VIEW_FILE.total_jobs
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      document.getElementById('modalMessage').textContent =
        `Guardado exitosamente ${data.saved} postulación(es) para ${data.companies.length} empresas.`;
      new bootstrap.Modal(document.getElementById('successModal')).show();
    }
  })
  .catch(error => {
    console.error('Error saving applications:', error);
    alert('Error guardando postulaciones. Por favor intenta de nuevo.');
  });
}

function processConnections() {
  const sendConnections = document.getElementById('sendConnections').checked;

  if (sendConnections) {
    window.location.href = '/connections?auto_start=true';
  } else {
    window.location.href = '/results';
  }
}

// Add job to tracker
function addJobToTracker(rowIndex, evt) {
  // Prevent any default button behavior
  if (evt) {
    evt.preventDefault();
    evt.stopPropagation();
  }

  const table = document.getElementById('jobTable');
  const headerRow = table.querySelector('thead tr');
  const headers = Array.from(headerRow.querySelectorAll('th')).map(th => th.textContent.trim());

  const row = table.querySelectorAll('tbody tr')[rowIndex];
  const cells = row.querySelectorAll('td');

  // Get the button element first
  // Note: When called from applyAndTrack, evt.target might be the icon or the button
  const button = evt ? evt.target.closest('button') : null;

  // Check if button is already disabled (already added)
  if (button && button.disabled) {
    console.log('Job already added to tracker');
    return;
  }

  // Find column indices dynamically
  const titleIdx = headers.indexOf('Título');
  const companyIdx = headers.indexOf('Empresa');
  const locationIdx = headers.indexOf('Ubicación');
  const jobLinkIdx = headers.indexOf('Enlace');
  const appliedIdx = headers.indexOf('Aplicado');

  console.log('Column indices:', { titleIdx, companyIdx, locationIdx, jobLinkIdx, appliedIdx });

  // Check if "Applied" toggle is checked for this row
  const appliedToggle = appliedIdx !== -1 && cells[appliedIdx] ?
    cells[appliedIdx].querySelector('input[type="checkbox"]') : null;
  const isApplied = appliedToggle ? appliedToggle.checked : false;

  // Determine status: "applied" if toggle is checked, otherwise "bookmarked"
  const status = isApplied ? 'applied' : 'bookmarked';

  // Extract job data from row cells
  const jobData = {
    title: titleIdx !== -1 && cells[titleIdx] ? cells[titleIdx].textContent.trim() : 'Not specified',
    company: companyIdx !== -1 && cells[companyIdx] ? cells[companyIdx].textContent.trim() : 'Not specified',
    location: locationIdx !== -1 && cells[locationIdx] ? cells[locationIdx].textContent.trim() : 'Not specified',
    job_link: jobLinkIdx !== -1 && cells[jobLinkIdx] ? cells[jobLinkIdx].querySelector('a')?.href || '' : '',
    status: status,
    excitement: 3,  // Default excitement level
    date_applied: isApplied ? new Date().toISOString().split('T')[0] : null  // Set date if applied
  };

  console.log('Sending job data:', jobData, 'Applied status:', isApplied);

  // Disable button immediately to prevent double-clicks
  if (button) {
    button.disabled = true;
    button.innerHTML = '<i class="bi bi-hourglass-split"></i> Añadiendo...';
  }

  // Send to API
  fetch('/api/tracker/job', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(jobData)
  })
    .then(response => {
      console.log('Response status:', response.status);
      // Handle 409 Conflict (duplicate) separately
      if (response.status === 409) {
        return response.json().then(data => {
          throw { isDuplicate: true, data: data };
        });
      }
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      console.log('Response data:', data);
      if (data.success) {
        // Show success message
        if (button) {
          button.innerHTML = '<i class="bi bi-check-circle-fill"></i> Seguido!';
          button.classList.remove('btn-outline-primary');
          button.classList.add('btn-success');
          button.disabled = true;
        }

        // Show success notification with status
        const statusMsg = jobData.status === 'applied' ? 'APLICADO' : 'GUARDADO';
        // alert(`Ô£à Trabajo añadido a la columna ${statusMsg} en el rastreador!`);
        // Removed alert to avoid popup spam when using Super Button
        console.log(`Trabajo añadido a la columna ${statusMsg} en el rastreador!`);
      } else {
        // Re-enable button on error
        if (button) {
          button.disabled = false;
          button.innerHTML = '<i class="bi bi-rocket-takeoff"></i> Postular y Seguir';
        }
        alert('ÔØî Error: ' + (data.error || 'Error desconocido'));
        console.error('API Error:', data);
      }
    })
    .catch(error => {
      // Handle duplicate error
      if (error.isDuplicate) {
        if (button) {
          button.innerHTML = '<i class="bi bi-check-circle"></i> Ya Seguido';
          button.classList.remove('btn-outline-primary');
          button.classList.add('btn-secondary');
          button.disabled = true;
        }
        // alert('Ôä╣´©Å Este trabajo ya está en tu rastreador!');
        console.log('Este trabajo ya está en tu rastreador!');
        return;
      }

      // Handle other errors
      console.error('Full error details:', error);
      if (error.stack) {
        console.error('Error stack:', error.stack);
      }

      // Re-enable button on error
      if (button) {
        button.disabled = false;
        button.innerHTML = '<i class="bi bi-rocket-takeoff"></i> Postular y Seguir';
      }

      alert('ÔØî Error: ' + (error.message || 'Error desconocido'));
    });
}

// ── Advanced Filters ──────────────────────────────────
function applyFilters() {
  const keyword = document.getElementById('filterKeyword').value.toLowerCase();
  const showRemote  = document.getElementById('filterRemote').checked;
  const showHybrid  = document.getElementById('filterHybrid').checked;
  const showOnsite  = document.getElementById('filterOnsite').checked;
  const showOther   = document.getElementById('filterOther').checked;

  const rows = document.querySelectorAll('#jobTable tbody tr');
  let visible = 0;

  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    const loc  = text;

    // Keyword filter
    if (keyword && !text.includes(keyword)) {
      row.style.display = 'none';
      return;
    }

    // Modality filter (keyword detection in row text)
    const isRemote  = /remot|remote/.test(loc);
    const isHybrid  = /h[íi]brido|hybrid/.test(loc);
    const isOnsite  = /presencial|on.?site|oficina/.test(loc);
    const isOther   = !isRemote && !isHybrid && !isOnsite;

    const allowed = (isRemote && showRemote) ||
                    (isHybrid && showHybrid) ||
                    (isOnsite && showOnsite) ||
                    (isOther  && showOther);

    row.style.display = allowed ? '' : 'none';
    if (allowed) visible++;
  });

  const countEl = document.getElementById('filterCount');
  if (countEl) countEl.textContent = visible;
}

function resetFilters() {
  document.getElementById('filterKeyword').value = '';
  ['filterRemote','filterHybrid','filterOnsite','filterOther']
    .forEach(id => document.getElementById(id).checked = true);
  applyFilters();
}

// Run on load to set count
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    const total = document.querySelectorAll('#jobTable tbody tr').length;
    const countEl = document.getElementById('filterCount');
    if (countEl) countEl.textContent = total;
  }, 200);
});
