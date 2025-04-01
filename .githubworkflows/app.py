import os
import sys
import subprocess
import random
import time
import threading
import json
import logging

# Функция для установки недостающих зависимостей
def install_missing_dependencies():
    required_packages = [
        "flask", "flask-socketio", "eventlet", "playwright",
        "requests", "python-dotenv", "websocket-client",
        "beautifulsoup4", "fake-useragent", "pillow", "gpt4all"
    ]
    
    # Устанавливаем сначала базовые зависимости
    for package in required_packages:
        try:
            __import__(package.replace("-", "_").split("==")[0])
            print(f"✓ {package} уже установлен")
        except ImportError:
            print(f"✗ Установка {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"✓ {package} успешно установлен")
            except Exception as e:
                print(f"Ошибка установки {package}: {e}")

    # Отдельно устанавливаем llama-cpp-python с нужными флагами
    try:
        import llama_cpp
        print("✓ llama-cpp-python уже установлен")
    except ImportError:
        print("✗ Установка llama-cpp-python...")
        try:
            # Устанавливаем с флагами для CPU
            subprocess.check_call([
                sys.executable, 
                "-m", 
                "pip", 
                "install", 
                "llama-cpp-python==0.2.11",
                "--no-cache-dir",
                "--verbose",
                "--force-reinstall"
            ])
            print("✓ llama-cpp-python успешно установлен")
        except Exception as e:
            print(f"Ошибка установки llama-cpp-python: {e}")

print("Проверка зависимостей...")
try:
    install_missing_dependencies()
except Exception as e:
    print(f"Ошибка установки зависимостей: {e}")
    sys.exit(1)

try:
    # Теперь можно импортировать библиотеки
    import eventlet
    eventlet.monkey_patch()
    from flask import Flask, render_template, jsonify, request, Response, send_from_directory
    from flask_socketio import SocketIO, emit
    from queue import Queue
    from playwright.sync_api import sync_playwright
    import requests
    from requests.exceptions import RequestException
    from fake_useragent import UserAgent
    import base64
    from bs4 import BeautifulSoup
    from llama_cpp import Llama
    from gpt4all import GPT4All
except ImportError as e:
    print(f"Ошибка импорта библиотек: {e}")
    print("Попробуйте перезапустить скрипт")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("логи_приложения.txt")]
)
logger = logging.getLogger()

def initialize_ai_models():
    try:
        global llm
        from gpt4all import GPT4All
        
        models_dir = os.path.join(os.getcwd(), 'models')
        os.makedirs(models_dir, exist_ok=True)
        
        model_path = os.path.join(models_dir, 'ggml-gpt4all-j-v1.3-groovy.bin')
        
        if not os.path.exists(model_path):
            logger.info("Скачивание модели GPT4All...")
            model = GPT4All("ggml-gpt4all-j-v1.3-groovy")
            model.download_model(model_path)
            logger.info(f"Модель GPT4All скачана в {model_path}")
        
        logger.info("Загрузка модели GPT4All...")
        llm = GPT4All(model_path)
        
        logger.info("ИИ модель GPT4All успешно инициализирована")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка инициализации GPT4All: {e}")
        return False

app = Flask(__name__, 
    template_folder=os.path.join(os.getcwd(), 'templates'),
    static_folder=os.path.join(os.getcwd(), 'static'),
    static_url_path='/static'
)

socketio = SocketIO(
    app, 
    async_mode='eventlet', 
    cors_allowed_origins="*",
    ping_timeout=10,
    ping_interval=5,
    max_http_buffer_size=10e6,
    manage_session=False
)

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled Exception: {e}")
    return jsonify({"error": "Internal Server Error"}), 500

@app.route('/')
def index():
    try:
        template_path = os.path.join(os.getcwd(), 'templates', 'index.html')
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype='text/html')
        else:
            return "Error: index.html not found", 500
    except Exception as e:
        logger.error(f"Error serving index.html: {e}")
        return str(e), 500

