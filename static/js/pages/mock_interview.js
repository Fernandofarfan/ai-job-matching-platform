// ── State ──────────────────────────────────────────────────────────────────
let interviewState = {
    questions: [],
    currentIndex: 0,
    answers: [],
    scores: [],
    jobTitle: '',
    company: '',
    jobDescription: '',
    difficulty: 'medio',
    mode: 'text',
    totalQuestions: 10,
    timer: null,
    timerSeconds: 120,
};

// ── Setup ──────────────────────────────────────────────────────────────────

// Difficulty buttons
document.querySelectorAll('.diff-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.diff-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        interviewState.difficulty = btn.dataset.diff;
    });
});

// Mode selector
document.querySelectorAll('input[name="interview-mode"]').forEach(radio => {
    radio.addEventListener('change', () => {
        document.querySelectorAll('.mode-option').forEach(m => m.classList.remove('active'));
        radio.parentElement.classList.add('active');
        interviewState.mode = radio.value;
    });
});

// Questions count slider
const slider = document.getElementById('questions-count');
const label = document.getElementById('questions-label');
slider.addEventListener('input', () => {
    label.textContent = slider.value;
    interviewState.totalQuestions = parseInt(slider.value);
});

// Populate from tracker job selector
document.getElementById('tracker-job-select').addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    if (opt.value) {
        document.getElementById('manual-title').value = opt.dataset.title || '';
        document.getElementById('manual-company').value = opt.dataset.company || '';
        document.getElementById('manual-description').value = opt.dataset.description || '';
    }
});

// ── Start Interview ────────────────────────────────────────────────────────
async function startInterview() {
    const title = document.getElementById('manual-title').value.trim();
    const company = document.getElementById('manual-company').value.trim();
    const description = document.getElementById('manual-description').value.trim();

    if (!title) {
        showToast('⚠️ ' + t('Ingresá el título del puesto para comenzar'), 'warning');
        return;
    }

    interviewState.jobTitle = title;
    interviewState.company = company;
    interviewState.jobDescription = description;
    interviewState.currentIndex = 0;
    interviewState.answers = [];
    interviewState.scores = [];

    const btn = document.getElementById('start-interview-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> ' + tHtml('Generando preguntas...');

    try {
        const response = await fetch('/api/ai/interview/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_title: title,
                job_description: description,
                difficulty: interviewState.difficulty,
            })
        });
        const data = await response.json();

        if (data.success && data.questions) {
            interviewState.questions = data.questions.slice(0, interviewState.totalQuestions);
            showInterviewPanel();
            loadQuestion(0);
        } else {
            showToast(t('Error al generar preguntas:') + ' ' + (data.error || t('desconocido')), 'danger');
        }
    } catch (error) {
        showToast(t('Error de conexión:') + ' ' + error.message, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-play-circle me-2"></i> ' + tHtml('Comenzar Entrevista');
    }
}

function showInterviewPanel() {
    document.getElementById('setup-panel').classList.add('d-none');
    document.getElementById('interview-panel').classList.remove('d-none');
    document.getElementById('interview-job-title').textContent = interviewState.jobTitle;
    document.getElementById('interview-company').textContent = interviewState.company;
}

function loadQuestion(index) {
    const q = interviewState.questions[index];
    if (!q) return;

    const total = interviewState.questions.length;

    document.getElementById('question-badge').textContent = t('Pregunta %(n)s/%(total)s').replace('%(n)s', index + 1).replace('%(total)s', total);
    document.getElementById('question-type-badge').textContent = capitalize(q.tipo || t('técnica'));
    document.getElementById('question-text').textContent = q.pregunta;
    document.getElementById('hint-text').textContent = q.pista_respuesta || '';
    document.getElementById('user-answer').value = '';
    document.getElementById('question-progress').style.width = `${((index + 1) / total) * 100}%`;
    document.getElementById('question-hint').classList.add('d-none');
    document.getElementById('hint-btn').innerHTML = '<i class="bi bi-lightbulb me-1"></i> ' + tHtml('Ver pista');

    // Hide feedback if showing
    document.getElementById('feedback-modal').classList.add('d-none');

    // Start timer if timed mode
    if (interviewState.mode === 'timed') {
        startTimer(parseInt(q.tiempo_sugerido) || 120);
    }

    document.getElementById('user-answer').focus();
}

