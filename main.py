import sys
import json
import os
import csv
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QComboBox, QDateEdit, QInputDialog, QTabWidget, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QFileDialog, QDialog, QCompleter, QAction, QTextEdit, QScrollArea, QListView
)
from PyQt5.QtCore import QDate, QThread, pyqtSignal, QStringListModel, Qt, QEvent, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QMovie, QColor
from PyQt5.QtSvg import QSvgWidget
from PyQt5 import QtSvg
import psycopg2
import requests
import subprocess
import time
import shutil

PROFILES_FILE = 'profiles.json'
PRODUCTS_FILE = 'products.json'

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Загрузка линий из файла (ранее профилей)
def load_lines():
    try:
        with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_lines(lines):
    with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
        json.dump(lines, f, ensure_ascii=False, indent=2)

# Загрузка продуктов из файла
def load_products():
    try:
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

# Сохранение продуктов в файл
def save_products(products):
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

class ProductSearchLineEdit(QLineEdit):
    def __init__(self, products, parent=None):
        super().__init__(parent)
        self.completer = QCompleter(products, self)
        popup = QListView()
        popup.setMouseTracking(True)
        popup.setEditTriggers(QListView.NoEditTriggers)
        popup.setSelectionBehavior(QListView.SelectRows)
        popup.setSelectionMode(QListView.SingleSelection)
        popup.setUniformItemSizes(True)
        popup.setMinimumWidth(400)
        popup.setStyleSheet(
            "QListView {"
            "    background: #1B3B33;"
            "    border-radius: 8px;"
            "    color: #F1F1F1;"
            "    border: 1.5px solid #FF5B00;"
            "    font-size: 18px;"
            "    font-weight: 600;"
            "    selection-background-color: #FF5B00;"
            "    selection-color: #fff;"
            "    padding: 8px 16px;"
            "    outline: none;"
            "}"
            "QListView::item {"
            "    padding: 12px 16px;"
            "    margin: 2px 0px;"
            "    border-radius: 6px;"
            "    min-height: 24px;"
            "    background: transparent;"
            "}"
            "QListView::item:hover {"
            "    background: #FF5B00;"
            "    color: #fff;"
            "    font-weight: bold;"
            "    border-radius: 6px;"
            "}"
            "QListView::item:selected {"
            "    background: #FF5B00;"
            "    color: #fff;"
            "    font-weight: bold;"
            "    border-radius: 6px;"
            "}"
            "QListView::item:alternate {"
            "    background: transparent;"
            "}"
        )
        self.completer.setPopup(popup)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.setCompleter(self.completer)

        # Обработка mouseMoveEvent для подсветки
        popup.viewport().installEventFilter(self)
        self._popup = popup
        
        # Переменные для отслеживания изменений
        self._last_text = ""
        self._popup_initialized = False
        self._popup_interacting = False  # Флаг для отслеживания взаимодействия с popup
        self._popup_height_locked = False  # Флаг для блокировки изменения высоты
        
        # Подключаем сигнал для обновления высоты только при реальном изменении текста
        self.textChanged.connect(self.on_text_changed)
        
        # Подключаем обработку показа popup
        self.completer.activated.connect(self.on_completer_activated_internal)
        
        # Переопределяем метод showPopup для правильной инициализации высоты
        original_show_popup = self.completer.complete
        
        def custom_complete():
            original_show_popup()
            # Небольшая задержка для корректного расчета высоты
            QtCore.QTimer.singleShot(10, self.initialize_popup_height)
        
        self.completer.complete = custom_complete
        
        # Таймер для отложенного обновления высоты
        self._update_timer = QtCore.QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._delayed_update_height)
        
        # Таймер для задержки сброса флага взаимодействия
        self._interaction_timer = QtCore.QTimer()
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.timeout.connect(self._reset_interaction_flag)
        
        # Подключаем обработку скрытия popup
        popup.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._popup.viewport():
            if event.type() == QEvent.MouseMove:
                self._popup_interacting = True
                self._popup_height_locked = True
                # Останавливаем таймер сброса флага
                self._interaction_timer.stop()
                index = self._popup.indexAt(event.pos())
                if index.isValid():
                    self._popup.setCurrentIndex(index)
            elif event.type() == QEvent.MouseButtonPress:
                self._popup_interacting = True
                self._popup_height_locked = True
                self._interaction_timer.stop()
            elif event.type() == QEvent.Leave:
                # Запускаем таймер для задержки сброса флага
                self._interaction_timer.start(200)  # 200ms задержка
        elif obj is self._popup:
            if event.type() == QEvent.Hide:
                self._popup_interacting = False
                self._popup_height_locked = False
                self._popup_initialized = False
                self._interaction_timer.stop()
        return super().eventFilter(obj, event)

    def set_products(self, products):
        model = QStringListModel(products)
        self.completer.setModel(model)
    
    def get_text(self):
        return self.text()
    
    def set_text(self, text):
        self.setText(text)
    
    def on_text_changed(self, text):
        """Обработчик изменения текста - только при реальном изменении пользователем"""
        # Проверяем, что текст действительно изменился
        if text != self._last_text:
            self._last_text = text
            self.update_popup_height()
    
    def initialize_popup_height(self):
        """Инициализация высоты popup при первом показе"""
        self._popup_initialized = True
        self._popup_height_locked = False  # Сбрасываем блокировку при инициализации
        self.update_popup_height()
    
    def update_popup_height(self):
        """Динамически обновляет высоту popup в зависимости от количества совпадений"""
        # Запускаем отложенное обновление для предотвращения частых пересчетов
        self._update_timer.start(50)  # 50ms задержка
    
    def _delayed_update_height(self):
        """Отложенное обновление высоты popup"""
        popup = self.completer.popup()
        
        # Если popup не видим, пользователь взаимодействует с ним, или высота заблокирована, не обновляем высоту
        if not popup.isVisible() or self._popup_interacting or self._popup_height_locked:
            return
            
        model = self.completer.model()
        if not model:
            return
            
        # Подсчитываем количество совпадений
        search_text = self.text().lower()
        match_count = 0
        
        for i in range(model.rowCount()):
            item_text = model.data(model.index(i, 0), Qt.DisplayRole).lower()
            if search_text in item_text:
                match_count += 1
        
        # Вычисляем высоту
        item_height = 48  # Высота одного элемента (padding 12px + margin 2px + min-height 24px + spacing)
        max_items = 12    # Максимальное количество элементов для отображения
        min_height = 60   # Минимальная высота popup
        max_height = 600  # Максимальная высота popup
        
        # Ограничиваем количество отображаемых элементов
        visible_items = min(match_count, max_items)
        
        # Вычисляем высоту с учетом padding popup (16px сверху и снизу)
        calculated_height = max(min_height, visible_items * item_height + 32)
        calculated_height = min(calculated_height, max_height)
        
        # Устанавливаем высоту только если она действительно изменилась
        current_height = popup.height()
        if abs(current_height - calculated_height) > 5:  # Допуск в 5px
            popup.setFixedHeight(calculated_height)
            popup.update()

    def on_completer_activated_internal(self, text):
        matches = self.completer.model().match(
            self.completer.model().index(0, 0), Qt.DisplayRole, text, -1, Qt.MatchExactly
        )
        if matches and matches[0].isValid():
            self._popup.setCurrentIndex(matches[0])

    def _reset_interaction_flag(self):
        """Сброс флага взаимодействия с проверкой позиции курсора"""
        popup = self.completer.popup()
        if popup.isVisible():
            # Проверяем, находится ли курсор в пределах popup
            cursor_pos = popup.mapFromGlobal(popup.cursor().pos())
            popup_rect = popup.rect()
            
            # Если курсор за пределами popup, сбрасываем флаги
            if not popup_rect.contains(cursor_pos):
                self._popup_interacting = False
                self._popup_height_locked = False
        else:
            # Если popup не видим, сбрасываем флаги
            self._popup_interacting = False
            self._popup_height_locked = False

