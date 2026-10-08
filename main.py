"""
AI Earphone Assistant v0.2
Голосовой ИИ-помощник в наушник (Bluetooth + Microphone)
Стек: Kivy + SpeechRecognition + gTTS + Groq API (всё бесплатно)
"""

import threading
import os
import json
import tempfile
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.storage.jsonstore import JsonStore

# ── Цвета ─────────────────────────────────────────────────────────────────────
BG_COLOR      = (0.07, 0.07, 0.11, 1)
ACCENT        = (0.28, 0.55, 1.00, 1)
CARD_COLOR    = (0.13, 0.13, 0.20, 1)
TEXT_COLOR    = (0.92, 0.92, 0.95, 1)
SUCCESS_COLOR = (0.20, 0.76, 0.50, 1)
ERROR_COLOR   = (0.93, 0.33, 0.33, 1)
WARN_COLOR    = (1.00, 0.71, 0.25, 1)
MUTED_COLOR   = (0.48, 0.48, 0.58, 1)

Window.clearcolor = BG_COLOR

# ── Настройки (сохраняются на телефоне) ──────────────────────────────────────
store = JsonStore('assistant_settings.json')

DEFAULTS = {
    'groq_api_key':  '',
    'groq_model':    'llama3-8b-8192',
    'wake_word':     'окей ассистент',
    'speech_lang':   'ru-RU',
    'system_prompt': (
        'Ты голосовой помощник. Отвечай ОЧЕНЬ кратко — максимум 2 предложения. '
        'Никаких списков, только живая речь.'
    ),
}

def get_s(key):
    try:
        return store.get(key)['value']
    except Exception:
        return DEFAULTS.get(key, '')

def set_s(key, value):
    store.put(key, value=value)


