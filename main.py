# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

import sys
import json
import os
import csv
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QMessageBox, QComboBox, QDateEdit, QInputDialog, QTabWidget, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QFileDialog, QDialog
)
from PyQt5.QtCore import QDate, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QMovie
from PyQt5.QtSvg import QSvgWidget
import psycopg2

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

class MainTab(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        # Линии
        line_layout = QHBoxLayout()
        self.line_combo = QComboBox()
        self.line_combo.addItem('--- Новая линия ---')
        self.line_combo.addItems(self.parent.lines.keys())
        self.line_combo.currentTextChanged.connect(self.on_line_select)
        line_layout.addWidget(QLabel('Линия:'))
        line_layout.addWidget(self.line_combo)
        layout.addLayout(line_layout)
        # Продукты
        prod_layout = QHBoxLayout()
        self.product_combo = QComboBox()
        self.update_products()
        prod_layout.addWidget(QLabel('Продукт:'))
        prod_layout.addWidget(self.product_combo)
        layout.addLayout(prod_layout)
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

    def update_lines(self):
        current = self.line_combo.currentText()
        self.line_combo.blockSignals(True)
        self.line_combo.clear()
        self.line_combo.addItem('--- Новая линия ---')
        self.line_combo.addItems(self.parent.lines.keys())
        # Восстановить выбор, если он есть
        idx = self.line_combo.findText(current)
        if idx != -1:
            self.line_combo.setCurrentIndex(idx)
        self.line_combo.blockSignals(False)

    def update_products(self):
        current = self.product_combo.currentText()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        for name in self.parent.products:
            self.product_combo.addItem(name)
        # Восстановить выбор, если он есть
        idx = self.product_combo.findText(current)
        if idx != -1:
            self.product_combo.setCurrentIndex(idx)
        self.product_combo.blockSignals(False)

    def on_line_select(self, name):
        if name in self.parent.lines:
            self.parent.current_line = name
        else:
            self.parent.current_line = None

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
        self.worker = DBWorker(conn_params, gtin, date_from, date_to)
        self.worker.result_ready.connect(self.on_db_result)
        self.worker.start()

    def on_db_result(self, rows, colnames, error, status):
        self.loading.close()
        if status == 'error':
            self.result_table.setVisible(False)
            self.export_btn.setVisible(False)
            self.count_label.setVisible(False)
            self.status_label.setText('<span style="color:#E53935">ОШИБКА</span>')
            self.status_label.setVisible(True)
            QMessageBox.critical(self, 'Ошибка подключения', error)
            return
        if not rows:
            self.result_table.setVisible(False)
            self.export_btn.setVisible(False)
            self.count_label.setVisible(True)
            self.count_label.setText('Найдено строк: 0')
            self.status_label.setText('<span style="color:#E53935">НЕТ ЗАПИСЕЙ</span>')
            self.status_label.setVisible(True)
            return
        self.result_table.setVisible(True)
        self.export_btn.setVisible(True)
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
                writer = csv.writer(f)
                # Заголовки
                headers = [self.result_table.horizontalHeaderItem(i).text() for i in range(self.result_table.columnCount())]
                writer.writerow(headers)
                # Данные
                for row in range(self.result_table.rowCount()):
                    rowdata = [self.result_table.item(row, col).text() if self.result_table.item(row, col) else '' for col in range(self.result_table.columnCount())]
                    writer.writerow(rowdata)
            QMessageBox.information(self, 'Выгрузка завершена', f'Данные успешно сохранены в {path}')
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка', f'Ошибка при сохранении: {e}')

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
        self.list.currentItemChanged.connect(self.on_select)
        self.update_list()
        main_layout.addWidget(self.list, 2)
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
            self.inputs['IP адрес'].setText(line['ip'])
            self.inputs['Порт'].setText(line['port'])
            self.inputs['Логин'].setText(line['user'])
            self.inputs['Пароль'].setText(line['password'])
            self.inputs['База данных'].setText(line['dbname'])
        else:
            self.selected_name = None
            for edit in self.inputs.values():
                edit.clear()

    def add_line(self):
        for edit in self.inputs.values():
            edit.clear()
        self.list.clearSelection()
        self.selected_name = None

    def save_line(self):
        data = {k: self.inputs[k].text() for k in self.inputs}
        if not all(data.values()):
            QMessageBox.warning(self, 'Ошибка', 'Заполните все поля!')
            return
        if self.selected_name:
            name = self.selected_name
        else:
            name, ok = QInputDialog.getText(self, 'Имя линии', 'Введите имя линии:')
            if not ok or not name:
                return
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

class DBChecker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Проверка записей в БД')
        self.setGeometry(200, 200, 900, 600)
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
                background: #1B3B33;
                border-radius: 12px;
            }
            QTabBar::tab {
                background: #1B3B33;
                color: #FF5B00;
                border-radius: 10px 10px 0 0;
                padding: 14px 40px;
                min-width: 180px;
                margin-right: 2px;
                font-weight: 500;
                font-size: 18px;
            }
            QTabBar::tab:selected {
                background: #15332B;
                color: #FF5B00;
                border-bottom: 3px solid #FF5B00;
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
                background: #2196F3;
                color: #fff;
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
                background: #43A047;
                color: #fff;
                border: none;
                border-radius: 10px;
                padding: 12px 28px;
                font-size: 18px;
                font-weight: 600;
                margin: 6px 0;
            }
            QPushButton:hover {
                background: #66BB6A;
            }
            QPushButton:pressed {
                background: #2E7D32;
            }
            QPushButton[red="true"] {
                background: #E53935;
                color: #fff;
            }
            QPushButton[orange="true"] {
                background: #FF5B00;
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
        # Вкладки
        self.tabs = QTabWidget()
        self.main_tab = MainTab(self)
        self.products_tab = ProductsTab(self)
        self.lines_tab = LinesTab(self)
        self.tabs.addTab(self.main_tab, 'Главная')
        self.tabs.addTab(self.products_tab, 'Продукты')
        self.tabs.addTab(self.lines_tab, 'Линии')
        self.tabs.currentChanged.connect(self.on_tab_change)
        main_layout.addWidget(self.tabs)
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = DBChecker()
    win.show()
    sys.exit(app.exec_())

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