class DBWorker(QThread):
    result_ready = pyqtSignal(object, object, object, object)  # rows, colnames, error, status
    def __init__(self, conn_params, gtin, date_from, date_to):
        super().__init__()
        self.conn_params = conn_params
        self.gtin = gtin
        self.date_from = date_from
        self.date_to = date_to
    def run(self):
        try:
            conn = psycopg2.connect(**self.conn_params)
            cur = conn.cursor()
            sql = "SELECT * FROM codes WHERE code LIKE %s AND dtime_ins::date >= %s"
            params = [f"%{self.gtin}%", self.date_from]
            if self.date_to:
                sql += " AND dtime_ins::date <= %s"
                params.append(self.date_to)
            cur.execute(sql, params)
            rows = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]
            cur.close()
            conn.close()
            self.result_ready.emit(rows, colnames, None, 'ok')
        except Exception as e:
            self.result_ready.emit(None, None, str(e), 'error')

class DBWorkerWithDateField(QThread):
    result_ready = pyqtSignal(object, object, object, object)  # rows, colnames, error, status
    def __init__(self, conn_params, gtin, date_from, date_to, date_field):
        super().__init__()
        self.conn_params = conn_params
        self.gtin = gtin
        self.date_from = date_from
        self.date_to = date_to
        self.date_field = date_field
    def run(self):
        try:
            conn = psycopg2.connect(**self.conn_params)
            cur = conn.cursor()
            sql = f"SELECT * FROM codes WHERE code LIKE %s AND {self.date_field}::date >= %s"
            params = [f"%{self.gtin}%", self.date_from]
            if self.date_to:
                sql += f" AND {self.date_field}::date <= %s"
                params.append(self.date_to)
            cur.execute(sql, params)
            rows = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]
            cur.close()
            conn.close()
            self.result_ready.emit(rows, colnames, None, 'ok')
        except Exception as e:
            self.result_ready.emit(None, None, str(e), 'error')

class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle('Загрузка...')
        self.setFixedSize(340, 160)
        layout = QVBoxLayout()
        # SVG-анимация (круговой лоадер)
        svg_data = '''
        <svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
          <circle cx="32" cy="32" r="28" stroke="#FF5B00" stroke-width="8" fill="none" opacity="0.2"/>
          <circle cx="32" cy="32" r="28" stroke="#FF5B00" stroke-width="8" fill="none"
            stroke-dasharray="44 100" stroke-linecap="round">
            <animateTransform attributeName="transform" type="rotate" from="0 32 32" to="360 32 32" dur="1s" repeatCount="indefinite"/>
          </circle>
        </svg>
        '''
        svg_widget = QSvgWidget()
        svg_widget.load(bytearray(svg_data, encoding='utf-8'))
        svg_widget.setFixedSize(64, 64)
        layout.addWidget(svg_widget, alignment=QtCore.Qt.AlignCenter)
        label = QLabel('Пожалуйста, подождите...')
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)
        self.setLayout(layout)
        self.setWindowFlags((self.windowFlags() | QtCore.Qt.CustomizeWindowHint) & ~QtCore.Qt.WindowCloseButtonHint & ~QtCore.Qt.WindowContextHelpButtonHint)

class CompleterHoverDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QtWidgets.QStyle.State_MouseOver:
            painter.save()
            painter.setBrush(QtGui.QColor('#FF5B00'))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(option.rect)
            painter.setPen(QtGui.QColor('#fff'))
            font = option.font
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(option.rect.adjusted(8, 0, 0, 0), QtCore.Qt.AlignVCenter, index.data())
            painter.restore()
        else:
            super().paint(painter, option, index)

