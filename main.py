# -*- coding: utf-8 -*-
"""
ВидеоЛоопер для Android (киоск-режим).

Проигрывает по очереди все видео из выбранной папки, в бесконечном цикле.
Если в настройках платы/телевизора включён автозапуск последнего
приложения, при включении устройства плеер откроется сам и начнёт
с первого видео.

УПРАВЛЕНИЕ:
  5 быстрых касаний экрана (в течение ~2 секунд) → ввод PIN-кода
  → меню: «Настройки» (папка, перемешивание, смена PIN)
          «Выйти из приложения» / «Продолжить показ».

PIN-код по умолчанию: 1234. Все настройки хранятся внутри приложения.
"""

import json
import os
import random
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.video import Video

# ===================== КОНФИГУРАЦИЯ (по умолчанию) =====================
DEFAULT_VIDEO_DIR = "/sdcard/Movies"   # папка, пока пользователь не выбрал свою
DEFAULT_PIN = "1234"                   # PIN, пока пользователь не сменил
VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".3gp")
TAPS_TO_MENU = 5                       # касаний для вызова меню
TAP_TIMEOUT = 2.0                      # секунды, за которые нужно успеть коснуться
RESCAN_SECONDS = 60                    # перечитывать папку каждые N сек (0 — выкл.)
# =======================================================================