def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Необработанное исключение", exc_info=(exc_type, exc_value, exc_traceback))
sys.excepthook = handle_unhandled_exception

# Глобальные переменные
bot_thread = None
bot_active = False
message_count = 0
total_messages = 0
accounts = []
proxies = []
message_to_send = ""
min_age = 18
max_age = 99
lock = threading.Lock()
message_queue = Queue()
current_screenshot = None
screenshot_lock = threading.Lock()
ai_browser_manager = None

DEFAULT_TIMEOUT = 500
SCREENSHOT_INTERVAL = 2

def check_proxy(proxy: str) -> dict:
    test_url = "https://httpbin.org/ip"
    try:
        proxy_url = proxy if proxy.startswith('http://') or proxy.startswith('https://') else f"http://{proxy}"
        proxy_dict = {"http": proxy_url, "https": proxy_url}
        response = requests.get(test_url, proxies=proxy_dict, timeout=10)
        if response.status_code == 200:
            return {"status": "success", "message": "Прокси работает!"}
        else:
            return {"status": "fail", "message": f"HTTP ошибка {response.status_code}"}
    except RequestException as e:
        return {"status": "fail", "message": f"Ошибка соединения: {str(e)}"}

def broadcast_screenshot():
    while bot_active:
        with screenshot_lock:
            if ai_browser_manager:
                screenshot = ai_browser_manager.get_screenshot()
                if screenshot:
                    screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
                    socketio.emit('screenshot_update', {'screenshot': screenshot_b64})
        eventlet.sleep(SCREENSHOT_INTERVAL)

