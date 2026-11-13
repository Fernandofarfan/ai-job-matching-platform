document.addEventListener('DOMContentLoaded', function () {
    pollConnectionStatus();
});

function pollConnectionStatus() {
    fetch('/status')
        .then(response => response.json())
        .then(data => {
            updateConnectionStatusUI(data.connection_requests);
            setTimeout(pollConnectionStatus, 2000);
        })
        .catch(error => {
            console.error('Error al verificar estado:', error);
            setTimeout(pollConnectionStatus, 5000);
        });
}

function updateConnectionStatusUI(jobData) {
    const statusElem = document.getElementById('connection-status');
    const progressElem = document.getElementById('connection-progress');
    const messageElem = document.getElementById('connection-message');
    const stopForm = document.getElementById('stop-form');

    if (!jobData) return;

    const statusTranslations = {
        'idle': t('Inactivo'),
        'running': t('Ejecutando'),
        'completed': t('Completado'),
        'failed': t('Falló'),
        'stopped': t('Detenido')
    };
    const statusText = statusTranslations[jobData.status] || jobData.status;

    statusElem.textContent = statusText.charAt(0).toUpperCase() + statusText.slice(1);
    statusElem.className = 'badge';

    // Show/Hide Stop Button
    if (jobData.status === 'running') {
        stopForm.style.display = 'inline-block';
    } else {
        stopForm.style.display = 'none';
    }

    if (jobData.status === 'running') {
        statusElem.classList.add('bg-primary', 'animate-pulse');
        progressElem.classList.add('progress-bar-striped', 'progress-bar-animated');
    } else if (jobData.status === 'completed') {
        statusElem.classList.add('bg-success');
        progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
    } else if (jobData.status === 'failed') {
        statusElem.classList.add('bg-danger');
        progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
    } else if (jobData.status === 'stopped') {
        statusElem.classList.add('bg-warning', 'text-dark');
        progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
    } else {
        statusElem.classList.add('bg-secondary');
        progressElem.classList.remove('progress-bar-striped', 'progress-bar-animated');
    }

    progressElem.style.width = `${jobData.progress}%`;
    progressElem.setAttribute('aria-valuenow', jobData.progress);
    messageElem.textContent = jobData.message;
}

function toggleSearchMode() {
    const mode = document.querySelector('input[name="search_mode"]:checked').value;
    const generalInput = document.getElementById('general_search_input');
    const companyList = document.getElementById('company_list_container');
    const submitBtn = document.getElementById('connection-submit-btn');

    if (mode === 'general') {
        generalInput.style.display = 'block';
        companyList.style.display = 'none';
        submitBtn.disabled = false; // Always enable for general search (validation on submit)
    } else {
        generalInput.style.display = 'none';
        companyList.style.display = 'block';
        // Re-evaluate disabled state based on company list presence
        const hasCompanies = companyList.querySelectorAll('input[type="checkbox"]').length > 0;
        submitBtn.disabled = !hasCompanies;
    }
}

function excludeCompany(companyName, btnElement) {
    if (!confirm(t('¿Querés sacar a %(company)s de la lista de networking?').replace('%(company)s', companyName))) {
        return;
    }

    const formData = new FormData();
    formData.append('company_name', companyName);

    fetch('/exclude_company_from_networking', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove the element from the DOM with a fade out effect
            const row = btnElement.closest('.form-check');
            row.style.transition = 'opacity 0.3s ease';
            row.style.opacity = '0';
            setTimeout(() => row.remove(), 300);
        } else {
            alert(t('No se pudo sacar la empresa:') + ' ' + (data.error || t('Error desconocido')));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(t('Error de conexión'));
    });
}