class MainTab(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        # Поиск по продуктам
        search_layout = QHBoxLayout()
        # Используем новый ProductSearchLineEdit с пустым списком продуктов (будет обновлен позже)
        self.product_search = ProductSearchLineEdit([], self)
        self.product_search.setPlaceholderText('Поиск продукта...')
        self.product_search.setFixedHeight(52)
        self.product_search.setFixedWidth(400)
        self.product_search.setStyleSheet('''
            QLineEdit {
                border-radius: 18px;
                border: 1.5px solid #5A7C7C;
                background: #15332B;
                color: #F1F1F1;
                padding-left: 16px;
                font-size: 18px;
            }
        ''')
        # Подключаем сигналы для нового поиска
        self.product_search.textEdited.connect(self.on_search_text)
        self.product_search.returnPressed.connect(self.on_search_select)
        self.product_search.completer.activated[str].connect(self.on_completer_activated)
        search_layout.addWidget(self.product_search)
        layout.addLayout(search_layout)
        # Линии
        line_layout = QHBoxLayout()
        self.line_combo = QComboBox()
        self.line_combo.addItem('--- Выберите линию ---')
        self.line_combo.addItems(self.parent.lines.keys())
        self.line_combo.currentTextChanged.connect(self.on_line_select)
        line_layout.addWidget(QLabel('Линия:'))
        line_layout.addWidget(self.line_combo)
        layout.addLayout(line_layout)
        # Продукты (с аннотацией GTIN)
        prod_layout = QHBoxLayout()
        self.product_combo = QComboBox()
        self.update_products()
        self.product_combo.setItemDelegate(ProductDelegate(self))
        self.product_combo.currentTextChanged.connect(self.on_product_changed)
        prod_layout.addWidget(QLabel('Продукт:'))
        prod_layout.addWidget(self.product_combo)
        layout.addLayout(prod_layout)
        # Выбор поля даты
        date_field_layout = QHBoxLayout()
        date_field_layout.addWidget(QLabel('Искать по:'))
        self.date_field_combo = QComboBox()
        self.date_field_combo.addItem('Дата записи в БД (dtime_ins)')
        self.date_field_combo.addItem('Дата производства (production_date)')
        date_field_layout.addWidget(self.date_field_combo)
        layout.addLayout(date_field_layout)
        # Дата с/по
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel('Дата с:'))
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDate(QDate.currentDate())
        date_row.addWidget(self.date_from)
        date_row.addWidget(QLabel('Дата по:'))
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setSpecialValueText('')
        self.date_to.setDisplayFormat('yyyy-MM-dd')
        self.date_to.setDate(QDate.currentDate())
        date_row.addWidget(self.date_to)
        layout.addLayout(date_row)
        # Кнопка проверки
        self.check_btn = QPushButton('Проверить')
        self.check_btn.clicked.connect(self.check_codes)
        layout.addWidget(self.check_btn)
        # Таблица для результатов
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(0)
        self.result_table.setRowCount(0)
        self.result_table.setVisible(False)
        layout.addWidget(self.result_table)
        # Кнопка выгрузки в CSV
        self.export_btn = QPushButton('Выгрузить в CSV')
        self.export_btn.setVisible(False)
        self.export_btn.clicked.connect(self.export_to_csv)
        layout.addWidget(self.export_btn)
        # Кнопка очистки результатов
        self.clear_btn = QPushButton('Очистить результаты')
        self.clear_btn.setVisible(False)
        self.clear_btn.setStyleSheet('background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #444, stop:1 #222); color: #fff; font-weight: 600; border-radius: 10px; padding: 10px 24px; margin: 8px 0;')
        self.clear_btn.clicked.connect(self.clear_results)
        layout.addWidget(self.clear_btn)
        # Количество найденных строк
        self.count_label = QLabel()
        self.count_label.setVisible(False)
        font_count = self.count_label.font()
        font_count.setPointSize(18)
        font_count.setBold(True)
        self.count_label.setFont(font_count)
        self.count_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.count_label)
        # Крупный статус результата
        self.status_label = QLabel()
        self.status_label.setVisible(False)
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        font = self.status_label.font()
        font.setPointSize(48)
        font.setBold(True)
        self.status_label.setFont(font)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def clear_results(self):
        self.result_table.setVisible(False)
        self.export_btn.setVisible(False)
        self.clear_btn.setVisible(False)
        self.count_label.setVisible(False)
        self.status_label.setVisible(False)

    def on_product_changed(self, name):
        # Автоматическая очистка результатов при смене продукта
        self.clear_results()

    def on_line_select(self, name):
        if name in self.parent.lines:
            self.parent.current_line = name
        else:
            self.parent.current_line = None
        # Автоматическая очистка результатов при смене линии
        self.clear_results()

    def check_codes(self):
        line_name = self.line_combo.currentText()
        if line_name not in self.parent.lines:
            QMessageBox.critical(self, 'Ошибка', 'Выберите линию!')
            return
        product_name = self.product_combo.currentText()
        if product_name not in self.parent.products:
            QMessageBox.critical(self, 'Ошибка', 'Выберите продукт!')
            return
        line = self.parent.lines[line_name]
        gtin = self.parent.products[product_name]
        date_from = self.date_from.date().toString('yyyy-MM-dd')
        date_to = self.date_to.date().toString('yyyy-MM-dd') if self.date_to.date() else None
        # Выбор поля даты
        date_field = 'dtime_ins'
        if self.date_field_combo.currentIndex() == 1:
            date_field = 'production_date'
        conn_params = {
            'host': line['ip'],
            'port': line['port'],
            'user': line['user'],
            'password': line['password'],
            'dbname': line['dbname']
        }
        # Показываем окно загрузки
        self.loading = LoadingDialog(self)
        self.loading.show()
        # Запускаем поток
        self.worker = DBWorkerWithDateField(conn_params, gtin, date_from, date_to, date_field)
        self.worker.result_ready.connect(self.on_db_result)
        self.worker.start()

    def on_db_result(self, rows, colnames, error, status):
        self.loading.close()
        if status == 'error':
            self.result_table.setVisible(False)
            self.export_btn.setVisible(False)
            self.clear_btn.setVisible(False)
            self.count_label.setVisible(False)
            self.status_label.setText('<span style="color:#E53935">ОШИБКА</span>')
            self.status_label.setVisible(True)
            QMessageBox.critical(self, 'Ошибка подключения', error)
            return
        if not rows:
            self.result_table.setVisible(False)
            self.export_btn.setVisible(False)
            self.clear_btn.setVisible(True)
            self.count_label.setVisible(True)
            self.count_label.setText('Найдено строк: 0')
            self.status_label.setText('<span style="color:#E53935">НЕТ ЗАПИСЕЙ</span>')
            self.status_label.setVisible(True)
            return
        self.result_table.setVisible(True)
        self.export_btn.setVisible(True)
        self.clear_btn.setVisible(True)
        self.count_label.setVisible(True)
        self.count_label.setText(f'Найдено строк: {len(rows)}')
        self.status_label.setText('<span style="color:#43A047">OK</span>')
        self.status_label.setVisible(True)
        self.result_table.setColumnCount(len(colnames))
        self.result_table.setRowCount(len(rows))
        self.result_table.setHorizontalHeaderLabels(colnames)
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                self.result_table.setItem(i, j, QTableWidgetItem(str(val)))
        self.result_table.resizeColumnsToContents()

    def export_to_csv(self):
        if self.result_table.rowCount() == 0:
            QMessageBox.warning(self, 'Выгрузка', 'Нет данных для выгрузки!')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Сохранить как CSV', '', 'CSV Files (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                # Заголовки вручную, чтобы всегда были в кавычках
                headers = [f'"{self.result_table.horizontalHeaderItem(i).text()}"' for i in range(self.result_table.columnCount())]
                f.write(','.join(headers) + '\n')
                # Индексы столбцов, которые всегда должны быть в кавычках
                special_cols = []
                for i in range(self.result_table.columnCount()):
                    col_name = self.result_table.horizontalHeaderItem(i).text().strip().lower().replace('_', '')
                    if col_name in ('code', 'grcode', 'sscc'):
                        special_cols.append(i)
                for row in range(self.result_table.rowCount()):
                    rowdata = []
                    for col in range(self.result_table.columnCount()):
                        item = self.result_table.item(row, col)
                        val = item.text() if item and item.text() else ''
                        if val == 'None':
                            val = ''
                        # Для нужных столбцов — всегда в кавычках и с экранированием
                        if col in special_cols and val != '':
                            val = '"' + val.replace('"', '""') + '"'
                        rowdata.append(val)
                    f.write(','.join(rowdata) + '\n')
            QMessageBox.information(self, 'Выгрузка завершена', f'Данные успешно сохранены в {path}')
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка', f'Ошибка при сохранении: {e}')

    def on_search_text(self, text):
        # Автоматически подсвечивать первый совпадающий продукт
        idx = self.product_combo.findText(text, QtCore.Qt.MatchStartsWith)
        if idx != -1:
            self.product_combo.setCurrentIndex(idx)

    def on_search_select(self):
        text = self.product_search.text()
        idx = self.product_combo.findText(text, QtCore.Qt.MatchExactly)
        if idx != -1:
            self.product_combo.setCurrentIndex(idx)

    def on_completer_activated(self, text):
        idx = self.product_combo.findText(text, QtCore.Qt.MatchExactly)
        if idx != -1:
            self.product_combo.setCurrentIndex(idx)

    def update_products(self):
        current = self.product_combo.currentText()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        # Для автодополнения
        names = list(self.parent.products.keys())
        self.product_search.set_products(names)
        for name in names:
            gtin = self.parent.products[name]
            self.product_combo.addItem(f'{name}', gtin)
        # Восстановить выбор, если он есть
        idx = self.product_combo.findText(current)
        if idx != -1:
            self.product_combo.setCurrentIndex(idx)
        self.product_combo.blockSignals(False)

    def update_lines(self):
        current = self.line_combo.currentText()
        self.line_combo.blockSignals(True)
        self.line_combo.clear()
        self.line_combo.addItem('--- Выберите линию ---')
        self.line_combo.addItems(self.parent.lines.keys())
        idx = self.line_combo.findText(current)
        if idx != -1:
            self.line_combo.setCurrentIndex(idx)
        self.line_combo.blockSignals(False)

class ProductDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        name = index.data(QtCore.Qt.DisplayRole)
        gtin = index.data(QtCore.Qt.UserRole) or index.data(QtCore.Qt.ToolTipRole) or ''
        if not gtin:
            gtin = index.model().data(index, QtCore.Qt.UserRole)
        painter.save()
        rect = option.rect
        # Выделение при выборе или наведении
        if option.state & (QtWidgets.QStyle.State_Selected | QtWidgets.QStyle.State_MouseOver):
            painter.setBrush(QColor('#2196F3'))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(rect)
            text_color = QtCore.Qt.white
        else:
            text_color = QtCore.Qt.white
        # Основной текст (название)
        painter.setPen(text_color)
        font = option.font
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect.left()+8, rect.top()+22, name)
        # Аннотация (GTIN)
        font.setPointSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QtCore.Qt.gray if not (option.state & (QtWidgets.QStyle.State_Selected | QtWidgets.QStyle.State_MouseOver)) else QtCore.Qt.white)
        painter.drawText(rect.left()+8, rect.top()+60, f'GTIN: {gtin}')
        painter.restore()
    def sizeHint(self, option, index):
        return QtCore.QSize(320, 74)

