/**
 * Мой AI Бот — клиентская логика чата с поддержкой файлов
 */

const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const modelSelect = document.getElementById('model-select');
const clearBtn = document.getElementById('clear-btn');
const filesBtn = document.getElementById('files-btn');
const filesPanel = document.getElementById('files-panel');
const filesList = document.getElementById('files-list');
const closeFilesBtn = document.getElementById('close-files-btn');
const fileInput = document.getElementById('file-input');
const statusBar = document.getElementById('status-bar');
const statusText = document.getElementById('status-text');
const botTitle = document.getElementById('bot-title');

let conversationHistory = [];
let isGenerating = false;

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadModels();
    checkHealth();
    autoResizeTextarea();
    setupFileHandlers();
});

// Загрузка конфигурации
async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        if (data.title) {
            botTitle.textContent = '🤖 ' + data.title;
            document.title = data.title;
        }
    } catch (e) {
        console.error('Ошибка загрузки конфига:', e);
    }
}

// Загрузка списка моделей
async function loadModels() {
    try {
        const res = await fetch('/api/models');
        const data = await res.json();
        modelSelect.innerHTML = '';

        if (data.models.length === 0) {
            modelSelect.innerHTML = '<option value="">Нет моделей</option>';
            return;
        }

        data.models.forEach(model => {
            const opt = document.createElement('option');
            opt.value = model;
            opt.textContent = model;
            if (model === data.current) opt.selected = true;
            modelSelect.appendChild(opt);
        });
    } catch (e) {
        modelSelect.innerHTML = '<option value="">Ошибка загрузки</option>';
    }
}

// Проверка здоровья
async function checkHealth() {
    try {
        const res = await fetch('/api/health');
        const data = await res.json();

        if (!data.ollama) {
            showStatus('⚠️ Ollama недоступна. Убедитесь, что Ollama запущена.');
        }
    } catch (e) {
        showStatus('⚠️ Сервер недоступен');
    }
}

// === ФАЙЛЫ ===

function setupFileHandlers() {
    // Кнопка открытия панели файлов
    filesBtn.addEventListener('click', () => {
        filesPanel.style.display = filesPanel.style.display === 'none' ? 'block' : 'none';
        if (filesPanel.style.display === 'block') loadFilesList();
    });

    closeFilesBtn.addEventListener('click', () => {
        filesPanel.style.display = 'none';
    });

    // Загрузка файлов
    fileInput.addEventListener('change', async (e) => {
        const files = e.target.files;
        if (!files.length) return;

        for (const file of files) {
            await uploadFile(file);
        }
        fileInput.value = '';
    });
}

async function uploadFile(file) {
    showStatus(`📤 Загрузка: ${file.name}...`);

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        if (data.status === 'ok') {
            const fileInfo = data.file;
            const sizeStr = formatFileSize(fileInfo.size);

            // Показать в чате
            addMessage('user', `📎 Загружен файл: ${fileInfo.original_name} (${sizeStr})`);

            // Сообщить боту о файле
            conversationHistory.push({
                role: 'user',
                content: `Я загрузил файл: "${fileInfo.original_name}" (${sizeStr}, тип: ${fileInfo.content_type}). Файл доступен для скачивания.`
            });

            await generateResponse();
            hideStatus();
        } else {
            addMessage('bot', `❌ Ошибка загрузки: ${data.message}`);
            hideStatus();
        }
    } catch (e) {
        addMessage('bot', `❌ Ошибка загрузки файла: ${e.message}`);
        hideStatus();
    }
}

async function loadFilesList() {
    try {
        const res = await fetch('/api/files');
        const data = await res.json();

        if (data.files.length === 0) {
            filesList.innerHTML = '<p class="no-files">Нет загруженных файлов</p>';
            return;
        }

        filesList.innerHTML = data.files.map(f => `
            <div class="file-item">
                <span class="file-name">${f.name}</span>
                <span class="file-size">${formatFileSize(f.size)}</span>
                <div class="file-actions">
                    <a href="/api/files/${f.id}" download class="file-download" title="Скачать">⬇️</a>
                    <button onclick="deleteFileItem('${f.id}')" class="file-delete" title="Удалить">🗑️</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        filesList.innerHTML = '<p class="no-files">Ошибка загрузки списка</p>';
    }
}

async function deleteFileItem(fileId) {
    try {
        await fetch(`/api/files/${fileId}`, { method: 'DELETE' });
        loadFilesList();
    } catch (e) {
        console.error('Ошибка удаления:', e);
    }
}

// === ЧАТ ===

// Отправка сообщения
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = userInput.value.trim();
    if (!text || isGenerating) return;

    addMessage('user', text);
    conversationHistory.push({ role: 'user', content: text });
    userInput.value = '';
    userInput.style.height = 'auto';

    await generateResponse();
});

// Генерация ответа (стриминг)
async function generateResponse() {
    isGenerating = true;
    sendBtn.disabled = true;
    showStatus('💭 Бот думает...');

    const botMessageEl = addMessage('bot', '');
    const contentEl = botMessageEl.querySelector('.message-content');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                messages: conversationHistory,
                model: modelSelect.value || null,
            }),
        });

        if (!res.ok) {
            const errText = await res.text();
            throw new Error(errText || `HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            fullResponse += chunk;
            contentEl.textContent = fullResponse;
            scrollToBottom();
        }

        conversationHistory.push({ role: 'assistant', content: fullResponse });
        hideStatus();
    } catch (e) {
        contentEl.textContent = `❌ Ошибка: ${e.message}\n\nУбедитесь, что Ollama запущена и модель загружена.`;
        hideStatus();
    }

    isGenerating = false;
    sendBtn.disabled = false;
    userInput.focus();
}

// Добавление сообщения в чат
function addMessage(role, content) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role === 'user' ? 'user-message' : 'bot-message'}`;
    msgDiv.innerHTML = `<div class="message-content">${escapeHtml(content)}</div>`;
    chatMessages.appendChild(msgDiv);
    scrollToBottom();
    return msgDiv;
}

// Очистка чата
clearBtn.addEventListener('click', () => {
    conversationHistory = [];
    chatMessages.innerHTML = `
        <div class="message bot-message">
            <div class="message-content">Чат очищен. Задай мне новый вопрос! 🚀</div>
        </div>
    `;
});

// Авто-ресайз textarea
function autoResizeTextarea() {
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
    });

    // Enter для отправки, Shift+Enter для новой строки
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });
}

// Утилиты
function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showStatus(text) {
    statusBar.style.display = 'block';
    statusText.textContent = text;
}

function hideStatus() {
    statusBar.style.display = 'none';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' Б';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КБ';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' МБ';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' ГБ';
}
