let currentJobId = null;

// Load all jobs on page load
document.addEventListener('DOMContentLoaded', function () {
  loadAllJobs();
  loadFunnelStats();
});

function loadFunnelStats() {
  fetch('/api/tracker/stats')
    .then(r => r.json())
    .then(data => {
      if (!data.success) return;
      const s = data.stats;
      const stages = ['applied', 'interviewing', 'negotiating', 'accepted'];
      stages.forEach(k => {
        const el = document.getElementById('fm-val-' + k);
        if (el) el.textContent = s[k] || 0;
      });
      // Conversion rates
      const applied = s.applied || 0;
      if (applied > 0) {
        const setConv = (id, val) => {
          const el = document.getElementById(id);
          if (el) el.textContent = Math.round(val / applied * 100) + '%';
        };
        setConv('fm-conv-interviewing', s.interviewing || 0);
        setConv('fm-conv-negotiating', s.negotiating || 0);
        setConv('fm-conv-accepted', s.accepted || 0);
      }
      document.getElementById('funnel-metrics').style.display = '';
    })
    .catch(() => {});
}

function loadAllJobs() {
  fetch('/api/tracker/jobs')
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        renderJobs(data.jobs);
      }
    })
    .catch(error => console.error('Error loading jobs:', error));
}

function renderJobs(jobs) {
  // Clear all stages
  const stages = ['applied', 'interviewing', 'negotiating', 'accepted'];
  stages.forEach(stage => {
    document.getElementById(`stage-${stage}`).innerHTML = '';
    document.getElementById(`count-${stage}`).textContent = '0';
  });

  // Group jobs by stage
  const jobsByStage = {};
  stages.forEach(stage => jobsByStage[stage] = []);

  jobs.forEach(job => {
    if (jobsByStage[job.status]) {
      jobsByStage[job.status].push(job);
    }
  });

  // Render jobs in each stage
  Object.keys(jobsByStage).forEach(stage => {
    const stageElement = document.getElementById(`stage-${stage}`);
    const count = jobsByStage[stage].length;

    document.getElementById(`count-${stage}`).textContent = count;

    jobsByStage[stage].forEach(job => {
      const card = createJobCard(job);
      stageElement.appendChild(card);
    });
  });

  // Apply compact view if saved
  const isCompact = localStorage.getItem('trackerCompactView') === 'true';
  if (isCompact) {
    document.querySelectorAll('.job-card').forEach(card => card.classList.add('compact'));
    updateToggleButton(true);
  }

  // Setup drag and drop
  setupDragAndDrop();
}

function createJobCard(job) {
  const card = document.createElement('div');
  card.className = 'job-card';
  card.draggable = true;
  card.dataset.jobId = job.id;

  const stars = '⭐'.repeat(job.excitement || 0);
  const appliedDate = job.date_applied ? new Date(job.date_applied).toLocaleDateString() : t("Pendiente");

  card.innerHTML = `
  <div class="job-card-title text-truncate">${job.title}</div>
  <div class="job-card-company">
    <i class="bi bi-building me-2 text-muted"></i> ${job.company}
  </div>
  ${job.location ? `<div class="text-muted mb-1 small"><i class="bi bi-geo-alt me-1"></i> ${job.location}</div>` : ''}
  ${job.salary && job.salary !== 'Not specified' ? `<div class="text-success mb-2 small fw-bold"><i class="bi bi-currency-dollar me-1"></i> ${job.salary}</div>` : ''}
  ${job.follow_up_due ? `<div class="badge bg-warning text-dark mb-2"><i class="bi bi-alarm me-1" aria-hidden="true"></i> ${tHtml("Hacer seguimiento")}</div>` : ''}
  ${!job.follow_up_due && job.follow_up ? `<div class="text-muted mb-2 small"><i class="bi bi-alarm me-1" aria-hidden="true"></i> ${tHtml("Seguimiento:")} ${escapeHtml(job.follow_up)}</div>` : ''}
  <div class="job-card-footer">
    <span class="text-warning small" style="letter-spacing: -2px;">${stars}</span>
    <span class="small">${appliedDate}</span>
  </div>
`;

  card.addEventListener('click', () => showJobDetails(job.id));

  return card;
}

