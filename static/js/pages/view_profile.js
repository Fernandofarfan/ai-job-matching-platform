function togglePreview() {
  const preview = document.getElementById('resumePreview');
  const icon = document.getElementById('expandIcon');

  preview.classList.toggle('expanded');

  if (preview.classList.contains('expanded')) {
    icon.className = 'bi bi-arrows-angle-contract';
  } else {
    icon.className = 'bi bi-arrows-angle-expand';
  }
}

// Add fade-in animation on load
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.card, .stat-card, .alert').forEach((el, index) => {
    el.style.animationDelay = `${index * 0.1}s`;
    el.classList.add('fade-in');
  });
});
