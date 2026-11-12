// Lanza un lote de cartas/CVs y, si el servidor lo encola en Celery (202), consulta el progreso.
async function runDocumentBatch(url, body, onProgress) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  let data = await response.json();
  if (!response.ok && response.status !== 202) throw new Error(data.error || 'Error desconocido');
  if (!data.task_id) return data;
  const taskUrl = `/api/documents/tasks/${encodeURIComponent(data.task_id)}`;
  for (;;) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    const poll = await fetch(taskUrl);
    data = await poll.json();
    if (!poll.ok || data.state === 'failed') throw new Error(data.error || 'Error desconocido');
    if (data.state === 'completed') return data;
    onProgress(data.progress || 0, data.message || (data.state === 'queued' ? 'En cola...' : 'Generando...'));
  }
}

// Filas de resultados armadas con textContent: títulos y empresas vienen de portales externos.
function renderDocumentRows(tbody, results) {
  tbody.replaceChildren(...results.map(result => {
    const ok = result.status === 'success';
    const tr = document.createElement('tr');
    const title = document.createElement('td');
    title.className = 'ps-3 fw-medium';
    title.textContent = result.job_title;
    const company = document.createElement('td');
    company.className = 'text-muted';
    company.textContent = result.company;
    const state = document.createElement('td');
    state.className = 'text-center';
    const badge = document.createElement('span');
    badge.className = `badge bg-opacity-10 border border-opacity-25 ${ok ? 'bg-success text-success border-success' : 'bg-danger text-danger border-danger'}`;
    badge.textContent = ok ? 'Éxito' : 'Error';
    state.appendChild(badge);
    const action = document.createElement('td');
    action.className = 'pe-3 text-end';
    if (ok && result.filename) {
      const link = document.createElement('a');
      link.href = `/download_resume/${encodeURIComponent(result.filename)}`;
      link.className = 'btn btn-sm btn-primary';
      link.innerHTML = '<i class="bi bi-download me-1" aria-hidden="true"></i>Descargar';
      action.appendChild(link);
    } else {
      action.classList.add('text-muted', 'small');
      action.textContent = result.error || 'Fallido';
    }
    tr.append(title, company, state, action);
    return tr;
  }));
}
