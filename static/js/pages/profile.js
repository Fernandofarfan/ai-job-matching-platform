document.addEventListener("DOMContentLoaded", function () {
  loadAllProfiles();
  setupDragAndDrop();
});

function setupDragAndDrop() {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('resume');

  dropZone.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
  });

  dropZone.addEventListener('drop', handleDrop, false);
  fileInput.addEventListener('change', handleFileSelect, false);
}

function handleDrop(e) {
  const dt = e.dataTransfer;
  const files = dt.files;
  document.getElementById('resume').files = files;
  handleFileSelect({ target: { files } });
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;

  const dropZoneContent = document.getElementById('dropZoneContent');
  const filePreview = document.getElementById('filePreview');
  const fileName = document.getElementById('fileName');
  const fileSize = document.getElementById('fileSize');

  dropZoneContent.style.display = 'none';
  filePreview.style.display = 'block';

  fileName.textContent = file.name;
  fileSize.textContent = formatFileSize(file.size);

  // Update icon based on file type
  const icon = filePreview.querySelector('.file-icon i');
  if (file.name.endsWith('.pdf')) {
    icon.className = 'bi bi-file-earmark-pdf-fill fs-1 text-danger';
  } else if (file.name.endsWith('.docx')) {
    icon.className = 'bi bi-file-earmark-word-fill fs-1 text-primary';
  } else {
    icon.className = 'bi bi-file-earmark-text-fill fs-1 text-secondary';
  }
}

function openResumePicker() {
  document.getElementById('resume').click();
}

function removeFile() {
  document.getElementById('resume').value = '';
  document.getElementById('dropZoneContent').style.display = 'block';
  document.getElementById('filePreview').style.display = 'none';
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function loadAllProfiles() {
  fetch("/api/all_profiles")
    .then((response) => response.json())
    .then((data) => {
      updateProfilesDisplay(data.profiles);
      updateStatusSummary(data.profiles);
      updateProgressCircle(data.profiles);
    })
    .catch((error) => {
      console.error("Error loading profiles:", error);
      document.getElementById("profilesContainer").innerHTML = `
        <div class="text-center py-5 text-muted">
          <i class="bi bi-exclamation-circle fs-4 d-block mb-2"></i>
          ${tHtml("Error al cargar perfiles.")}
        </div>
      `;
    });
}

function updateProgressCircle(profiles) {
  const total = 5; // Total possible profiles
  const active = Object.keys(profiles).length;
  const percentage = (active / total) * 100;
  const circumference = 339.292;
  const offset = circumference - (percentage / 100) * circumference;

  const circle = document.getElementById('progressCircle');
  circle.style.strokeDashoffset = offset;
}

function updateProfilesDisplay(profiles) {
  const container = document.getElementById("profilesContainer");

  if (Object.keys(profiles).length === 0) {
    container.innerHTML = `
      <div class="text-center py-5 text-muted">
        <i class="bi bi-folder2-open fs-1 d-block mb-3 opacity-50"></i>
        <h6 class="fw-bold">${tHtml("No hay perfiles cargados")}</h6>
        <p class="small mb-0">${tHtml("¡Sube tu primer CV arriba!")}</p>
      </div>
    `;
    return;
  }

  const roleIcons = {
    data_analyst: "📊",
    data_engineer: "⚙️",
    data_scientist: "🔬",
    ai_engineer: "🤖",
    other: "📄",
  };

  const roleNames = {
    data_analyst: "Data Analyst",
    data_engineer: "Data Engineer",
    data_scientist: "Data Scientist",
    ai_engineer: "AI/ML Engineer",
    other: t("Otros"),
  };

  container.innerHTML = "";

  for (const [roleType, profile] of Object.entries(profiles)) {
    const uploadDate = new Date(profile.upload_date).toLocaleDateString('es-AR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
    const skillsCount = profile.skills ? profile.skills.length : 0;
    const resumeFilename = profile.resume_filename || t("Desconocido");

    const card = document.createElement('div');
    card.className = 'profile-card fade-in';
    card.innerHTML = `
      <div class="d-flex align-items-start justify-content-between">
        <div class="d-flex align-items-start gap-3 flex-grow-1">
          <div class="rounded p-3 bg-light fs-1">${roleIcons[roleType] || "📄"}</div>
          <div class="flex-grow-1">
            <div class="d-flex align-items-center gap-2 mb-2">
              <h5 class="fw-bold mb-0">${roleNames[roleType] || roleType}</h5>
              <span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25">
                <i class="bi bi-check-circle me-1"></i>${tHtml("Activo")}
              </span>
            </div>
            <div class="small text-muted mb-2">
              <i class="bi bi-paperclip me-1"></i>${resumeFilename.substring(0, 40)}${resumeFilename.length > 40 ? '...' : ''}
            </div>
            <div class="small text-muted mb-3">
              <i class="bi bi-calendar me-1"></i>${tHtml("Subido:")} ${uploadDate}
            </div>
            ${profile.skills && profile.skills.length > 0 ? `
            <div class="mb-2">
              <div class="small fw-bold text-muted mb-2">${tHtml("Habilidades detectadas:")}</div>
              <div class="d-flex flex-wrap gap-1">
                ${profile.skills.slice(0, 8).map(skill => `
                  <span class="skill-badge">${skill}</span>
                `).join('')}
                ${profile.skills.length > 8 ? `
                  <span class="badge bg-light text-dark border">+${profile.skills.length - 8} más</span>
                ` : ''}
              </div>
            </div>
            ` : ''}
          </div>
        </div>
        <div class="d-flex gap-2">
          <a href="/view_profile/${roleType}" class="btn btn-sm btn-outline-primary" title="${tHtml("Ver Detalles")}">
            <i class="bi bi-eye"></i>
          </a>
          <a href="/delete_profile/${roleType}" class="btn btn-sm btn-outline-danger" 
             title="${tHtml("Eliminar")}" data-confirm="${tHtml("¿Eliminar este perfil?")}">
            <i class="bi bi-trash"></i>
          </a>
        </div>
      </div>
    `;

    container.appendChild(card);
  }
}

function updateStatusSummary(profiles) {
  document.getElementById("total-profiles").textContent = Object.keys(profiles).length;

  const roleKeys = {
    data_analyst: "status-analyst",
    data_engineer: "status-engineer",
    data_scientist: "status-scientist",
    ai_engineer: "status-ai",
    other: "status-other",
  };

  for (const [roleType, elementId] of Object.entries(roleKeys)) {
    const statusElement = document.getElementById(elementId);
    if (statusElement) {
      if (profiles[roleType]) {
        statusElement.textContent = t("Activo");
        statusElement.className = "badge bg-success bg-opacity-10 text-success border border-success border-opacity-25";
        statusElement.innerHTML = '<i class="bi bi-check-circle me-1"></i> ' + tHtml("Activo");
      } else {
        statusElement.textContent = t("Pendiente");
        statusElement.className = "badge bg-light text-muted border";
        statusElement.innerHTML = t("Pendiente");
      }
    }
  }
}