function toggleHint() {
    const hint = document.getElementById('question-hint');
    const btn = document.getElementById('hint-btn');
    if (hint.classList.contains('d-none')) {
        hint.classList.remove('d-none');
        btn.innerHTML = '<i class="bi bi-lightbulb-fill me-1 text-warning"></i> ' + tHtml('Ocultar pista');
    } else {
        hint.classList.add('d-none');
        btn.innerHTML = '<i class="bi bi-lightbulb me-1"></i> ' + tHtml('Ver pista');
    }
}

function startTimer(seconds) {
    clearInterval(interviewState.timer);
    interviewState.timerSeconds = seconds;
    const display = document.getElementById('timer-value');
    const timerEl = document.getElementById('timer-display');
    timerEl.classList.remove('d-none');

    interviewState.timer = setInterval(() => {
        interviewState.timerSeconds--;
        const m = Math.floor(interviewState.timerSeconds / 60);
        const s = interviewState.timerSeconds % 60;
        display.textContent = `${m}:${s.toString().padStart(2, '0')}`;
        if (interviewState.timerSeconds <= 10) {
            timerEl.classList.add('timer-urgent');
        }
        if (interviewState.timerSeconds <= 0) {
            clearInterval(interviewState.timer);
            submitAnswer();
        }
    }, 1000);
}

// ── Answer Submission ──────────────────────────────────────────────────────
async function submitAnswer() {
    clearInterval(interviewState.timer);
    const answer = document.getElementById('user-answer').value.trim();
    const q = interviewState.questions[interviewState.currentIndex];

    if (!answer) {
        showToast('⚠️ ' + t('Escribí algo antes de enviar'), 'warning');
        return;
    }

    const btn = document.getElementById('submit-answer-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> ' + tHtml('Evaluando...');

    try {
        const response = await fetch('/api/ai/interview/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: q.pregunta,
                answer: answer,
                job_title: interviewState.jobTitle,
            })
        });
        const data = await response.json();

        if (data.success) {
            const evaluation = data.evaluation;
            interviewState.answers.push({ question: q, answer, evaluation });
            interviewState.scores.push(evaluation.puntaje || 5);
            showFeedback(evaluation);
            addToHistory(interviewState.currentIndex, evaluation.puntaje);
        } else {
            showToast(t('Error al evaluar:') + ' ' + (data.error || ''), 'danger');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-send me-2"></i> ' + tHtml('Enviar y ver feedback');
    }
}

function showFeedback(eval_data) {
    document.getElementById('feedback-score').textContent = (eval_data.puntaje || 0).toFixed(1);
    document.getElementById('feedback-stars').textContent = '★'.repeat(Math.round(eval_data.puntaje / 2)) +
        '☆'.repeat(5 - Math.round(eval_data.puntaje / 2));

    const strengthsList = document.getElementById('feedback-strengths');
    strengthsList.innerHTML = (eval_data.fortalezas || []).map(f => `<li>${escapeHtml(f)}</li>`).join('');

    const improvList = document.getElementById('feedback-improvements');
    improvList.innerHTML = (eval_data.areas_mejora || []).map(a => `<li>${escapeHtml(a)}</li>`).join('');

    document.getElementById('feedback-improved').textContent = eval_data.respuesta_mejorada || '';
    document.getElementById('feedback-advice').textContent = eval_data.consejo_clave || '';
    document.getElementById('feedback-modal').classList.remove('d-none');
}

function addToHistory(index, score) {
    const history = document.getElementById('answers-history');
    const q = interviewState.questions[index];
    const scoreColor = score >= 7 ? '#22c55e' : score >= 5 ? '#f59e0b' : '#ef4444';
    const item = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = `
        <div class="d-flex justify-content-between align-items-center p-2 border-bottom" style="border-color:rgba(255,255,255,0.05)!important;">
            <small class="text-muted text-truncate pe-2" style="max-width:70%;">P${index + 1}: ${escapeHtml(q.pregunta.substring(0, 50))}...</small>
            <span class="badge" style="background:${scoreColor};min-width:42px;">${score.toFixed(1)}</span>
        </div>`;
    if (history.querySelector('p')) history.innerHTML = '';
    history.appendChild(item);
}

function nextQuestion() {
    document.getElementById('feedback-modal').classList.add('d-none');
    interviewState.currentIndex++;

    if (interviewState.currentIndex >= interviewState.questions.length) {
        showResults();
    } else {
        loadQuestion(interviewState.currentIndex);
    }
}

function skipQuestion() {
    interviewState.answers.push({
        question: interviewState.questions[interviewState.currentIndex],
        answer: '',
        evaluation: { puntaje: 0 }
    });
    interviewState.scores.push(0);
    nextQuestion();
}

