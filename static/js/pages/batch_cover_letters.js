// ── Tone selector visual toggle ──────────
document.querySelectorAll('.tone-option').forEach(option => {
  option.addEventListener('click', () => {
    document.querySelectorAll('.tone-option').forEach(o => o.classList.remove('selected'));
    option.classList.add('selected');
    option.querySelector('input[type="radio"]').checked = true;
  });
});

// ── Generate button ──────────────────────
// sin archivos de búsqueda no se muestra el botón
document.getElementById('start_generation')?.addEventListener('click', function () {
  const filename = document.getElementById('job_file_select').value;
  const numJobs  = parseInt(document.getElementById('num_jobs').value) || 5;
  const tone     = document.querySelector('input[name="tone"]:checked')?.value || 'profesional';
  const btn      = this;

  if (!filename) { alert(t('Por favor seleccioná un archivo de empleos')); return; }

  const statusDiv   = document.getElementById('generation_status');
  const resultsDiv  = document.getElementById('generation_results');
  const emptyState  = document.getElementById('empty-state');
  const progressBar = document.getElementById('generation_progress');
  const messageEl   = document.getElementById('generation_message');
  const percentageEl= document.getElementById('progress-percentage');
  const resultsList = document.getElementById('results_list');
  const statusBadge = document.getElementById('status-badge');

  statusDiv.style.display  = 'block';
  resultsDiv.style.display = 'none';
  emptyState.style.display = 'none';
  progressBar.style.width  = '10%';
  percentageEl.textContent = '10%';
  messageEl.textContent    = t('Analizando CV y generando cartas (tono: %(tone)s)...').replace('%(tone)s', tone);
  statusBadge.className    = 'badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25';
  statusBadge.textContent  = 'Generando...';
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> ' + tHtml('Procesando...');

  const showProgress = (pct, msg) => {
    progressBar.style.width = `${pct}%`;
    percentageEl.textContent = `${pct}%`;
    messageEl.textContent = msg;
  };
  runDocumentBatch('/api/batch_cover_letters', { filename, num_jobs: numJobs, tone }, showProgress)
    .then(data => {
      showProgress(100, t('¡Proceso finalizado!'));
      progressBar.classList.remove('progress-bar-striped', 'progress-bar-animated');
      progressBar.classList.add('bg-success');
      statusBadge.className = 'badge bg-success bg-opacity-10 text-success border border-success border-opacity-25';
      statusBadge.textContent = t('Completado');
      renderDocumentRows(resultsList, data.results);
      resultsDiv.style.display = 'block';
    })
    .catch(error => {
      messageEl.textContent = 'Error: ' + error.message;
      progressBar.classList.add('bg-danger');
      statusBadge.className = 'badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25';
      statusBadge.textContent = 'Error';
    })
    .finally(() => {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-magic me-2"></i> ' + tHtml('Generar Cartas con IA');
    });
});

// ── Preview modal ─────────────────────────
function showPreview(btn) {
  const text = decodeURIComponent(btn.dataset.preview);
  const job  = btn.dataset.job || t('Carta');
  document.getElementById('previewModalTitle').textContent = `${t('Vista previa')} — ${job}`;
  document.getElementById('previewModalBody').textContent  = text;
  new bootstrap.Modal(document.getElementById('previewModal')).show();
}