class SelfLearningAIBrowser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.history_file = os.path.join(os.getcwd(), 'ai_learning_history.json')
        
        self.SITE_LOGIN_URL = "https://www.manhunt.net/login"
        self.SITE_PROFILES_URL = "https://www.manhunt.net/lists/men/men"
        self.MAX_MESSAGES_PER_ACCOUNT = 25
        
        self.knowledge_base = {
            "login_page": {
                "patterns": ["/login"],
                "selectors": {
                    "username": ['input[id="loginusername"]', 'input[name="username"]', 'input[type="text"]'],
                    "password": ['input[id="loginpassword"]', 'input[name="password"]', 'input[type="password"]'],
                    "submit": ['button[type="submit"]', 'input[type="submit"]', 'button:contains("Login")']
                }
            },
            "profiles_page": {
                "patterns": ["/lists/men", "/search"],
                "selectors": {
                    "profiles": ['div.profCont', '.profile-container'],
                    "message_button": ['span.profIcon.msgLink', 'a[href*="messages"]']
                }
            }
        }
        
        self.learning_history = {
            "successful_patterns": {},
            "failed_attempts": {},
            "visited_urls": set(),
            "selector_cache": {},
            "successful_sequences": [],
            "performance_metrics": {
                "total_actions": 0,
                "successful_actions": 0,
                "average_action_time": 0.0
            }
        }
        
        self.load_learning_history()

    def initialize(self, proxy=None):
        try:
            self.playwright = sync_playwright().start()
            browser_options = {
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-extensions'
                ]
            }
            
            if proxy:
                browser_options['proxy'] = {
                    'server': proxy
                }
                
            self.browser = self.playwright.chromium.launch(**browser_options)
            self.context = self.browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent=UserAgent().random
            )
            self.page = self.context.new_page()
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации браузера: {e}")
            return False

    def human_like_typing(self, element, text):
        try:
            element.click()
            element.fill("")
            for char in text:
                element.type(char, delay=random.randint(50, 150))
                time.sleep(random.uniform(0.01, 0.05))
            return True
        except Exception as e:
            logger.error(f"Ошибка при вводе текста: {e}")
            return False

    def human_like_message_typing(self, message):
        try:
            textarea = self.page.query_selector('textarea')
            if textarea:
                self.human_like_typing(textarea, message)
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при вводе сообщения: {e}")
            return False

    def get_screenshot(self):
        try:
            if self.page:
                return self.page.screenshot(type="jpeg", quality=80)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения скриншота: {e}")
            return None

    def cleanup(self):
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.error(f"Ошибка очистки ресурсов: {e}")

    def load_learning_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    
                    for key, value in loaded_data.items():
                        if key != 'visited_urls':
                            self.learning_history[key] = value
                    
                    if 'visited_urls' in loaded_data:
                        self.learning_history['visited_urls'] = set(loaded_data['visited_urls'])
                    
                    logger.info(f"Загружена история обучения ИИ: {len(self.learning_history['successful_patterns'])} шаблонов")
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки истории обучения: {e}")
            return False
    
    def save_learning_history(self):
        try:
            history_copy = self.learning_history.copy()
            history_copy['visited_urls'] = list(self.learning_history['visited_urls'])
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history_copy, f, ensure_ascii=False, indent=2)
            logger.info("История обучения ИИ сохранена")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения истории обучения: {e}")
            return False
    
    def learn_from_action(self, action_type, success, context=None):
        try:
            self.learning_history['performance_metrics']['total_actions'] += 1
            
            if success:
                self.learning_history['performance_metrics']['successful_actions'] += 1
                
                if action_type not in self.learning_history['successful_patterns']:
                    self.learning_history['successful_patterns'][action_type] = {
                        'count': 0,
                        'success_rate': 0,
                        'contexts': []
                    }
                
                pattern = self.learning_history['successful_patterns'][action_type]
                pattern['count'] += 1
                
                if context and len(pattern['contexts']) < 10:
                    pattern['contexts'].append(context)
                
                total_attempts = pattern['count'] + self.learning_history['failed_attempts'].get(action_type, 0)
                pattern['success_rate'] = pattern['count'] / total_attempts if total_attempts > 0 else 1.0
            else:
                if action_type not in self.learning_history['failed_attempts']:
                    self.learning_history['failed_attempts'][action_type] = 0
                self.learning_history['failed_attempts'][action_type] += 1
                
                if action_type.startswith('selector_'):
                    selector_name = action_type.split('_', 1)[1]
                    if selector_name in self.learning_history['selector_cache']:
                        logger.info(f"Удаляем неработающий селектор из кэша: {selector_name}")
                        del self.learning_history['selector_cache'][selector_name]
            
            if context and 'duration' in context:
                metrics = self.learning_history['performance_metrics']
                old_avg = metrics['average_action_time']
                total_actions = metrics['total_actions']
                
                if total_actions == 1:
                    metrics['average_action_time'] = context['duration']
                else:
                    metrics['average_action_time'] = (old_avg * (total_actions - 1) + context['duration']) / total_actions
            
            if self.learning_history['performance_metrics']['total_actions'] % 10 == 0:
                self.save_learning_history()
                
            self._send_performance_metrics(action_type, success, context)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка обработки результата действия: {e}")
            return False
    
    def _send_performance_metrics(self, action_type, success, context):
        try:
            metrics = self.learning_history['performance_metrics']
            
            last_action = {
                'type': action_type,
                'success': success,
                'duration': context.get('duration', 0) if context else 0
            }
            
            socketio.emit('performance_update', {
                'metrics': metrics,
                'last_action': last_action
            })
        except Exception as e:
            logger.error(f"Ошибка отправки метрик: {e}")
    
    def smart_find_element(self, selector_name, context=None):
        try:
            cache_key = f"selector_{selector_name}"
            
            if cache_key in self.learning_history['selector_cache']:
                cached_selectors = self.learning_history['selector_cache'][cache_key]
                for selector in cached_selectors:
                    try:
                        element = self.page.query_selector(selector)
                        if element and element.is_visible():
                            self.learn_from_action(cache_key, True, {'selector': selector})
                            return element
                    except:
                        continue
            
            all_selectors = []
            
            for section in self.knowledge_base.values():
                if 'selectors' in section and selector_name in section['selectors']:
                    all_selectors.extend(section['selectors'][selector_name])
            
            if not all_selectors:
                common_selectors = {
                    'username': ['input[type="text"]', 'input[id*="user"]', 'input[name*="user"]'],
                    'password': ['input[type="password"]'],
                    'submit': ['button[type="submit"]', 'input[type="submit"]', 'button:contains("Login")'],
                    'message': ['textarea', 'div[contenteditable="true"]']
                }
                if selector_name in common_selectors:
                    all_selectors = common_selectors[selector_name]
            
            for selector in all_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        if cache_key not in self.learning_history['selector_cache']:
                            self.learning_history['selector_cache'][cache_key] = []
                        
                        if selector not in self.learning_history['selector_cache'][cache_key]:
                            self.learning_history['selector_cache'][cache_key].append(selector)
                        
                        self.learn_from_action(cache_key, True, {'selector': selector})
                        return element
                except:
                    continue
            
            self.learn_from_action(cache_key, False)
            return None
        except Exception as e:
            logger.error(f"Ошибка умного поиска элемента {selector_name}: {e}")
            return None
    
    def generate_text(self, prompt, max_tokens=100):
        """Генерирует текст с помощью GPT4All"""
        try:
            response = llm.generate(
                prompt,
                max_tokens=max_tokens,
                temp=0.7,
                top_k=40,
                top_p=0.9,
                repeat_penalty=1.1
            )
            return response
        except Exception as e:
            logger.error(f"Ошибка генерации текста: {e}")
            return "Не удалось сгенерировать текст"
    
    def navigate_and_interact(self, url, context):
        try:
            start_time = time.time()
            logger.info(f"Начало навигации на {url}")
            
            # Переходим на страницу
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_load_state("networkidle")
            
            current_url = self.page.url
            success = False
            
            if "/login" in current_url:
                # Обработка страницы входа
                success = self._handle_login(context["username"], context["password"])
            elif "/lists/men" in current_url or "/search" in current_url:
                # Обработка страницы поиска профилей
                self._set_age_filters(context["min_age"], context["max_age"])
                success = self._send_messages_to_profiles(context["message"])
            
            duration = time.time() - start_time
            self.learn_from_action("navigate", success, {
                "url": url,
                "duration": duration,
                "success": success
            })
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка навигации: {e}")
            return False

    def _handle_login(self, username, password):
        try:
            # Поиск полей входа
            username_field = self.smart_find_element("username")
            password_field = self.smart_find_element("password")
            submit_button = self.smart_find_element("submit")
            
            if not all([username_field, password_field, submit_button]):
                logger.error("Не найдены поля для входа")
                return False
            
            # Ввод данных
            self.human_like_typing(username_field, username)
            self.human_like_typing(password_field, password)
            
            # Нажатие кнопки входа
            submit_button.click()
            
            # Ожидание перехода
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)  # Дополнительное ожидание
            
            return "/login" not in self.page.url
            
        except Exception as e:
            logger.error(f"Ошибка при входе: {e}")
            return False

if __name__ == "__main__":
    try:
        # Подробное логирование запуска
        logger.info("=== Запуск приложения ===")
        logger.info(f"Текущая директория: {os.getcwd()}")
        logger.info(f"Python версия: {sys.version}")
        
        # Проверка директорий
        for directory in ['templates', 'static/js', 'logs', 'models']:
            full_path = os.path.join(os.getcwd(), directory)
            os.makedirs(full_path, exist_ok=True)
            logger.info(f"Директория {full_path} проверена")
            
        # Проверка файлов
        required_files = {
            'templates/index.html': 'HTML шаблон',
            'static/js/app.js': 'JavaScript код',
        }
        
        for file_path, description in required_files.items():
            full_path = os.path.join(os.getcwd(), file_path)
            if os.path.exists(full_path):
                logger.info(f"Найден {description}: {full_path}")
            else:
                logger.warning(f"Не найден {description}: {full_path}")
        
        # Запуск сервера с подробным логированием
        logger.info("Запуск Flask сервера...")
        socketio.run(app, host='127.0.0.1', port=5001, debug=True)
        
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'ai_browser_manager' in globals() and ai_browser_manager:
            ai_browser_manager.cleanup()