class ProductsTab(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.selected_name = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        # Список продуктов
        self.list = QListWidget()
        self.list.setMinimumWidth(360)
        self.list.currentItemChanged.connect(self.on_select)
        self.update_list()
        main_layout.addWidget(self.list, 4)
        # Форма справа
        form_layout = QVBoxLayout()
        self.name_edit = QLineEdit()
        self.gtin_edit = QLineEdit()
        row1 = QHBoxLayout()
        row1.addWidget(QLabel('Название:'))
        row1.addWidget(self.name_edit)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel('GTIN:'))
        row2.addWidget(self.gtin_edit)
        form_layout.addLayout(row1)
        form_layout.addLayout(row2)
        # Кнопки
        btns = QHBoxLayout()
        add_btn = QPushButton('Добавить')
        add_btn.clicked.connect(self.add_product)
        save_btn = QPushButton('Сохранить')
        save_btn.clicked.connect(self.save_product)
        del_btn = QPushButton('Удалить')
        del_btn.clicked.connect(self.del_product)
        import_btn = QPushButton('Импорт из файла')
        import_btn.clicked.connect(self.import_from_file)
        btns.addWidget(add_btn)
        btns.addWidget(save_btn)
        btns.addWidget(del_btn)
        btns.addWidget(import_btn)
        form_layout.addLayout(btns)
        form_layout.addStretch()
        main_layout.addLayout(form_layout, 3)
        self.setLayout(main_layout)

    def update_list(self):
        self.list.clear()
        for name in self.parent.products:
            self.list.addItem(name)

    def on_select(self, curr, prev):
        if curr:
            name = curr.text()
            self.selected_name = name
            self.name_edit.setText(name)
            self.gtin_edit.setText(self.parent.products[name])
        else:
            self.selected_name = None
            self.name_edit.clear()
            self.gtin_edit.clear()

    def add_product(self):
        self.name_edit.clear()
        self.gtin_edit.clear()
        self.list.clearSelection()
        self.selected_name = None

    def save_product(self):
        name = self.name_edit.text()
        gtin = self.gtin_edit.text()
        if not name or not gtin:
            QMessageBox.warning(self, 'Ошибка', 'Заполните все поля!')
            return
        # Если редактируем — удалить старое имя, если оно изменилось
        if self.selected_name and self.selected_name != name:
            del self.parent.products[self.selected_name]
        self.parent.products[name] = gtin
        save_products(self.parent.products)
        self.update_list()
        self.parent.tabs.widget(0).update_products()
        # Выделить сохранённый
        items = self.list.findItems(name, QtCore.Qt.MatchExactly)
        if items:
            self.list.setCurrentItem(items[0])

    def del_product(self):
        if not self.selected_name:
            return
        del self.parent.products[self.selected_name]
        save_products(self.parent.products)
        self.update_list()
        self.parent.tabs.widget(0).update_products()
        self.selected_name = None
        self.name_edit.clear()
        self.gtin_edit.clear()

    def import_from_file(self):
        import json
        path, _ = QFileDialog.getOpenFileName(self, 'Выберите файл продуктов', '', 'JSON Files (*.json)')
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            count = 0
            for item in data:
                name = item.get('Name')
                gtin = item.get('Gtin')
                if name and gtin:
                    self.parent.products[name] = gtin
                    count += 1
            save_products(self.parent.products)
            self.update_list()
            self.parent.tabs.widget(0).update_products()
            QMessageBox.information(self, 'Импорт завершён', f'Импортировано продуктов: {count}')
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка импорта', str(e))