def scan_videos(folder):
    """Список видеофайлов в папке, отсортированный по имени."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    files = []
    for name in names:
        path = os.path.join(folder, name)
        if name.lower().endswith(VIDEO_EXT) and os.path.isfile(path):
            files.append(path)
    return files


def android_setup():
    """Не даём экрану гаснуть + прячем системные панели (только Android)."""
    try:
        from jnius import autoclass
        activity = autoclass('org.kivy.android.PythonActivity').mActivity
        window = activity.getWindow()
        LayoutParams = autoclass('android.view.WindowManager$LayoutParams')
        window.addFlags(LayoutParams.FLAG_KEEP_SCREEN_ON)
        decor = window.getDecorView()
        View = autoclass('android.view.View')
        decor.setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_FULLSCREEN)
    except Exception:
        pass  # не Android — например, отладка на ПК


def request_android_permissions():
    """Запрос разрешения на чтение видео (на ПК просто игнорируется)."""
    try:
        from android.permissions import request_permissions
        request_permissions([
            'android.permission.READ_MEDIA_VIDEO',       # Android 13+
            'android.permission.READ_EXTERNAL_STORAGE',  # Android 12 и ниже
        ])
    except Exception:
        pass


class PlayerScreen(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.playlist = []
        self.index = 0
        self._taps = 0
        self._last_tap = 0.0
        self._browse_path = ''

        self.video = Video(state='stop',
                           allow_stretch=True,   # растягивать на весь экран
                           keep_ratio=False,
                           size_hint=(1, 1),
                           pos_hint={'center_x': 0.5, 'center_y': 0.5})
        self.video.bind(on_eos=self._on_eos)      # ролик доиграл
        self.add_widget(self.video)

        self.label = Label(text='Загрузка...', font_size='22sp')
        self.add_widget(self.label)

        self.bind(on_touch_down=self._on_touch)

        # сторожевой таймер: если воспроизведение остановилось
        # (битый файл и т.п.) — продолжаем со следующего ролика
        Clock.schedule_interval(self._watchdog, 2.0)
        if RESCAN_SECONDS:
            Clock.schedule_interval(lambda dt: self._rescan(), RESCAN_SECONDS)
        self._rescan()

    # ---------- воспроизведение ----------

    @property
    def cfg(self):
        return App.get_running_app().config_data

    def _rescan(self):
        files = scan_videos(self.cfg['video_dir'])
        if files != self.playlist:
            self.playlist = files
            if self.index >= len(self.playlist):
                self.index = 0

    def _next_index(self):
        """Следующий ролик: по порядку или случайно (если включено перемешивание)."""
        if self.cfg.get('shuffle') and len(self.playlist) > 1:
            new_index = self.index
            while new_index == self.index:
                new_index = random.randrange(len(self.playlist))
            return new_index
        return self.index + 1

    def _play(self, index):
        if not self.playlist:
            self._stop_all()
            return
        self.index = index % len(self.playlist)
        path = self.playlist[self.index]
        # если тот же файл, что сейчас — сбрасываем источник,
        # иначе повторный запуск того же ролика не сработает
        if self.video.source == path:
            self.video.source = ''
        self.label.text = ''
        self.video.source = path
        self.video.state = 'play'

    def _stop_all(self):
        self.video.state = 'stop'
        self.label.text = (
            'В папке нет видео:\n' + self.cfg['video_dir'] +
            '\n\nМеню: ' + str(TAPS_TO_MENU) + ' быстрых касаний экрана'
        )

    def _on_eos(self, instance):
        Clock.schedule_once(lambda dt: self._play(self._next_index()), 0.1)

    def _watchdog(self, dt):
        if self.playlist and self.video.state != 'play':
            self._play(self._next_index())

    # ---------- жест: N быстрых касаний → меню ----------

    def _on_touch(self, instance, touch):
        now = time.time()
        if now - self._last_tap > TAP_TIMEOUT:
            self._taps = 0
        self._last_tap = now
        self._taps += 1
        if self._taps >= TAPS_TO_MENU:
            self._taps = 0
            self._show_pin_popup()

    # ---------- окно PIN-кода ----------

    def _show_pin_popup(self):
        app = App.get_running_app()
        box = BoxLayout(orientation='vertical', spacing='10dp', padding='10dp')
        pin = TextInput(hint_text='PIN-код', password=True, multiline=False,
                        input_filter='int', size_hint_y=None, height='48dp')
        row = BoxLayout(size_hint_y=None, height='48dp', spacing='10dp')
        btn_ok = Button(text='Войти')
        btn_cancel = Button(text='Отмена')
        row.add_widget(btn_ok)
        row.add_widget(btn_cancel)
        box.add_widget(pin)
        box.add_widget(row)

        popup = Popup(title='Введите PIN-код', content=box,
                      size_hint=(0.5, 0.4), auto_dismiss=False)

        def check(*args):
            if pin.text == app.config_data['pin']:
                popup.dismiss()
                self._show_menu()
            else:
                pin.text = ''
                pin.hint_text = 'Неверный PIN'

        pin.bind(on_text_validate=check)
        btn_ok.bind(on_release=check)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()

    # ---------- главное меню ----------

    def _show_menu(self):
        box = BoxLayout(orientation='vertical', spacing='10dp', padding='10dp')
        btn_settings = Button(text='Настройки')
        btn_exit = Button(text='Выйти из приложения')
        btn_close = Button(text='Продолжить показ')
        box.add_widget(btn_settings)
        box.add_widget(btn_exit)
        box.add_widget(btn_close)

        popup = Popup(title='Меню', content=box,
                      size_hint=(0.5, 0.5), auto_dismiss=False)

        btn_settings.bind(on_release=lambda *a: (popup.dismiss(),
                                               self._show_settings()))
        btn_exit.bind(on_release=lambda *a: App.get_running_app().stop())
        btn_close.bind(on_release=popup.dismiss)
        popup.open()

    # ---------- настройки ----------

    def _show_settings(self):
        app = App.get_running_app()
        cfg = app.config_data

        box = BoxLayout(orientation='vertical', spacing='8dp', padding='10dp')

        # текущая папка
        count = len(self.playlist)
        lbl_folder = Label(
            text='Папка с видео:\n' + cfg['video_dir'] +
                 '\n(видео найдено: ' + str(count) + ')',
            size_hint_y=None, height='90dp')
        box.add_widget(lbl_folder)

        # выбор папки
        btn_browse = Button(text='Выбрать папку...', size_hint_y=None, height='52dp')
        btn_browse.bind(on_release=lambda *a: self._show_folder_chooser(lbl_folder))
        box.add_widget(btn_browse)

        # перемешивание
        row_shuffle = BoxLayout(size_hint_y=None, height='52dp')
        row_shuffle.add_widget(Label(text='Перемешивать видео'))
        chk = CheckBox(active=bool(cfg.get('shuffle')), size_hint_x=None, width='52dp')
        row_shuffle.add_widget(chk)
        box.add_widget(row_shuffle)

        def on_shuffle(checkbox, value):
            cfg['shuffle'] = bool(value)
            app.save_config()
        chk.bind(active=on_shuffle)

        # смена PIN
        btn_pin = Button(text='Сменить PIN-код', size_hint_y=None, height='52dp')
        btn_pin.bind(on_release=lambda *a: self._show_change_pin())
        box.add_widget(btn_pin)

        # закрыть
        btn_close = Button(text='Готово', size_hint_y=None, height='52dp')
        box.add_widget(btn_close)

        popup = Popup(title='Настройки', content=box,
                      size_hint=(0.6, 0.75), auto_dismiss=False)
        btn_close.bind(on_release=popup.dismiss)
        popup.open()

    # ---------- проводник: выбор папки ----------

    def _show_folder_chooser(self, settings_label):
        app = App.get_running_app()
        start = self.cfg['video_dir'] or '/sdcard'
        if not os.path.isdir(start):
            start = '/sdcard'

        box = BoxLayout(orientation='vertical', spacing='6dp', padding='6dp')
        browse_label = Label(size_hint_y=None, height='40dp')
        scroll = ScrollView()
        browse_list = GridLayout(cols=1, spacing='4dp', size_hint_y=None)
        browse_list.bind(minimum_height=browse_list.setter('height'))
        scroll.add_widget(browse_list)

        row = BoxLayout(size_hint_y=None, height='52dp', spacing='8dp')
        btn_ok = Button(text='Выбрать эту папку')
        btn_cancel = Button(text='Отмена')
        row.add_widget(btn_ok)
        row.add_widget(btn_cancel)

        box.add_widget(browse_label)
        box.add_widget(scroll)
        box.add_widget(row)

        popup = Popup(title='Выбор папки с видео', content=box,
                      size_hint=(0.85, 0.85), auto_dismiss=False)

        def fill(path):
            self._browse_path = path
            browse_label.text = path
            browse_list.clear_widgets()
            parent = os.path.dirname(path)
            if parent and parent != path:
                b = Button(text='[..]  Вверх', size_hint_y=None, height='48dp',
                           background_color=(0.4, 0.4, 0.5, 1))
                b.bind(on_release=lambda *a: fill(parent))
                browse_list.add_widget(b)
            try:
                dirs = sorted(d for d in os.listdir(path)
                              if os.path.isdir(os.path.join(path, d)))
            except OSError:
                dirs = []
            if not dirs:
                lbl = Label(text='(нет вложенных папок)',
                            size_hint_y=None, height='48dp')
                browse_list.add_widget(lbl)
            for d in dirs:
                b = Button(text='[папка]  ' + d, size_hint_y=None, height='48dp')
                b.bind(on_release=lambda *a, d=d: fill(os.path.join(path, d)))
                browse_list.add_widget(b)

        def choose(*a):
            self.cfg['video_dir'] = self._browse_path
            app.save_config()
            popup.dismiss()
            self.index = 0
            self._rescan()
            Clock.schedule_once(lambda dt: self._play(0), 0.3)
            settings_label.text = ('Папка с видео:\n' + self.cfg['video_dir'] +
                                   '\n(видео найдено: ' + str(len(self.playlist)) + ')')

        btn_ok.bind(on_release=choose)
        btn_cancel.bind(on_release=popup.dismiss)
        fill(start)
        popup.open()

    # ---------- смена PIN ----------

    def _show_change_pin(self):
        app = App.get_running_app()
        box = BoxLayout(orientation='vertical', spacing='10dp', padding='10dp')
        pin = TextInput(hint_text='Новый PIN (только цифры)', password=True,
                        multiline=False, input_filter='int',
                        size_hint_y=None, height='48dp')
        row = BoxLayout(size_hint_y=None, height='48dp', spacing='10dp')
        btn_ok = Button(text='Сохранить')
        btn_cancel = Button(text='Отмена')
        row.add_widget(btn_ok)
        row.add_widget(btn_cancel)
        box.add_widget(pin)
        box.add_widget(row)

        popup = Popup(title='Смена PIN-кода', content=box,
                      size_hint=(0.5, 0.4), auto_dismiss=False)

        def save(*args):
            text = pin.text.strip()
            if text:
                app.config_data['pin'] = text
                app.save_config()
                popup.dismiss()
            else:
                pin.hint_text = 'PIN не может быть пустым'

        btn_ok.bind(on_release=save)
        btn_cancel.bind(on_release=popup.dismiss)
        popup.open()


class VideoLooperApp(App):
    def build(self):
        self.user_data_dir  # вычислить путь к данным приложения
        self.config_data = self._load_config()
        request_android_permissions()
        Clock.schedule_once(lambda dt: android_setup(), 0)
        self.screen = PlayerScreen()
        return self.screen

    # ---------- хранение настроек (JSON в папке приложения) ----------

    def _config_path(self):
        try:
            folder = self.user_data_dir
        except Exception:
            folder = os.path.expanduser('~')
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass
        return os.path.join(folder, 'videolooper_settings.json')

    def _load_config(self):
        cfg = {'video_dir': DEFAULT_VIDEO_DIR,
               'pin': DEFAULT_PIN,
               'shuffle': False}
        try:
            with open(self._config_path(), encoding='utf-8') as f:
                saved = json.load(f)
            for key in cfg:
                if key in saved:
                    cfg[key] = saved[key]
        except Exception:
            pass  # первый запуск или файл повреждён — берём значения по умолчанию
        return cfg

    def save_config(self):
        try:
            with open(self._config_path(), 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # ---------- жизненный цикл ----------

    def on_start(self):
        # при запуске приложения сразу играем первое видео
        Clock.schedule_once(lambda dt: self.screen._play(0), 0.5)

    def on_resume(self):
        android_setup()   # на всякий случай прячем панели снова
        Clock.schedule_once(lambda dt: self.screen._play(0), 0.2)
        return super().on_resume()

    def on_pause(self):
        return True       # не закрывать приложение при сворачивании


if __name__ == '__main__':
    VideoLooperApp().run()