function setupDragAndDrop() {
  const cards = document.querySelectorAll('.job-card');
  const stages = document.querySelectorAll('.stage-body');

  cards.forEach(card => {
    card.addEventListener('dragstart', handleDragStart);
    card.addEventListener('dragend', handleDragEnd);
  });

  stages.forEach(stage => {
    stage.addEventListener('dragover', handleDragOver);
    stage.addEventListener('drop', handleDrop);
    stage.addEventListener('dragleave', handleDragLeave);
  });
}

function handleDragStart(e) {
  e.target.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/html', e.target.innerHTML);
  e.dataTransfer.setData('jobId', e.target.dataset.jobId);
}

function handleDragEnd(e) {
  e.target.classList.remove('dragging');
}

function handleDragOver(e) {
  if (e.preventDefault) {
    e.preventDefault();
  }
  e.dataTransfer.dropEffect = 'move';
  e.currentTarget.classList.add('drag-over');
  return false;
}

function handleDragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}

function handleDrop(e) {
  if (e.stopPropagation) {
    e.stopPropagation();
  }
  e.preventDefault();

  e.currentTarget.classList.remove('drag-over');

  const jobId = e.dataTransfer.getData('jobId');
  const newStage = e.currentTarget.closest('.stage-column').dataset.stage;

  // Update job status
  updateJobStatus(jobId, newStage);

  return false;
}

function updateJobStatus(jobId, newStatus) {
  fetch(`/api/tracker/job/${jobId}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: newStatus })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        loadAllJobs(); // Reload to show updated position
      } else {
        console.error('Failed to update status:', data.error);
      }
    })
    .catch(error => console.error('Error updating status:', error));
}

function showJobDetails(jobId) {
  currentJobId = jobId;

  fetch(`/api/tracker/job/${jobId}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const job = data.job;
        const stars = '⭐'.repeat(job.excitement || 0);

        document.getElementById('jobDetailTitle').textContent = job.title;
        document.getElementById('jobDetailBody').innerHTML = `
        <div class="row g-4">
          <div class="col-md-6">
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase">${tHtml("Empresa")}</label>
              <div class="fs-5">${job.company}</div>
            </div>
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase">${tHtml("Ubicación")}</label>
              <div><i class="bi bi-geo-alt me-2"></i> ${job.location || t("No especificada")}</div>
            </div>
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase">${tHtml("Salario")}</label>
              <div class="text-success fw-bold"><i class="bi bi-currency-dollar me-2"></i> ${job.salary || t("No especificado")}</div>
            </div>
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase">${tHtml("Estado Actual")}</label>
              <div><span class="badge bg-primary">${job.status}</span></div>
            </div>
          </div>
          <div class="col-md-6">
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase">${tHtml("Fechas")}</label>
              <div class="small">
                <div class="mb-1">${tHtml("Guardado:")} ${new Date(job.date_saved || job.created_at).toLocaleDateString()}</div>
                <div class="mb-1">Aplicado: ${(job.date_applied || job.applied_date) ? new Date(job.date_applied || job.applied_date).toLocaleDateString() : t("Pendiente")}</div>
              </div>
            </div>
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase" for="detailFollowUp">${tHtml("Recordar seguimiento el")}</label>
              <input type="date" class="form-control form-control-sm" id="detailFollowUp" value="${escapeHtml((job.follow_up || '').slice(0, 10))}">
            </div>
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase" for="detailDeadline">${tHtml("Fecha límite")}</label>
              <input type="date" class="form-control form-control-sm" id="detailDeadline" value="${escapeHtml((job.deadline || '').slice(0, 10))}">
            </div>
            <div class="mb-3">
              <label class="small text-muted fw-bold text-uppercase">${tHtml("Interés")}</label>
              <div class="text-warning">${stars}</div>
            </div>
          </div>
          <div class="col-12">
            <div class="p-3 bg-light rounded">
              <label class="small text-muted fw-bold text-uppercase mb-2">${tHtml("Enlace")}</label>
              <div class="text-truncate">
                <a href="${job.job_link}" target="_blank" class="text-decoration-none">
                  <i class="bi bi-box-arrow-up-right me-2"></i> ${job.job_link}
                </a>
              </div>
            </div>
          </div>
          <div class="col-12">
            <label class="small text-muted fw-bold text-uppercase" for="detailNotes">${tHtml("Notas")}</label>
            <textarea class="form-control" id="detailNotes" rows="3">${escapeHtml(job.notes || '')}</textarea>
            <div class="d-flex align-items-center gap-2 mt-2">
              <button type="button" class="btn btn-sm btn-primary" data-onclick="saveReminder">
                <i class="bi bi-alarm me-1" aria-hidden="true"></i> Guardar fechas y notas
              </button>
              <span id="reminderStatus" class="small" role="status"></span>
            </div>
          </div>
        </div>
      `;

        new bootstrap.Modal(document.getElementById('jobDetailModal')).show();
      }
    });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