class LinesTab(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.selected_name = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.on_select)
        self.update_list()
        main_layout.addWidget(self.list, 2)
        form_layout = QVBoxLayout()
        # Новое поле для имени линии
        name_row = QHBoxLayout()
        name_label = QLabel('Название линии:')
        self.line_name_edit = QLineEdit()
        name_row.addWidget(name_label)
        name_row.addWidget(self.line_name_edit)
        form_layout.addLayout(name_row)
        self.inputs = {}
        fields = ['IP адрес', 'Порт', 'Логин', 'Пароль', 'База данных']
        for field in fields:
            row = QHBoxLayout()
            label = QLabel(field+':')
            edit = QLineEdit()
            if field == 'Пароль':
                edit.setEchoMode(QLineEdit.Password)
            row.addWidget(label)
            row.addWidget(edit)
            self.inputs[field] = edit
            form_layout.addLayout(row)
        btns = QHBoxLayout()
        add_btn = QPushButton('Добавить')
        add_btn.clicked.connect(self.add_line)
        save_btn = QPushButton('Сохранить')
        save_btn.clicked.connect(self.save_line)
        del_btn = QPushButton('Удалить')
        del_btn.clicked.connect(self.del_line)
        import_btn = QPushButton('Импорт из файла')
        import_btn.clicked.connect(self.import_from_appsettings)
        btns.addWidget(add_btn)
        btns.addWidget(save_btn)
        btns.addWidget(del_btn)
        btns.addWidget(import_btn)
        form_layout.addLayout(btns)
        form_layout.addStretch()
        main_layout.addLayout(form_layout, 3)
        self.setLayout(main_layout)

    def update_list(self):
        self.list.clear()
        for name in self.parent.lines:
            self.list.addItem(name)

    def on_select(self, curr, prev):
        if curr:
            name = curr.text()
            self.selected_name = name
            line = self.parent.lines[name]
            self.line_name_edit.setText(name)
            self.inputs['IP адрес'].setText(line['ip'])
            self.inputs['Порт'].setText(line['port'])
            self.inputs['Логин'].setText(line['user'])
            self.inputs['Пароль'].setText(line['password'])
            self.inputs['База данных'].setText(line['dbname'])
        else:
            self.selected_name = None
            self.line_name_edit.clear()
            for edit in self.inputs.values():
                edit.clear()

    def add_line(self):
        for edit in self.inputs.values():
            edit.clear()
        self.line_name_edit.clear()
        self.list.clearSelection()
        self.selected_name = None

    def save_line(self):
        data = {k: self.inputs[k].text() for k in self.inputs}
        name = self.line_name_edit.text().strip()
        if not all(data.values()) or not name:
            QMessageBox.warning(self, 'Ошибка', 'Заполните все поля и имя линии!')
            return
        # Если редактируем и имя изменилось — переименовать ключ
        if self.selected_name and self.selected_name != name:
            if name in self.parent.lines:
                QMessageBox.warning(self, 'Ошибка', f'Линия с именем "{name}" уже существует!')
                return
            self.parent.lines[name] = self.parent.lines.pop(self.selected_name)
        self.parent.lines[name] = {
            'ip': data['IP адрес'],
            'port': data['Порт'],
            'user': data['Логин'],
            'password': data['Пароль'],
            'dbname': data['База данных']
        }
        save_lines(self.parent.lines)
        self.update_list()
        self.parent.tabs.widget(0).update_lines()
        # Выделить сохранённую
        items = self.list.findItems(name, QtCore.Qt.MatchExactly)
        if items:
            self.list.setCurrentItem(items[0])
        self.selected_name = name

    def del_line(self):
        if not self.selected_name:
            QMessageBox.warning(self, 'Удаление линии', 'Сначала выберите линию для удаления.')
            return
        reply = QMessageBox.question(self, 'Удаление линии', f'Удалить линию "{self.selected_name}"?', QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            del self.parent.lines[self.selected_name]
            save_lines(self.parent.lines)
            self.update_list()
            self.parent.tabs.widget(0).update_lines()
            main_tab = self.parent.tabs.widget(0)
            if main_tab.line_combo.currentText() == self.selected_name:
                main_tab.line_combo.setCurrentIndex(0)
            self.selected_name = None
            for edit in self.inputs.values():
                edit.clear()
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка', f'Ошибка при удалении: {e}')

    def import_from_appsettings(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Выберите appsettings.json', os.getcwd(), 'JSON Files (*.json)')
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            pg = data['DataBase']['PostgreSql']
            line = {
                'ip': pg['Server'],
                'port': str(pg['Port']),
                'user': pg['User'],
                'password': pg['Password'],
                'dbname': pg['DataBase']
            }
            name, ok = QInputDialog.getText(self, 'Импорт линии', 'Имя для импортируемой линии:', text='Из appsettings.json')
            if not ok or not name:
                return
            if name in self.parent.lines:
                reply = QMessageBox.question(self, 'Линия уже существует', f'Линия "{name}" уже есть. Обновить?', QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return
            self.parent.lines[name] = line
            save_lines(self.parent.lines)
            self.update_list()
            self.parent.tabs.widget(0).update_lines()
            QMessageBox.information(self, 'Импорт завершён', f'Линия "{name}" импортирована!')
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка импорта', str(e))

class InfoTab(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.info_label = QLabel()
        layout.addWidget(self.info_label)
        self.setLayout(layout)
        self.update_info()

    def update_info(self):
        if self.parent.current_line and self.parent.current_line in self.parent.lines:
            line = self.parent.lines[self.parent.current_line]
            text = f"<b>Линия:</b> {self.parent.current_line}<br>"
            text += f"<b>IP:</b> {line['ip']}<br>"
            text += f"<b>Порт:</b> {line['port']}<br>"
            text += f"<b>Логин:</b> {line['user']}<br>"
            text += f"<b>БД:</b> {line['dbname']}<br>"
        else:
            text = "Линия не выбрана."
        self.info_label.setText(text)

class HelpTab(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.expanded_sections = set()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        # Создаем прокручиваемую область
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('''
            QScrollArea {
                border: none;
                background: #1B3B33;
            }
            QScrollBar:vertical {
                background: #15332B;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #FF5B00;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        ''')
        help_widget = QWidget()
        help_layout = QVBoxLayout()
        # Заголовок
        title = QLabel('РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ')
        title.setStyleSheet('''
            QLabel {
                color: #FF5B00;
                font-size: 26px;
                font-weight: bold;
                padding: 20px;
                background: #15332B;
                border-radius: 10px;
                margin-bottom: 20px;
                letter-spacing: 1px;
            }
        ''')
        title.setAlignment(QtCore.Qt.AlignCenter)
        help_layout.addWidget(title)
        self.sections = {}
        # Главная
        main_section = self.create_collapsible_section(
            '1. ГЛАВНАЯ ВКЛАДКА — Проверка записей',
            '''
            <div style="color: #F1F1F1; font-size: 16px; line-height: 1.7;">
                <b>Пошаговая инструкция:</b>
                <ol>
                    <li><b>Выберите продукт</b> через строку поиска или выпадающий список.<br>
                        <span style="color:#FF5B00;">Совет:</span> используйте быстрый поиск по первым буквам.</li>
                    <li><b>Выберите линию</b> из выпадающего списка.<br>
                        <span style="color:#FF5B00;">Если линий нет</span> — добавьте их на вкладке "Линии".</li>
                    <li><b>Настройте фильтр по дате</b> ("Дата с" и "Дата по") и выберите поле для фильтрации ("Дата записи в БД" или "Дата производства").</li>
                    <li><b>Нажмите кнопку "Проверить"</b> и дождитесь завершения поиска.</li>
                    <li><b>Результаты:</b>
                        <ul>
                            <li>Появится таблица с найденными записями и их количеством.</li>
                            <li>Статус <span style="color:#43A047;">OK</span> — записи найдены, <span style="color:#E53935;">НЕТ ЗАПИСЕЙ</span> — ничего не найдено.</li>
                            <li>Для очистки результатов используйте кнопку <b>"Очистить результаты"</b> (или смените продукт/линию — очистка произойдет автоматически).</li>
                        </ul>
                    </li>
                </ol>
            </div>
            '''
        )
        help_layout.addWidget(main_section)
        # Экспорт и работа с CSV
        export_section = self.create_collapsible_section(
            '2. ВЫГРУЗКА В CSV — Формат и особенности',
            '''
            <div style="color: #F1F1F1; font-size: 16px; line-height: 1.7;">
                <b>Как сохранить результаты:</b>
                <ol>
                    <li>Нажмите <b>"Выгрузить в CSV"</b> под таблицей результатов.</li>
                    <li>Выберите путь и имя файла.</li>
                </ol>
                <b>Формат CSV:</b>
                <ul>
                    <li>Заголовки <b>всегда</b> в двойных кавычках: <code>"id","dtime_ins","code",...</code></li>
                    <li>Поля <b>code</b>, <b>grcode</b>, <b>sscc</b> — <span style="color:#FF5B00;">всегда в двойных кавычках</span> (даже если внутри есть запятые или кавычки).</li>
                    <li>Остальные значения — без кавычек.</li>
                    <li>Пустые значения и None — просто пусто (между запятыми).</li>
                    <li>Разделитель — запятая, без пробелов.</li>
                </ul>
                <b>Пример строки:</b>
                <pre style="background:#222;padding:8px;border-radius:6px;">"id","dtime_ins","code","grcode","sscc"
1534,2025-03-14 11:41:16.446,"010460...","91EE10...","92pNF..."
</pre>
                <b>Совет:</b> Открывайте такие файлы не в Excel, а в текстовом редакторе Блокнот или Notepad++.
            </div>
            '''
        )
        help_layout.addWidget(export_section)
        # Продукты
        products_section = self.create_collapsible_section(
            '3. ВКЛАДКА "ПРОДУКТЫ" — Управление списком',
            '''
            <div style="color: #F1F1F1; font-size: 16px; line-height: 1.7;">
                <b>Добавление/редактирование:</b>
                <ol>
                    <li>Нажмите "Добавить" для нового продукта или выберите существующий для редактирования.</li>
                    <li>Заполните название и GTIN.</li>
                    <li>Сохраните изменения.</li>
                </ol>
                <b>Импорт:</b> Поддерживается импорт из JSON-файла с массивом объектов <code>[{"Name": ..., "Gtin": ...}]</code>.
            </div>
            '''
        )
        help_layout.addWidget(products_section)
        # Линии
        lines_section = self.create_collapsible_section(
            '4. ВКЛАДКА "ЛИНИИ" — Подключения к БД',
            '''
            <div style="color: #F1F1F1; font-size: 16px; line-height: 1.7;">
                <b>Добавление/редактирование:</b>
                <ol>
                    <li>Нажмите "Добавить" для новой линии или выберите существующую для редактирования.</li>
                    <li>Заполните параметры подключения (IP, порт, логин, пароль, БД).</li>
                    <li>Сохраните изменения.</li>
                </ol>
                <b>Импорт:</b> Поддерживается импорт из <code>appsettings.json</code> (формат 1С или .NET).</div>
            '''
        )
        help_layout.addWidget(lines_section)
        # Советы и FAQ
        tips_section = self.create_collapsible_section(
            '5. СОВЕТЫ, FAQ и устранение неполадок',
            '''
            <div style="color: #F1F1F1; font-size: 16px; line-height: 1.7;">
                <ul>
                    <li><b>Очистка результатов:</b> используйте кнопку "Очистить результаты" или просто смените продукт/линию.</li>
                    <li><b>Быстрый поиск:</b> используйте строку поиска для автодополнения по названию.</li>
                    <li><b>Проблемы с подключением:</b> проверьте параметры линии, доступность сервера и таблицу <code>codes</code> в БД.</li>
                    <li><b>Пустые значения в CSV:</b> это нормально, если данных нет или они были None.</li>
                    <li><b>Экспорт больших таблиц:</b> Excel может не сразу корректно открыть файл — используйте "Данные → Из текста/CSV".</li>
                </ul>
            </div>
            '''
        )
        help_layout.addWidget(tips_section)
        help_widget.setLayout(help_layout)
        scroll.setWidget(help_widget)
        layout.addWidget(scroll)
        self.setLayout(layout)

    def create_collapsible_section(self, title, content_html):
        section_widget = QWidget()
        section_layout = QVBoxLayout()
        section_layout.setSpacing(0)
        section_layout.setContentsMargins(0, 0, 0, 0)
        # Кнопка-заголовок
        header_button = QPushButton(title)
        header_button.setCheckable(True)
        header_button.setStyleSheet('''
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1B3B33, stop:1 #2E4C44);
                color: #FFF9F3;
                font-size: 19px;
                font-weight: 600;
                padding: 16px 28px 16px 32px;
                border: none;
                border-radius: 10px;
                margin: 10px 0 0 0;
                text-align: left;
                position: relative;
                transition: background 0.3s, color 0.3s;
                box-shadow: 0 2px 8px rgba(255, 184, 77, 0.10);
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFB84D, stop:1 #2E4C44);
                color: #fff;
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFB84D, stop:1 #FF8C42);
                color: #2E4C44;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
                box-shadow: 0 4px 18px 0 rgba(255,184,77,0.18);
            }
            QPushButton::before {
                content: '';
                display: block;
                position: absolute;
                left: 0; top: 0; bottom: 0;
                width: 7px;
                background: #FFB84D;
                border-radius: 7px 0 0 7px;
            }
        ''')
        header_button.setIcon(QtGui.QIcon())
        header_button.setLayoutDirection(QtCore.Qt.LeftToRight)
        # Содержимое
        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(20, 15, 20, 20)
        content_text = QTextEdit()
        content_text.setHtml(content_html)
        content_text.setReadOnly(True)
        content_text.setMaximumHeight(400)
        content_text.setStyleSheet('''
            QTextEdit {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22343C, stop:1 #1B3B33);
                border: 2px solid #FFB84D;
                border-top: none;
                border-radius: 0 0 10px 10px;
                padding: 16px;
                color: #FFF9F3;
                font-size: 16px;
                selection-background-color: #FFB84D;
                selection-color: #2E4C44;
                transition: max-height 0.3s;
            }
        ''')
        content_layout.addWidget(content_text)
        content_widget.setLayout(content_layout)
        content_widget.setVisible(False)
        # Анимация раскрытия
        def toggle_content(checked, content=content_widget):
            content.setVisible(checked)
            if checked:
                content.setMaximumHeight(1000)
            else:
                content.setMaximumHeight(0)
        header_button.toggled.connect(toggle_content)
        section_layout.addWidget(header_button)
        section_layout.addWidget(content_widget)
        section_widget.setLayout(section_layout)
        return section_widget

class UpdateTab(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.status_label = QLabel('')
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.setStyleSheet('font-size: 18px; color: #FF8C42;')
        layout.addWidget(self.status_label)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.update_btn = QPushButton('Проверить\nи обновить')
        self.update_btn.setFixedHeight(64)
        self.update_btn.setFixedWidth(220)
        self.update_btn.setStyleSheet('font-size: 22px; border-radius: 18px; text-align: center; line-height: 120%;')
        self.update_btn.clicked.connect(self.start_update)
        layout.addWidget(self.update_btn)
        layout.addStretch(1)
        self.setLayout(layout)

    def start_update(self):
        self.update_btn.setEnabled(False)
        self.status_label.setText('Проверка обновлений...')
        QtCore.QTimer.singleShot(100, self.check_for_update_and_run)

    def check_for_update_and_run(self):
        api_url = "https://api.github.com/repos/Andrejj12380/CheckDB/releases/latest"
        try:
            r = requests.get(api_url)
            latest = r.json()
            if "assets" not in latest or not latest["assets"]:
                self.status_label.setText('Нет доступных обновлений на GitHub!')
                self.update_btn.setEnabled(True)
                return
            exe_name = "CheckDB.exe"
            for asset in latest["assets"]:
                if asset["name"] == exe_name:
                    download_url = asset["browser_download_url"]
                    break
            else:
                self.status_label.setText('Не найден файл обновления!')
                self.update_btn.setEnabled(True)
                return
            # Скачиваем с прогрессом
            self.status_label.setText('Скачивание обновления...')
            self.progress.setVisible(True)
            new_exe_path = os.path.join(os.path.dirname(sys.executable), "CheckDB_new.exe")
            with requests.get(download_url, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                downloaded = 0
                with open(new_exe_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                percent = int(downloaded * 100 / total)
                                self.progress.setValue(percent)
            self.progress.setValue(100)
            self.status_label.setText('Обновление скачано! Перезапуск...')
            QtCore.QTimer.singleShot(1200, lambda: self.restart_with_new(new_exe_path))
        except Exception as e:
            self.status_label.setText(f'Ошибка: {e}')
            self.update_btn.setEnabled(True)
            self.progress.setVisible(False)

    def restart_with_new(self, new_exe_path):
        # Запустить скачанный exe и выйти
        try:
            subprocess.Popen([new_exe_path])
        except Exception as e:
            self.status_label.setText(f'Ошибка запуска: {e}')
            return
        QtCore.QCoreApplication.quit()

class DBChecker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Проверка записей в БД')
        self.setGeometry(200, 200, 1280, 720)
        self.set_industrial_style()
        self.setWindowIcon(QIcon(resource_path('flash.ico')))
        self.lines = load_lines()
        self.products = load_products()
        self.current_line = None
        self.init_ui()

    def set_industrial_style(self):
        self.setStyleSheet('''
            QWidget {
                background: #15332B;
                color: #F1F1F1;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 16px;
            }
            QTabWidget::pane {
                border: none;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #1B3B33, stop:1 #15332B);
                border-radius: 15px;
                margin-top: -2px;
            }
            QTabBar {
                qproperty-drawBase: 0;
                alignment: center;
            }
            QTabBar::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #2E4C44, stop:1 #1B3B33);
                color: #FF8C42;
                border-radius: 12px 12px 0 0;
                padding: 14px 20px;
                min-width: 135px;
                margin-right: 4px;
                font-weight: 600;
                font-size: 17px;
                border: 2px solid transparent;
                border-bottom: none;
                position: relative;
            }
            QTabBar::tab:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #FF5B00, stop:1 #E64A19);
                color: #FFFFFF;
                border: 2px solid #FF8C42;
                border-bottom: none;
                transform: translateY(-2px);
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #FF5B00, stop:1 #E64A19);
                color: #FFFFFF;
                border: 2px solid #FF8C42;
                border-bottom: none;
                font-weight: 700;
                font-size: 18px;
            }
            QTabBar::tab:selected:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #FF6B1A, stop:1 #FF5B00);
                color: #FFFFFF;
                border: 2px solid #FFA726;
                border-bottom: none;
            }
            QTabBar::tab:!selected:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #3E5A52, stop:1 #2E4C44);
                color: #FF8C42;
                border: 2px solid #FF8C42;
                border-bottom: none;
            }
            QTabBar::close-button {
                background: #FF5B00;
                border-radius: 8px;
                margin: 4px;
                padding: 2px;
            }
            QTabBar::close-button:hover {
                background: #FF6B1A;
            }
            QLabel {
                color: #F1F1F1;
                font-weight: 500;
            }
            QLineEdit, QComboBox, QDateEdit, QListWidget, QTextEdit {
                background: #1B3B33;
                border: 1.5px solid #2E4C44;
                border-radius: 8px;
                padding: 8px 12px;
                color: #F1F1F1;
                font-size: 16px;
            }
            QTextEdit {
                background: #1B3B33;
                border: 1.5px solid #2E4C44;
                border-radius: 8px;
                padding: 12px;
                color: #F1F1F1;
                font-size: 16px;
                selection-background-color: #FF5B00;
                selection-color: #fff;
            }
            QTextEdit:focus {
                border: 1.5px solid #FF5B00;
                background: #1B3B33;
            }
            QComboBox, QComboBox QAbstractItemView {
                font-size: 18px;
                font-weight: 600;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {
                border: 1.5px solid #FF5B00;
                background: #1B3B33;
            }
            QComboBox {
                padding-right: 32px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 32px;
                border-left: 1.5px solid #2E4C44;
                background: #1B3B33;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0;
                height: 0;
                border-left: 8px solid transparent;
                border-right: 8px solid transparent;
                border-top: 10px solid #FF5B00;
                margin: 0 8px 0 0;
            }
            QComboBox QAbstractItemView {
                background: #1B3B33;
                border-radius: 8px;
                color: #F1F1F1;
                border: 1.5px solid #FF5B00;
                font-size: 18px;
                font-weight: 600;
                selection-background-color: #2196F3;
                selection-color: #fff;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #FF5B00;
                color: #fff;
                border-radius: 8px;
                font-weight: bold;
            }
            QDateEdit {
                qproperty-calendarPopup: true;
            }
            QCalendarWidget {
                background: #1B3B33;
                color: #F1F1F1;
                border: 1.5px solid #FF5B00;
                border-radius: 8px;
                font-size: 16px;
            }
            QCalendarWidget QToolButton {
                background: #15332B;
                color: #FF5B00;
                border: none;
                font-size: 16px;
                font-weight: bold;
                margin: 2px;
            }
            QCalendarWidget QMenu {
                background: #1B3B33;
                color: #F1F1F1;
                border: 1.5px solid #FF5B00;
            }
            QCalendarWidget QSpinBox {
                background: #1B3B33;
                color: #F1F1F1;
                border: 1.5px solid #FF5B00;
                border-radius: 6px;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: #15332B;
            }
            QCalendarWidget QAbstractItemView:enabled {
                background: #1B3B33;
                color: #F1F1F1;
                selection-background-color: #FF5B00;
                selection-color: #fff;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #43A047, stop:1 #2E7D32);
                color: #fff;
                border: none;
                border-radius: 12px;
                padding: 14px 32px;
                font-size: 18px;
                font-weight: 600;
                margin: 8px 0;
                box-shadow: 0 4px 8px rgba(67, 160, 71, 0.3);
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #66BB6A, stop:1 #43A047);
                box-shadow: 0 6px 12px rgba(67, 160, 71, 0.4);
                transform: translateY(-1px);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #2E7D32, stop:1 #1B5E20);
                box-shadow: 0 2px 4px rgba(67, 160, 71, 0.3);
                transform: translateY(1px);
            }
            QPushButton[red="true"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #E53935, stop:1 #C62828);
                color: #fff;
            }
            QPushButton[orange="true"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #FF5B00, stop:1 #E64A19);
                color: #fff;
            }
            QListWidget {
                background: #1B3B33;
                border: 1.5px solid #2E4C44;
                border-radius: 8px;
                color: #F1F1F1;
            }
            QHeaderView::section {
                background: #1B3B33;
                color: #FF5B00;
                font-weight: bold;
                border: none;
                border-bottom: 2px solid #FF5B00;
                padding: 8px 6px;
            }
            QMessageBox QLabel {
                color: #F1F1F1;
                font-size: 16px;
            }
        ''')

    def get_profile_dialog(self):
        fields = ['IP адрес', 'Порт', 'Логин', 'Пароль', 'База данных']
        values = {}
        for field in fields:
            val, ok = QInputDialog.getText(self, 'Параметры профиля', field + ':')
            if not ok or not val:
                return None
            values[field.lower().replace(' ', '') if field != 'База данных' else 'dbname'] = val
        return {
            'ip': values['ipадрес'],
            'port': values['порт'],
            'user': values['логин'],
            'password': values['пароль'],
            'dbname': values['dbname']
        }

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        # Логотип по центру сверху
        logo_label = QLabel()
        logo_pixmap = QPixmap(resource_path('new_logo.png'))
        if not logo_pixmap.isNull():
            logo_pixmap = logo_pixmap.scaledToWidth(250, QtCore.Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        main_layout.addWidget(logo_label)
        # --- Горизонтальная строка: только вкладки ---
        top_row = QHBoxLayout()
        self.tabs = QTabWidget()
        self.main_tab = MainTab(self)
        self.products_tab = ProductsTab(self)
        self.lines_tab = LinesTab(self)
        self.help_tab = HelpTab(self)
        self.update_tab = UpdateTab(self)
        self.tabs.addTab(self.main_tab, 'Главная')
        self.tabs.addTab(self.products_tab, 'Продукты')
        self.tabs.addTab(self.lines_tab, 'Линии')
        self.tabs.addTab(self.help_tab, 'Справка')
        self.tabs.addTab(self.update_tab, 'Обновление')
        self.tabs.currentChanged.connect(self.on_tab_change)
        top_row.addWidget(self.tabs)
        main_layout.addLayout(top_row)
        # --- Основное содержимое (текущая вкладка) ---
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def on_tab_change(self, idx):
        if idx == 0:
            self.main_tab.update_lines()
            self.main_tab.update_products()
        elif idx == 1:
            self.products_tab.update_list()
        elif idx == 2:
            self.lines_tab.update_list()

    def check_for_update_and_run(self):
        api_url = "https://api.github.com/repos/Andrejj12380/CheckDB/releases/latest"
        r = requests.get(api_url)
        latest = r.json()
        if "assets" not in latest or not latest["assets"]:
            QtWidgets.QMessageBox.warning(self, "Обновление", "Нет доступных обновлений на GitHub!")
            return
        exe_name = "CheckDB.exe"
        for asset in latest["assets"]:
            if asset["name"] == exe_name:
                download_url = asset["browser_download_url"]
                break
        else:
            QtWidgets.QMessageBox.warning(self, "Обновление", "Не найден файл обновления!")
            return
        # 2. Скачать новый exe во временную папку
        new_exe_path = os.path.join(os.path.dirname(sys.executable), "CheckDB_new.exe")
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(new_exe_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # 3. Запустить updater.exe и выйти
        if getattr(sys, 'frozen', False):
            # Если запущено из exe
            base_dir = os.path.dirname(sys.executable)
        else:
            # Если запущено из .py
            base_dir = os.path.abspath(os.path.dirname(__file__))

        updater_path = os.path.join(base_dir, "updater.exe")
        subprocess.Popen([updater_path, sys.executable, new_exe_path])
        sys.exit(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = DBChecker()
    win.show()
    sys.exit(app.exec_())

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
