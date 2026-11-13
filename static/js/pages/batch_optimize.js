// sin archivos de búsqueda no se muestra el botón
document.getElementById('start_optimization')?.addEventListener('click', function () {
  const filename = document.getElementById('job_file_select').value;
  const numJobs = parseInt(document.getElementById('num_jobs').value) || 5;
  const btn = this;

  if (!filename) {
    alert(t('Por favor seleccioná un archivo de empleos'));
    return;
  }

  // UI Updates
  const statusDiv = document.getElementById('optimization_status');
  const resultsDiv = document.getElementById('optimization_results');
  const emptyState = document.getElementById('empty-state');
  const progressBar = document.getElementById('optimization_progress');
  const messageEl = document.getElementById('optimization_message');
  const percentageEl = document.getElementById('progress-percentage');
  const resultsList = document.getElementById('results_list');
  const statusBadge = document.getElementById('status-badge');

  statusDiv.style.display = 'block';
  resultsDiv.style.display = 'none';
  emptyState.style.display = 'none';
  progressBar.style.width = '10%';
  percentageEl.textContent = '10%';
  messageEl.textContent = t('Analizando CV y ofertas...');

  statusBadge.className = 'badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25 animate-pulse';
  statusBadge.textContent = t('Optimizando...');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> ' + tHtml('Procesando...');

  const showProgress = (pct, msg) => {
    progressBar.style.width = `${pct}%`;
    percentageEl.textContent = `${pct}%`;
    messageEl.textContent = msg;
  };
  runDocumentBatch('/api/batch_optimize', { filename: filename, num_jobs: numJobs }, showProgress)
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
      btn.innerHTML = '<i class="bi bi-magic me-2"></i> ' + tHtml('Optimizar CVs');
    });
});