function saveReminder() {
  const status = document.getElementById('reminderStatus');
  fetch(`/api/tracker/job/${currentJobId}/reminder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      follow_up: document.getElementById('detailFollowUp').value || null,
      deadline: document.getElementById('detailDeadline').value || null,
      notes: document.getElementById('detailNotes').value
    })
  })
    .then(response => response.json())
    .then(data => {
      status.className = data.success ? 'small text-success' : 'small text-danger';
      status.textContent = data.success ? t("Guardado") : (data.error || t("No se pudo guardar"));
      if (data.success) loadAllJobs();
    });
}

function saveManualJob() {
  const form = document.getElementById('addJobForm');
  const formData = new FormData(form);

  const jobData = {
    title: formData.get('title'),
    company: formData.get('company'),
    location: formData.get('location') || 'Not specified',
    salary: formData.get('salary') || 'Not specified',
    job_link: formData.get('job_link') || '',
    status: formData.get('status'),
    excitement: parseInt(formData.get('excitement')) || 0,
    follow_up: formData.get('follow_up') || null,
    deadline: formData.get('deadline') || null
  };

  fetch('/api/tracker/job', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(jobData)
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        bootstrap.Modal.getInstance(document.getElementById('addJobModal')).hide();
        form.reset();
        loadAllJobs();
        if (data.warning) alert(data.warning);
      } else {
        alert(data.error || data.message || t("No se pudo agregar la postulación"));
      }
    });
}

function deleteJob() {
  if (!currentJobId) return;

  if (confirm(t("¿Estás seguro de eliminar este empleo?"))) {
    fetch(`/api/tracker/job/${currentJobId}`, {
      method: 'DELETE'
    })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          bootstrap.Modal.getInstance(document.getElementById('jobDetailModal')).hide();
          loadAllJobs();
        }
      });
  }
}

function toggleCompactView() {
  const cards = document.querySelectorAll('.job-card');
  const isCompact = localStorage.getItem('trackerCompactView') === 'true';
  const newState = !isCompact;

  cards.forEach(card => {
    if (newState) {
      card.classList.add('compact');
    } else {
      card.classList.remove('compact');
    }
  });

  localStorage.setItem('trackerCompactView', newState);
  updateToggleButton(newState);
}

function updateToggleButton(isCompact) {
  const btn = document.getElementById('toggleCompactView');
  if (isCompact) {
    btn.classList.add('active', 'bg-secondary', 'text-white');
    btn.innerHTML = '<i class="bi bi-grid me-2"></i> ' + tHtml("Vista Normal");
  } else {
    btn.classList.remove('active', 'bg-secondary', 'text-white');
    btn.innerHTML = '<i class="bi bi-list-ul me-2"></i> ' + tHtml("Vista Compacta");
  }
}