function showResults() {
    clearInterval(interviewState.timer);
    document.getElementById('interview-panel').classList.add('d-none');
    document.getElementById('results-panel').classList.remove('d-none');

    const avg = interviewState.scores.length > 0
        ? interviewState.scores.reduce((a, b) => a + b, 0) / interviewState.scores.length
        : 0;

    document.getElementById('final-score-text').textContent = avg.toFixed(1);
    drawScoreChart(avg);
}

function drawScoreChart(score) {
    const canvas = document.getElementById('score-chart');
    const ctx = canvas.getContext('2d');
    const angle = (score / 10) * 2 * Math.PI;

    ctx.clearRect(0, 0, 200, 200);
    // Background ring
    ctx.beginPath();
    ctx.arc(100, 100, 80, 0, 2 * Math.PI);
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    ctx.lineWidth = 15;
    ctx.stroke();
    // Score ring
    ctx.beginPath();
    ctx.arc(100, 100, 80, -Math.PI / 2, -Math.PI / 2 + angle);
    const gradient = ctx.createLinearGradient(0, 0, 200, 200);
    gradient.addColorStop(0, '#667eea');
    gradient.addColorStop(1, '#764ba2');
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 15;
    ctx.lineCap = 'round';
    ctx.stroke();
}

function endInterview() {
    if (!confirm(t('¿Terminás la entrevista? Se perderán las últimas respuestas sin enviar.'))) return;
    if (interviewState.answers.length > 0) {
        showResults();
    } else {
        startNewInterview();
    }
}

function startNewInterview() {
    clearInterval(interviewState.timer);
    document.getElementById('results-panel').classList.add('d-none');
    document.getElementById('setup-panel').classList.remove('d-none');
    document.getElementById('interview-panel').classList.add('d-none');
    document.getElementById('answers-history').innerHTML = '<p class="text-muted text-center py-3 px-3 mb-0"><small>' + tHtml('Las respuestas evaluadas aparecerán aquí') + '</small></p>';
    interviewState = { ...interviewState, questions: [], currentIndex: 0, answers: [], scores: [] };
}

function downloadResults() {
    const data = {
        job: interviewState.jobTitle,
        company: interviewState.company,
        date: new Date().toLocaleDateString('es-AR'),
        score: (interviewState.scores.reduce((a,b)=>a+b,0)/interviewState.scores.length).toFixed(1),
        qa: interviewState.answers.map((a, i) => ({
            pregunta: a.question.pregunta,
            respuesta: a.answer,
            puntaje: a.evaluation.puntaje,
            feedback: a.evaluation.consejo_clave,
        }))
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `entrevista_${interviewState.jobTitle.replace(/\s+/g, '_')}_${Date.now()}.json`;
    a.click();
}

// ── Utilities ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

function capitalize(str) { return str ? str.charAt(0).toUpperCase() + str.slice(1) : ''; }

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} position-fixed bottom-0 end-0 m-3 shadow`;
    toast.style.cssText = 'z-index:9999;border-radius:12px;min-width:280px;';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}
// ── Web Speech API (Voice API) ───────────────────────────────────────────
let recognition;
let isRecording = false;

if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'es-AR';

    recognition.onresult = function(event) {
        let finalTranscript = '';
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }

        const textArea = document.getElementById('user-answer');
        if (finalTranscript) {
            textArea.value += (textArea.value ? ' ' : '') + finalTranscript;
        }
    };

    recognition.onerror = function(event) {
        console.error("Speech Recognition Error", event.error);
        if (event.error === 'not-allowed') {
            showToast('⚠️ ' + t('Permiso de micrófono denegado'), 'danger');
            toggleVoiceRecording(true);
        }
    };

    recognition.onend = function() {
        if (isRecording) { // If it stopped automatically but we still want recording
            recognition.start();
        }
    };
}

function toggleVoiceRecording(forceStop = false) {
    if (!recognition) {
        showToast('🎙️ ' + t('Tu navegador no soporta reconocimiento de voz'), 'warning');
        return;
    }

    const btn = document.getElementById('voice-btn');
    if (isRecording || forceStop) {
        isRecording = false;
        recognition.stop();
        btn.innerHTML = '<i class="bi bi-mic me-1"></i> ' + tHtml('Hablar');
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-outline-danger');
    } else {
        isRecording = true;
        recognition.start();
        btn.innerHTML = '<i class="bi bi-stop-circle me-1"></i> ' + tHtml('Detener grabación');
        btn.classList.remove('btn-outline-danger');
        btn.classList.add('btn-danger');
        showToast('🎙️ ' + t('Grabando... Empezá a hablar'), 'info');
    }
}
