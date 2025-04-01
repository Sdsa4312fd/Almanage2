document.addEventListener('DOMContentLoaded', () => {
    // Оптимизированный код запуска
    console.log('JS и DOM загружены, готово к работе.');

    // DOM-элементы
    const elements = {
        botScreenshot: document.getElementById('bot-screenshot'),
        statusBadge: document.getElementById('status-badge'),
        logs: document.getElementById('logs'),
        progressBar: document.getElementById('progress-bar'),
        messageCount: document.getElementById('message-count'),
        accountCount: document.getElementById('account-count'),
        accountsList: document.getElementById('accounts-list'),
        proxiesList: document.getElementById('proxies-list'),
        username: document.getElementById('username'),
        password: document.getElementById('password'),
        proxy: document.getElementById('proxy'),
        addAccount: document.getElementById('add-account'),
        addProxy: document.getElementById('add-proxy'),
        checkProxy: document.getElementById('check-proxy'),
        startBot: document.getElementById('start-bot'),
        stopBot: document.getElementById('stop-bot'),
        clearLogs: document.getElementById('clear-logs'),
        message: document.getElementById('message'),
        minAge: document.getElementById('min-age'),
        maxAge: document.getElementById('max-age')
    };

    // Состояние
    const state = {
        accounts: [],
        proxies: [],
        botActive: false,
        screenshotUpdateTime: 0
    };

    // Инициализация Socket.IO с явным адресом
    console.log('Подключение к серверу Socket.IO...');
    const socket = io.connect(window.location.origin, {
        reconnectionAttempts: 3,
        timeout: 5000,
        forceNew: true
    });

    // Функции
    function addLog(message) {
        const timeStr = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `<span class="log-time">[${timeStr}]</span> ${message}`;
        elements.logs.appendChild(entry);
        elements.logs.scrollTop = elements.logs.scrollHeight;
    }

    function updateBotStatus(active) {
        state.botActive = active;
        elements.statusBadge.textContent = active ? 'Активен' : 'Неактивен';
        
        if (active) {
            elements.statusBadge.classList.add('active');
        } else {
            elements.statusBadge.classList.remove('active');
        }
        
        elements.startBot.disabled = active;
        elements.stopBot.disabled = !active;
        
        if (active) {
            addLog('Бот активирован');
        } else {
            addLog('Бот остановлен');
        }
    }

    function renderList(listElement, items, formatter, removeCallback) {
        // Очистка списка для оптимизации
        while (listElement.firstChild) {
            listElement.removeChild(listElement.firstChild);
        }
        
        if (!items.length) {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = 'Нет добавленных';
            listElement.appendChild(li);
            return;
        }
        
        const fragment = document.createDocumentFragment();
        items.forEach((item, index) => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = formatter ? formatter(item) : (item.username || item);
            
            if (removeCallback) {
                const btn = document.createElement('button');
                btn.className = 'danger';
                btn.innerHTML = '<i class="fas fa-trash"></i>';
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    removeCallback(index, item);
                });
                li.appendChild(btn);
            }
            fragment.appendChild(li);
        });
        listElement.appendChild(fragment);
    }

    // Socket.IO события
    socket.on('connect', () => {
        console.log('Подключено к серверу Socket.IO');
        addLog('Подключено к серверу');
        socket.emit('get_status');
    });
    
    socket.on('connect_error', (error) => {
        console.error('Ошибка подключения к Socket.IO:', error);
        addLog('Ошибка соединения с сервером');
    });
    
    socket.on('disconnect', () => {
        addLog('Соединение с сервером потеряно');
        updateBotStatus(false);
    });
    
    socket.on('status', data => {
        addLog(data.message);
    });
    
    socket.on('status_update', data => {
        console.log('Получен статус:', data);
        
        // Принудительно обновляем статус бота на основе данных от сервера
        if (data.bot_active !== undefined) {
            updateBotStatus(Boolean(data.bot_active));
        }
        
        if (data.message_count !== undefined && data.total_messages !== undefined) {
            elements.messageCount.textContent = `${data.message_count}/${data.total_messages}`;
        }
        
        if (data.accounts_count !== undefined) {
            elements.accountCount.textContent = `${data.accounts_count}`;
        }
    });
    
    socket.on('progress_update', data => {
        elements.progressBar.style.width = `${data.percentage}%`;
        elements.messageCount.textContent = `${data.current_messages}/${data.total_messages}`;
        elements.accountCount.textContent = `${data.current_account}/${data.total_accounts}`;
    });
    
    socket.on('proxies_update', data => {
        state.proxies = data.proxies;
        renderList(elements.proxiesList, state.proxies, null, (index) => {
            socket.emit('remove_proxy', { proxy: state.proxies[index] });
        });
    });
    
    socket.on('counter_update', data => {
        if (data.message_count !== undefined && data.total_messages !== undefined) {
            elements.messageCount.textContent = `${data.message_count}/${data.total_messages}`;
        }
    });
    
    socket.on('screenshot_update', data => {
        if (data.screenshot) {
            const now = Date.now();
            // Обновляем скриншот не чаще чем раз в 500 мс для оптимизации
            if (now - state.screenshotUpdateTime > 500) {
                elements.botScreenshot.src = `data:image/jpeg;base64,${data.screenshot}`;
                state.screenshotUpdateTime = now;
            }
        }
    });

    // Обработчики событий интерфейса
    elements.addAccount.addEventListener('click', () => {
        const username = elements.username.value.trim();
        const password = elements.password.value.trim();
        
        if (username && password) {
            state.accounts.push({ username, password });
            renderList(
                elements.accountsList, 
                state.accounts, 
                item => item.username, 
                (index) => {
                    state.accounts.splice(index, 1);
                    renderList(elements.accountsList, state.accounts, item => item.username);
                }
            );
            elements.username.value = '';
            elements.password.value = '';
            addLog(`Аккаунт добавлен: ${username}`);
        } else {
            addLog('Введите логин и пароль');
        }
    });

    elements.addProxy.addEventListener('click', () => {
        const proxy = elements.proxy.value.trim();
        if (proxy) {
            socket.emit('add_proxy', { proxy });
            elements.proxy.value = '';
        } else {
            addLog('Введите адрес прокси');
        }
    });

    elements.checkProxy.addEventListener('click', () => {
        const proxy = elements.proxy.value.trim();
        if (proxy) {
            addLog('Проверка прокси...');
            fetch('/check_proxy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proxy })
            })
            .then(res => res.json())
            .then(data => addLog(data.message))
            .catch(error => addLog(`Ошибка проверки: ${error}`));
        } else {
            addLog('Введите адрес прокси для проверки');
        }
    });

    elements.startBot.addEventListener('click', () => {
        if (!state.accounts.length) { 
            addLog('Добавьте хотя бы один аккаунт'); 
            return; 
        }
        
        const messageText = elements.message.value.trim();
        if (!messageText) { 
            addLog('Введите сообщение для отправки'); 
            showStatusMessage('Необходимо ввести сообщение для отправки', false);
            return; 
        }
        
        // Дополнительная проверка на активность бота
        if (state.botActive) {
            addLog('Бот уже активен. Сначала остановите его.');
            return;
        }
        
        const data = {
            accounts: state.accounts,
            proxies: state.proxies,
            message: messageText,
            minAge: parseInt(elements.minAge.value),
            maxAge: parseInt(elements.maxAge.value)
        };
        
        // Отключаем кнопку запуска и включаем кнопку остановки
        elements.startBot.disabled = true;
        elements.stopBot.disabled = false;
        
        addLog(`Сообщение для отправки: "${messageText.substring(0, 30)}${messageText.length > 30 ? '...' : ''}"`);
        socket.emit('start_bot', data);
        
        // НЕ обновляем статус здесь, подождем ответа от сервера
        
        // Периодически проверяем статус
        const statusInterval = setInterval(() => {
            if (socket.connected) {
                socket.emit('get_status');
            }
            
            if (!state.botActive) {
                clearInterval(statusInterval);
            }
        }, 2000);
    });

    elements.stopBot.addEventListener('click', () => {
        // Отключаем кнопку остановки, чтобы предотвратить множественные нажатия
        elements.stopBot.disabled = true;
        
        addLog('Остановка бота...');
        socket.emit('stop_bot');
        
        // Через 5 секунд проверим статус ещё раз
        setTimeout(() => {
            socket.emit('get_status');
        }, 5000);
    });
    
    elements.clearLogs.addEventListener('click', () => { 
        elements.logs.innerHTML = ''; 
        addLog('Логи очищены'); 
    });
    
    elements.message.addEventListener('blur', () => {
        const msg = elements.message.value.trim();
        if (msg) socket.emit('set_message', { message: msg });
    });
    
    [elements.minAge, elements.maxAge].forEach(input => {
        input.addEventListener('change', () => {
            socket.emit('set_age_range', { 
                minAge: parseInt(elements.minAge.value), 
                maxAge: parseInt(elements.maxAge.value) 
            });
        });
    });

    // Инициализация и периодические обновления
    function init() {
        addLog('Менеджер ботов инициализирован');
        socket.emit('get_status');
        
        // Периодически запрашиваем статус
        setInterval(() => {
            if (socket.connected) {
                socket.emit('get_status');
            }
        }, 5000);
        
        // Резервное обновление скриншотов (если сокеты не работают)
        setInterval(() => {
            if (state.botActive) {
                fetch('/screenshot')
                    .then(res => res.json())
                    .then(data => {
                        if (data.screenshot) {
                            elements.botScreenshot.src = 'data:image/jpeg;base64,' + data.screenshot;
                        }
                    })
                    .catch(err => console.error('Ошибка обновления скриншота:', err));
            }
        }, 3000);
        
        // Обработка событий клавиатуры для быстрой остановки
        document.addEventListener('keydown', (e) => {
            // Остановка по ESC
            if (e.key === 'Escape' && state.botActive) {
                addLog('Экстренная остановка бота (ESC)');
                socket.emit('stop_bot');
            }
        });
    }
    
    // Запускаем приложение
    init();
});