# ══════════════════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ ЭКРАН
# ══════════════════════════════════════════════════════════════════════════════
class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_listening = False
        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation='vertical', padding=16, spacing=10)

        # Заголовок
        root.add_widget(Label(
            text='🎧 AI Помощник',
            font_size='24sp', bold=True,
            color=ACCENT, size_hint_y=None, height=52,
        ))

        # Статус
        self.lbl_status = Label(
            text='Нажми кнопку и говори',
            font_size='13sp', color=TEXT_COLOR,
            size_hint_y=None, height=32,
        )
        root.add_widget(self.lbl_status)

        # Лог диалога (прокручиваемый)
        sv = ScrollView()
        self.lbl_log = Label(
            text='', font_size='13sp', color=TEXT_COLOR,
            halign='left', valign='top',
            text_size=(Window.width - 40, None),
            size_hint_y=None,
        )
        self.lbl_log.bind(texture_size=self.lbl_log.setter('size'))
        sv.add_widget(self.lbl_log)
        root.add_widget(sv)

        # Bluetooth-статус
        self.lbl_bt = Label(
            text='🔵 Bluetooth: определяется...',
            font_size='12sp', color=MUTED_COLOR,
            size_hint_y=None, height=28,
        )
        root.add_widget(self.lbl_bt)

        # Кнопки
        row = BoxLayout(orientation='horizontal',
                        size_hint_y=None, height=60, spacing=10)

        self.btn_listen = Button(
            text='🎤 Слушать',
            font_size='16sp', bold=True,
            background_color=ACCENT, background_normal='',
            color=(1, 1, 1, 1), size_hint_x=0.72,
        )
        self.btn_listen.bind(on_press=self._toggle_listen)

        btn_cfg = Button(
            text='⚙', font_size='22sp',
            background_color=CARD_COLOR, background_normal='',
            color=ACCENT, size_hint_x=0.28,
        )
        btn_cfg.bind(on_press=lambda *a: setattr(self.manager, 'current', 'settings'))

        row.add_widget(self.btn_listen)
        row.add_widget(btn_cfg)
        root.add_widget(row)

        # Wake-word
        self.lbl_wake = Label(
            text=f'Wake-word: «{get_s("wake_word")}»',
            font_size='11sp', color=MUTED_COLOR,
            size_hint_y=None, height=22,
        )
        root.add_widget(self.lbl_wake)

        self.add_widget(root)

        # Проверить Bluetooth при старте
        Clock.schedule_once(self._check_bluetooth, 1.5)

    # ── Bluetooth ──────────────────────────────────────────────────────────────
    def _check_bluetooth(self, *args):
        """
        На Android через Pyjnius запрашиваем имя подключённого BT-устройства.
        Работает только на реальном устройстве, не в эмуляторе.
        """
        try:
            from jnius import autoclass
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            adapter = BluetoothAdapter.getDefaultAdapter()
            if adapter is None:
                self.lbl_bt.text = '⚫ Bluetooth недоступен'
                return
            if not adapter.isEnabled():
                self.lbl_bt.text = '🔴 Bluetooth выключен'
                return
            # Ищем подключённые гарнитуры
            devices = adapter.getBondedDevices().toArray()
            names = [d.getName() for d in devices] if devices else []
            if names:
                self.lbl_bt.text = f'🟢 BT: {", ".join(names[:2])}'
            else:
                self.lbl_bt.text = '🔵 Bluetooth вкл, гарнитура не найдена'
        except Exception:
            # На ПК / эмуляторе Pyjnius недоступен — это нормально
            self.lbl_bt.text = '🔵 Bluetooth (проверка на телефоне)'

    # ── Слушать / Стоп ────────────────────────────────────────────────────────
    def _toggle_listen(self, *args):
        if self.is_listening:
            self.is_listening = False
            self.btn_listen.text = '🎤 Слушать'
            self.btn_listen.background_color = ACCENT
            self._set_status('Остановлено', TEXT_COLOR)
        else:
            self.is_listening = True
            self.btn_listen.text = '⏹ Стоп'
            self.btn_listen.background_color = ERROR_COLOR
            self._set_status('🎤 Слушаю...', WARN_COLOR)
            threading.Thread(target=self._listen_loop, daemon=True).start()

    # ── Поток: распознавание голоса ───────────────────────────────────────────
    def _listen_loop(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            lang = get_s('speech_lang') or 'ru-RU'

            with sr.Microphone() as src:
                r.adjust_for_ambient_noise(src, duration=0.6)
                while self.is_listening:
                    try:
                        audio = r.listen(src, timeout=6, phrase_time_limit=12)
                        text  = r.recognize_google(audio, language=lang)
                        Clock.schedule_once(lambda dt, t=text: self._on_heard(t))
                    except sr.WaitTimeoutError:
                        pass
                    except sr.UnknownValueError:
                        pass
                    except Exception as e:
                        Clock.schedule_once(
                            lambda dt, e=e: self._set_status(f'Ошибка: {e}', ERROR_COLOR))
                        break
        except Exception as e:
            Clock.schedule_once(
                lambda dt, e=e: self._set_status(f'Микрофон: {e}', ERROR_COLOR))

    # ── Проверка wake-word ────────────────────────────────────────────────────
    def _on_heard(self, text):
        wake = (get_s('wake_word') or '').lower().strip()
        t    = text.lower()
        if wake and wake not in t:
            self._set_status(f'Слышу: {text}', MUTED_COLOR)
            return
        query = t.replace(wake, '').strip() if wake else t
        if not query:
            self._set_status('Скажи запрос после wake-word', WARN_COLOR)
            return
        self._log(f'👤 {query}')
        self._set_status('🤔 Думаю...', ACCENT)
        threading.Thread(target=self._ask_ai, args=(query,), daemon=True).start()

    # ── Запрос к Groq ─────────────────────────────────────────────────────────
    def _ask_ai(self, query):
        import urllib.request, urllib.error
        key = get_s('groq_api_key') or ''
        if not key:
            Clock.schedule_once(lambda dt: self._set_status(
                '⚠ Нет API-ключа! Открой Настройки', ERROR_COLOR))
            return
        model  = get_s('groq_model') or 'llama3-8b-8192'
        prompt = get_s('system_prompt') or DEFAULTS['system_prompt']
        body   = json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user',   'content': query},
            ],
            'max_tokens': 200, 'temperature': 0.7,
        }).encode()
        try:
            req = urllib.request.Request(
                'https://api.groq.com/openai/v1/chat/completions',
                data=body,
                headers={'Content-Type': 'application/json',
                         'Authorization': f'Bearer {key}'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=12) as r:
                answer = json.loads(r.read())['choices'][0]['message']['content'].strip()
            Clock.schedule_once(lambda dt, a=answer: self._on_answer(a))
        except Exception as e:
            Clock.schedule_once(
                lambda dt, e=e: self._set_status(f'AI ошибка: {e}', ERROR_COLOR))

    # ── Ответ получен → говорим ───────────────────────────────────────────────
    def _on_answer(self, answer):
        self._log(f'🤖 {answer}')
        self._set_status('🔊 Говорю...', SUCCESS_COLOR)
        threading.Thread(target=self._speak, args=(answer,), daemon=True).start()

    # ── TTS через gTTS + pygame ───────────────────────────────────────────────
    def _speak(self, text):
        try:
            from gtts import gTTS
            import pygame

            lang_map = {'ru-RU': 'ru', 'en-US': 'en', 'en-GB': 'en'}
            lang = lang_map.get(get_s('speech_lang'), 'ru')

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            gTTS(text=text, lang=lang, slow=False).save(tmp.name)
            tmp.close()

            pygame.mixer.init()
            pygame.mixer.music.load(tmp.name)
            pygame.mixer.music.play()
            import time
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.quit()
            os.unlink(tmp.name)

            Clock.schedule_once(lambda dt: self._set_status('✅ Готово', SUCCESS_COLOR))
        except Exception as e:
            Clock.schedule_once(
                lambda dt, e=e: self._set_status(f'TTS: {e}', WARN_COLOR))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _log(self, text):
        lines = (self.lbl_log.text.split('\n') if self.lbl_log.text else []) + [text]
        self.lbl_log.text = '\n'.join(lines[-30:])

    def _set_status(self, text, color=TEXT_COLOR):
        self.lbl_status.text  = text
        self.lbl_status.color = color

    def on_enter(self):
        self.lbl_wake.text = f'Wake-word: «{get_s("wake_word")}»'
        Clock.schedule_once(self._check_bluetooth, 0.5)


# ══════════════════════════════════════════════════════════════════════════════
#  ЭКРАН НАСТРОЕК
# ══════════════════════════════════════════════════════════════════════════════
class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation='vertical', padding=16, spacing=8)

        # Шапка
        bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=48)
        btn_back = Button(
            text='← Назад', size_hint_x=None, width=110,
            background_color=CARD_COLOR, background_normal='', color=ACCENT,
        )
        btn_back.bind(on_press=lambda *a: self._save())
        bar.add_widget(btn_back)
        bar.add_widget(Label(text='⚙ Настройки', font_size='20sp',
                             color=ACCENT, bold=True))
        root.add_widget(bar)

        # Прокрутка
        sv = ScrollView()
        box = BoxLayout(orientation='vertical', spacing=8,
                        size_hint_y=None, padding=(0, 6))
        box.bind(minimum_height=box.setter('height'))

        def field(label, key, hint='', ml=False, pwd=False):
            box.add_widget(Label(
                text=label, font_size='12sp', color=MUTED_COLOR,
                size_hint_y=None, height=24, halign='left',
                text_size=(Window.width - 32, None),
            ))
            inp = TextInput(
                text=str(get_s(key) or ''),
                hint_text=hint, font_size='14sp',
                size_hint_y=None, height=(88 if ml else 46),
                background_color=CARD_COLOR, foreground_color=TEXT_COLOR,
                cursor_color=ACCENT, multiline=ml, password=pwd,
            )
            box.add_widget(inp)
            return inp

        self.f_key    = field('Groq API Key (получи бесплатно на console.groq.com)',
                              'groq_api_key', 'gsk_...', pwd=True)
        self.f_model  = field('Модель  (llama3-8b-8192  или  llama3-70b-8192)',
                              'groq_model', 'llama3-8b-8192')
        self.f_wake   = field('Wake-word — фраза активации',
                              'wake_word', 'окей ассистент')
        self.f_lang   = field('Язык распознавания  (ru-RU  /  en-US)',
                              'speech_lang', 'ru-RU')
        self.f_prompt = field('Системный промпт (характер ассистента)',
                              'system_prompt', ml=True)

        # Подсказка
        box.add_widget(Label(
            text=(
                '──────────────────────────────\n'
                '🎧 Bluetooth:\n'
                '   Подключи наушники ДО запуска\n'
                '   Звук идёт автоматически в BT\n\n'
                '💡 Groq API — бесплатно:\n'
                '   console.groq.com → API Keys\n\n'
                '📶 Нужен интернет (Wi-Fi / 4G)\n'
                '──────────────────────────────'
            ),
            font_size='12sp', color=MUTED_COLOR,
            size_hint_y=None, height=170,
            halign='left', text_size=(Window.width - 32, None),
        ))

        btn_save = Button(
            text='💾 Сохранить',
            font_size='16sp', size_hint_y=None, height=54,
            background_color=SUCCESS_COLOR, background_normal='',
            color=(1, 1, 1, 1),
        )
        btn_save.bind(on_press=lambda *a: self._save())
        box.add_widget(btn_save)

        sv.add_widget(box)
        root.add_widget(sv)
        self.add_widget(root)

    def _save(self):
        set_s('groq_api_key',  self.f_key.text.strip())
        set_s('groq_model',    self.f_model.text.strip() or 'llama3-8b-8192')
        set_s('wake_word',     self.f_wake.text.strip().lower())
        set_s('speech_lang',   self.f_lang.text.strip() or 'ru-RU')
        set_s('system_prompt', self.f_prompt.text.strip())
        self.manager.current = 'main'


# ══════════════════════════════════════════════════════════════════════════════
#  ПРИЛОЖЕНИЕ
# ══════════════════════════════════════════════════════════════════════════════
class AIAssistantApp(App):
    def build(self):
        for k, v in DEFAULTS.items():
            if not store.exists(k):
                set_s(k, v)
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(SettingsScreen(name='settings'))
        return sm

    def on_pause(self):   return True   # не убивать при сворачивании
    def on_resume(self):  pass


if __name__ == '__main__':
    AIAssistantApp().run()
