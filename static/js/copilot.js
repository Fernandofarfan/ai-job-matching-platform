let copilotHistory = [];
let copilotOpen = false;
let copilotTyping = false;

function toggleCopilot() {
    copilotOpen ? closeCopilot() : openCopilot();
}

function openCopilot() {
    copilotOpen = true;
    document.getElementById('copilot-sidebar').classList.add('open');
    document.getElementById('copilot-toggle-btn').classList.add('sidebar-open');
    document.getElementById('copilot-input').focus();
    // Show overlay on mobile
    if (window.innerWidth <= 768) {
        document.getElementById('copilot-overlay').style.display = 'block';
    }
}

function closeCopilot() {
    copilotOpen = false;
    document.getElementById('copilot-sidebar').classList.remove('open');
    document.getElementById('copilot-toggle-btn').classList.remove('sidebar-open');
    document.getElementById('copilot-overlay').style.display = 'none';
}

function quickAction(text) {
    document.getElementById('copilot-input').value = text;
    sendCopilotMessage();
}

function handleCopilotKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendCopilotMessage();
    }
}

function autoResizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

async function sendCopilotMessage() {
    if (copilotTyping) return;
    const input = document.getElementById('copilot-input');
    const message = input.value.trim();
    if (!message) return;

    // Add user message
    appendCopilotMessage('user', message);
    input.value = '';
    input.style.height = 'auto';
    copilotHistory.push({ role: 'user', content: message });

    // Show typing indicator
    copilotTyping = true;
    document.getElementById('copilot-send-btn').disabled = true;
    const typingId = appendTypingIndicator();
    setStatus('Pensando...', true);

    try {
        const response = await fetch('/api/ai/copilot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                history: copilotHistory.slice(-8)
            })
        });
        const data = await response.json();
        const reply = data.reply || 'No pude generar una respuesta.';

        removeTypingIndicator(typingId);
        appendCopilotMessage('assistant', reply);
        copilotHistory.push({ role: 'assistant', content: reply });

    } catch (error) {
        removeTypingIndicator(typingId);
        appendCopilotMessage('assistant', '❌ Error de conexión. Verificá que EmpleoIA esté corriendo.');
    } finally {
        copilotTyping = false;
        document.getElementById('copilot-send-btn').disabled = false;
        setStatus('Presioná Enter para enviar · Shift+Enter para nueva línea', false);
    }
}

function appendCopilotMessage(role, text) {
    const container = document.getElementById('copilot-messages');
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    const avatar = role === 'assistant' ? '🤖' : '<i class="bi bi-person"></i>';
    // Convert **bold** and line breaks for display
    const escaped = text.replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    const formatted = escaped
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    div.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-bubble">${formatted}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

function appendTypingIndicator() {
    const container = document.getElementById('copilot-messages');
    const id = 'typing-' + Date.now();
    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.id = id;
    div.innerHTML = `
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble">
            <div class="msg-typing">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function setStatus(text, active) {
    const status = document.getElementById('copilot-status');
    status.textContent = text;
    status.className = 'copilot-status' + (active ? ' active' : '');
}
