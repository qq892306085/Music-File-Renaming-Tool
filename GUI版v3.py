import os
import sys
import re
from functools import partial
from mutagen import File
from mutagen.id3 import ID3, TIT2, TPE1
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4
from mutagen.asf import ASF
from mutagen.apev2 import APEv2
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QLineEdit,
    QPushButton, QFileDialog, QListWidget, QMessageBox, QProgressBar,
    QHBoxLayout, QCheckBox, QComboBox, QGroupBox, QTabWidget, QTextEdit,
    QGridLayout, QSizePolicy, QSplitter, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDateTime
from PyQt6.QtGui import QFont, QIcon


class Worker(QThread):
    progress_updated = pyqtSignal(int, str)
    task_completed = pyqtSignal(int, int)
    metadata_found = pyqtSignal(dict)

    def __init__(self, files, rename_pattern, dry_run, conflict_action):
        super().__init__()
        self.files = files
        self.rename_pattern = rename_pattern
        self.dry_run = dry_run
        self.conflict_action = conflict_action
        self.running = True

    def run(self):
        success_count = 0
        fail_count = 0

        for i, file_path in enumerate(self.files):
            if not self.running:
                break

            try:
                file_info = self.process_file(file_path, i + 1)
                if file_info.get('new_name'):
                    if not self.dry_run:
                        if os.path.exists(file_info['new_path']):
                            if self.conflict_action == 'skip':
                                self.progress_updated.emit(i + 1, f"跳过: 文件已存在 {file_info['new_path']}")
                                continue
                            elif self.conflict_action == 'suffix':
                                base, ext = os.path.splitext(file_info['new_path'])
                                counter = 1
                                while os.path.exists(f"{base}_{counter}{ext}"):
                                    counter += 1
                                file_info['new_path'] = f"{base}_{counter}{ext}"
                        
                        self.rename_file(file_path, file_info['new_path'])
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                self.progress_updated.emit(i + 1, f"Error: {str(e)}")
                fail_count += 1

            self.task_completed.emit(success_count, fail_count)

    def process_file(self, file_path, current):
        file_info = {
            'original_path': file_path,
            'original_name': os.path.basename(file_path),
            'extension': os.path.splitext(file_path)[1].lower(),
            'new_name': None,
            'new_path': None,
            'metadata': {}
        }

        metadata = self.extract_metadata(file_path)
        file_info['metadata'] = metadata

        if metadata['title'] or metadata['artist']:
            new_name = self.generate_new_name(metadata)
            file_info['new_name'] = new_name
            
            if new_name:
                dirname = os.path.dirname(file_path)
                new_path = os.path.join(dirname, new_name + file_info['extension'])
                
                if self.conflict_action == 'suffix':
                    counter = 1
                    while os.path.exists(new_path):
                        new_path = os.path.join(dirname, f"{new_name}_{counter}{file_info['extension']}")
                        counter += 1
                
                file_info['new_path'] = new_path

        self.progress_updated.emit(current, f"Processing: {file_info['original_name']}")
        self.metadata_found.emit(file_info)
        return file_info

    def extract_metadata(self, file_path):
        metadata = {
            'title': '',
            'artist': '',
            'album': '',
            'track': '',
            'year': ''
        }

        try:
            ext = os.path.splitext(file_path)[1].lower()
            audio = File(file_path, easy=True)

            if audio is not None:
                if 'title' in audio:
                    metadata['title'] = audio['title'][0] if isinstance(audio['title'], list) else str(audio['title'])
                if 'artist' in audio:
                    metadata['artist'] = audio['artist'][0] if isinstance(audio['artist'], list) else str(audio['artist'])
                if 'album' in audio:
                    metadata['album'] = audio['album'][0] if isinstance(audio['album'], list) else str(audio['album'])
                if 'tracknumber' in audio:
                    metadata['track'] = audio['tracknumber'][0] if isinstance(audio['tracknumber'], list) else str(audio['tracknumber'])
                if 'date' in audio:
                    metadata['year'] = audio['date'][0] if isinstance(audio['date'], list) else str(audio['date'])

                if ext == '.mp3':
                    if hasattr(audio, 'tags') and audio.tags is not None:
                        id3 = audio.tags
                        metadata['title'] = id3.get('TIT2', [metadata['title']])[0]
                        metadata['artist'] = id3.get('TPE1', [metadata['artist']])[0]
                        metadata['album'] = id3.get('TALB', [metadata['album']])[0]
                        metadata['track'] = str(id3.get('TRCK', [metadata['track']])[0]).split('/')[0]
                        metadata['year'] = id3.get('TDRC', [metadata['year']])[0]
                elif ext == '.m4a':
                    if hasattr(audio, 'tags'):
                        metadata['title'] = audio.tags.get('\xa9nam', [metadata['title']])[0]
                        metadata['artist'] = audio.tags.get('\xa9ART', [metadata['artist']])[0]
                        metadata['album'] = audio.tags.get('\xa9alb', [metadata['album']])[0]
                        metadata['track'] = str(audio.tags.get('trkn', [[metadata['track']]])[0][0])
                        metadata['year'] = audio.tags.get('\xa9day', [metadata['year']])[0]

        except Exception as e:
            print(f"Error extracting metadata from {file_path}: {e}")

        for key in metadata:
            if metadata[key] and isinstance(metadata[key], str):
                metadata[key] = metadata[key].strip()

        return metadata

    def generate_new_name(self, metadata):
        try:
            new_name = self.rename_pattern
            new_name = new_name.replace('%title%', metadata['title'] or '未知标题')
            new_name = new_name.replace('%artist%', metadata['artist'] or '未知艺术家')
            new_name = new_name.replace('%album%', metadata['album'] or '未知专辑')
            new_name = new_name.replace('%track%', metadata['track'] or '')
            new_name = new_name.replace('%year%', metadata['year'] or '')

            new_name = self.clean_filename(new_name)
            new_name = re.sub(r'[-_]{2,}', '-', new_name)
            new_name = new_name.strip('-_ ')
            
            return new_name if new_name else None
        except Exception as e:
            print(f"Error generating new name: {e}")
            return None

    def clean_filename(self, name):
        if not name:
            return ''
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = re.sub(r'[\x00-\x1f\x7f]', '_', name)
        name = name.replace('\u2028', '_').replace('\u2029', '_')
        return name.strip()

    def rename_file(self, old_path, new_path):
        try:
            os.rename(old_path, new_path)
            return True
        except Exception as e:
            print(f"Error renaming {old_path} to {new_path}: {e}")
            return False

    def stop(self):
        self.running = False


class MusicRenamer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("高级音乐文件重命名工具 v2.0")
        self.setGeometry(100, 100, 1000, 800)
        
        self.settings = {
            'last_directory': os.path.expanduser('~'),
            'rename_pattern': '%artist% - %title%',
            'dry_run': False,
            'auto_rename': False,
            'conflict_action': 'suffix',
            'default_ext': '.mp3',
            'log_level': 'info',
            'supported_extensions': ['.mp3', '.flac', '.ogg', '.m4a', '.wma', '.wav', '.aac', '.ape', '.wv']
        }
        
        self.init_ui()
        self.worker = None
        self.music_files = []
        self.file_info_cache = {}

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)

        main_tab = QWidget()
        tab_widget.addTab(main_tab, "🎵 主界面")
        self.setup_main_tab(main_tab)

        settings_tab = QWidget()
        tab_widget.addTab(settings_tab, "⚙️ 设置")
        self.setup_settings_tab(settings_tab)

        log_tab = QWidget()
        tab_widget.addTab(log_tab, "📜 日志")
        self.setup_log_tab(log_tab)

        self.statusBar().showMessage("准备就绪")
        self.apply_styles()

    def setup_main_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        dir_group = QGroupBox("📂 文件夹选择")
        dir_group.setMaximumHeight(100)
        dir_layout = QHBoxLayout(dir_group)
        dir_layout.setContentsMargins(8, 8, 8, 8)

        self.dir_path = QLineEdit(self.settings['last_directory'])
        self.dir_path.setPlaceholderText("选择包含音乐文件的文件夹...")
        dir_layout.addWidget(self.dir_path)

        self.browse_button = QPushButton("浏览")
        self.browse_button.setFixedWidth(80)
        self.browse_button.clicked.connect(self.browse_directory)
        dir_layout.addWidget(self.browse_button)

        self.scan_button = QPushButton("扫描文件")
        self.scan_button.setFixedWidth(100)
        self.scan_button.clicked.connect(self.scan_files)
        dir_layout.addWidget(self.scan_button)

        layout.addWidget(dir_group)

        file_preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        file_preview_splitter.setSizes([500, 300])

        file_list_group = QGroupBox("🎧 文件列表")
        file_list_layout = QVBoxLayout(file_list_group)
        file_list_layout.setContentsMargins(5, 5, 5, 5)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.itemSelectionChanged.connect(self.on_file_selected)
        file_list_layout.addWidget(self.file_list)

        file_buttons_layout = QHBoxLayout()
        self.preview_button = QPushButton("预览重命名")
        self.preview_button.clicked.connect(partial(self.start_processing, True))
        self.preview_button.setEnabled(False)
        file_buttons_layout.addWidget(self.preview_button)

        self.rename_button = QPushButton("执行重命名")
        self.rename_button.clicked.connect(partial(self.start_processing, False))
        self.rename_button.setEnabled(False)
        file_buttons_layout.addWidget(self.rename_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop_processing)
        self.stop_button.setEnabled(False)
        file_buttons_layout.addWidget(self.stop_button)

        file_list_layout.addLayout(file_buttons_layout)
        file_preview_splitter.addWidget(file_list_group)

        info_preview_group = QGroupBox("📄 文件信息预览")
        info_preview_layout = QVBoxLayout(info_preview_group)
        info_preview_layout.setContentsMargins(5, 5, 5, 5)

        self.info_preview = QTextEdit()
        self.info_preview.setReadOnly(True)
        info_preview_layout.addWidget(self.info_preview)

        file_preview_splitter.addWidget(info_preview_group)
        layout.addWidget(file_preview_splitter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def on_file_selected(self):
        selected_items = self.file_list.selectedItems()
        if selected_items:
            file_name = selected_items[0].text().split(" → ")[0]
            for file_path, file_info in self.file_info_cache.items():
                if file_info['original_name'] == file_name:
                    self.display_file_info(file_info)
                    break

    def setup_settings_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        pattern_group = QGroupBox("✏️ 重命名设置")
        pattern_layout = QVBoxLayout(pattern_group)

        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("命名模板:"))
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems([
            "%artist% - %title%",
            "%title% - %artist%",
            "%track% - %title%",
            "%artist% - %album% - %track% - %title%",
            "%year% - %artist% - %title%"
        ])
        self.pattern_combo.setCurrentText(self.settings['rename_pattern'])
        self.pattern_combo.setEditable(True)
        template_layout.addWidget(self.pattern_combo)
        pattern_layout.addLayout(template_layout)

        pattern_help = QLabel("可用占位符: %title%, %artist%, %album%, %track%, %year%")
        pattern_help.setStyleSheet("color: #666; font-style: italic;")
        pattern_layout.addWidget(pattern_help)

        ext_layout = QHBoxLayout()
        ext_layout.addWidget(QLabel("默认扩展名:"))
        self.default_ext_combo = QComboBox()
        self.default_ext_combo.addItems(['.mp3', '.flac', '.m4a', '.ogg', '.wav'])
        self.default_ext_combo.setCurrentText(self.settings['default_ext'])
        ext_layout.addWidget(self.default_ext_combo)
        pattern_layout.addLayout(ext_layout)

        layout.addWidget(pattern_group)

        behavior_group = QGroupBox("⚡ 行为设置")
        behavior_layout = QVBoxLayout(behavior_group)

        self.auto_rename_check = QCheckBox("扫描后自动开始重命名")
        self.auto_rename_check.setChecked(self.settings['auto_rename'])
        behavior_layout.addWidget(self.auto_rename_check)

        self.dry_run_check = QCheckBox("总是先预览而不实际重命名")
        self.dry_run_check.setChecked(self.settings['dry_run'])
        behavior_layout.addWidget(self.dry_run_check)

        conflict_group = QGroupBox("文件冲突处理")
        conflict_layout = QVBoxLayout(conflict_group)
        
        self.conflict_overwrite = QRadioButton("覆盖现有文件")
        self.conflict_skip = QRadioButton("跳过已有文件")
        self.conflict_suffix = QRadioButton("添加数字后缀")
        
        conflict_button_group = QButtonGroup()
        conflict_button_group.addButton(self.conflict_overwrite)
        conflict_button_group.addButton(self.conflict_skip)
        conflict_button_group.addButton(self.conflict_suffix)
        
        if self.settings['conflict_action'] == 'overwrite':
            self.conflict_overwrite.setChecked(True)
        elif self.settings['conflict_action'] == 'skip':
            self.conflict_skip.setChecked(True)
        else:
            self.conflict_suffix.setChecked(True)
            
        conflict_layout.addWidget(self.conflict_overwrite)
        conflict_layout.addWidget(self.conflict_skip)
        conflict_layout.addWidget(self.conflict_suffix)
        behavior_layout.addWidget(conflict_group)

        layout.addWidget(behavior_group)

        ext_group = QGroupBox("📁 文件类型设置")
        ext_layout = QGridLayout(ext_group)

        ext_layout.addWidget(QLabel("支持的文件扩展名:"), 0, 0)

        ext_check_layout = QHBoxLayout()
        self.ext_mp3 = QCheckBox(".mp3")
        self.ext_mp3.setChecked('.mp3' in self.settings['supported_extensions'])
        ext_check_layout.addWidget(self.ext_mp3)

        self.ext_flac = QCheckBox(".flac")
        self.ext_flac.setChecked('.flac' in self.settings['supported_extensions'])
        ext_check_layout.addWidget(self.ext_flac)

        self.ext_m4a = QCheckBox(".m4a")
        self.ext_m4a.setChecked('.m4a' in self.settings['supported_extensions'])
        ext_check_layout.addWidget(self.ext_m4a)

        self.ext_ogg = QCheckBox(".ogg")
        self.ext_ogg.setChecked('.ogg' in self.settings['supported_extensions'])
        ext_check_layout.addWidget(self.ext_ogg)

        self.ext_ape = QCheckBox(".ape")
        self.ext_ape.setChecked('.ape' in self.settings['supported_extensions'])
        ext_check_layout.addWidget(self.ext_ape)

        self.ext_wv = QCheckBox(".wv")
        self.ext_wv.setChecked('.wv' in self.settings['supported_extensions'])
        ext_check_layout.addWidget(self.ext_wv)

        ext_layout.addLayout(ext_check_layout, 1, 0, 1, 2)
        layout.addWidget(ext_group)

        log_group = QGroupBox("📝 日志设置")
        log_layout = QVBoxLayout(log_group)

        log_level_layout = QHBoxLayout()
        log_level_layout.addWidget(QLabel("日志级别:"))
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(['debug', 'info', 'warning', 'error'])
        self.log_level_combo.setCurrentText(self.settings['log_level'])
        log_level_layout.addWidget(self.log_level_combo)
        log_layout.addLayout(log_level_layout)

        layout.addWidget(log_group)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.reset_button = QPushButton("恢复默认")
        self.reset_button.clicked.connect(self.reset_settings)
        button_layout.addWidget(self.reset_button)
        
        self.save_settings_button = QPushButton("保存设置")
        self.save_settings_button.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_settings_button)

        layout.addLayout(button_layout)

    def reset_settings(self):
        self.pattern_combo.setCurrentText('%artist% - %title%')
        self.default_ext_combo.setCurrentText('.mp3')
        self.auto_rename_check.setChecked(False)
        self.dry_run_check.setChecked(False)
        self.conflict_suffix.setChecked(True)
        
        default_exts = ['.mp3', '.flac', '.m4a', '.ogg', '.ape', '.wv']
        for cb in [self.ext_mp3, self.ext_flac, self.ext_m4a, self.ext_ogg, self.ext_ape, self.ext_wv]:
            cb.setChecked(cb.text() in default_exts)
        
        self.log_level_combo.setCurrentText('info')
        
        QMessageBox.information(self, "设置", "已恢复默认设置!")

    def setup_log_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        log_buttons_layout = QHBoxLayout()
        self.clear_log_button = QPushButton("清除日志")
        self.clear_log_button.clicked.connect(self.clear_log)
        log_buttons_layout.addWidget(self.clear_log_button)

        self.save_log_button = QPushButton("保存日志")
        self.save_log_button.clicked.connect(self.save_log)
        log_buttons_layout.addWidget(self.save_log_button)

        layout.addLayout(log_buttons_layout)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
            QLabel {
                font-size: 14px;
                color: #333;
            }
            QLineEdit, QListWidget, QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
                font-size: 14px;
                background-color: white;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                text-align: center;
                font-size: 14px;
                margin: 4px 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                width: 10px;
            }
            QTabWidget::pane {
                border-top: 2px solid #4CAF50;
            }
            QTabBar::tab {
                background: #f0f0f0;
                border: 1px solid #ddd;
                border-bottom-color: #ddd;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                min-width: 8ex;
                padding: 4px;
            }
            QTabBar::tab:selected {
                background: #fff;
                border-bottom-color: #4CAF50;
            }
        """)
        
        font = QFont()
        font.setFamily("Segoe UI" if sys.platform == "win32" else "Arial")
        font.setPointSize(10)
        self.setFont(font)

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, 
            "选择音乐文件夹", 
            self.settings['last_directory']
        )
        if directory:
            self.dir_path.setText(directory)
            self.settings['last_directory'] = directory

    def scan_files(self):
        directory = self.dir_path.text()
        if not directory or not os.path.isdir(directory):
            self.log("error", "请选择一个有效的文件夹!")
            QMessageBox.warning(self, "错误", "请选择一个有效的文件夹!")
            return
            
        self.file_list.clear()
        self.music_files = []
        self.file_info_cache = {}
        
        extensions = []
        if self.ext_mp3.isChecked(): extensions.append('.mp3')
        if self.ext_flac.isChecked(): extensions.append('.flac')
        if self.ext_m4a.isChecked(): extensions.append('.m4a')
        if self.ext_ogg.isChecked(): extensions.append('.ogg')
        if self.ext_ape.isChecked(): extensions.append('.ape')
        if self.ext_wv.isChecked(): extensions.append('.wv')
        
        if not extensions:
            self.log("error", "请至少选择一种文件扩展名!")
            QMessageBox.warning(self, "错误", "请至少选择一种文件扩展名!")
            return
        
        self.log("info", f"开始扫描文件夹: {directory}")
        file_count = 0
        for root, _, files in os.walk(directory):
            for file in files:
                if any(file.lower().endswith(ext) for ext in extensions):
                    file_path = os.path.join(root, file)
                    self.music_files.append(file_path)
                    file_count += 1
        
        if not self.music_files:
            self.log("warning", "在所选文件夹中未找到音乐文件")
            self.preview_button.setEnabled(False)
            self.rename_button.setEnabled(False)
            QMessageBox.warning(self, "提示", "在所选文件夹中未找到音乐文件")
            return
            
        self.file_list.addItems([os.path.basename(f) for f in self.music_files])
        self.log("info", f"找到 {len(self.music_files)} 个音乐文件")
        self.preview_button.setEnabled(True)
        self.rename_button.setEnabled(True)
        
        if self.settings['auto_rename'] and not self.settings['dry_run']:
            self.start_processing(False)

    def start_processing(self, dry_run):
        if not self.music_files:
            return
            
        pattern = self.pattern_combo.currentText().strip()
        if not pattern:
            self.log("error", "请设置有效的命名模板!")
            QMessageBox.warning(self, "错误", "请设置有效的命名模板!")
            return
            
        conflict_action = 'suffix'
        if self.conflict_overwrite.isChecked():
            conflict_action = 'overwrite'
        elif self.conflict_skip.isChecked():
            conflict_action = 'skip'
            
        self.set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.music_files))
        self.progress_bar.setValue(0)
        
        self.worker = Worker(
            files=self.music_files,
            rename_pattern=pattern,
            dry_run=dry_run or self.settings['dry_run'],
            conflict_action=conflict_action
        )
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.task_completed.connect(self.task_completed)
        self.worker.metadata_found.connect(self.update_file_info)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()
        
        mode = "预览" if dry_run or self.settings['dry_run'] else "重命名"
        self.log("info", f"开始{mode}操作...")

    def stop_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("info", "操作已停止")
            self.statusBar().showMessage("操作已停止")

    def worker_finished(self):
        self.set_buttons_enabled(True)
        self.progress_bar.setVisible(False)

    def set_buttons_enabled(self, enabled):
        self.browse_button.setEnabled(enabled)
        self.scan_button.setEnabled(enabled)
        self.preview_button.setEnabled(enabled and bool(self.music_files))
        self.rename_button.setEnabled(enabled and bool(self.music_files))
        self.stop_button.setEnabled(not enabled)

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.statusBar().showMessage(message)

    def update_file_info(self, file_info):
        self.file_info_cache[file_info['original_path']] = file_info

        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.text() == file_info['original_name']:
                if file_info['new_name']:
                    item.setText(f"{file_info['original_name']} → {file_info['new_name']}{file_info['extension']}")
                break

        if file_info['original_name']:
            self.display_file_info(file_info)

    def display_file_info(self, file_info):
        info_text = f"""
        <b>原始文件名:</b> {file_info['original_name']}<br>
        <b>路径:</b> {file_info['original_path']}<br>
        <b>新文件名:</b> {file_info['new_name'] + file_info['extension'] if file_info['new_name'] else '无变化'}<br>
        <hr>
        <b>元数据:</b><br>
        <b>标题:</b> {file_info['metadata'].get('title', '无')}<br>
        <b>艺术家:</b> {file_info['metadata'].get('artist', '无')}<br>
        <b>专辑:</b> {file_info['metadata'].get('album', '无')}<br>
        <b>音轨号:</b> {file_info['metadata'].get('track', '无')}<br>
        <b>年份:</b> {file_info['metadata'].get('year', '无')}<br>
        """
        self.info_preview.setHtml(info_text)

    def task_completed(self, success, fail):
        mode = "预览" if self.settings['dry_run'] else "重命名"
        self.log("info", f"{mode}完成! 成功: {success}, 失败: {fail}")
        self.statusBar().showMessage(f"{mode}完成! 成功: {success}, 失败: {fail}")

    def save_settings(self):
        self.settings['rename_pattern'] = self.pattern_combo.currentText()
        self.settings['default_ext'] = self.default_ext_combo.currentText()
        self.settings['auto_rename'] = self.auto_rename_check.isChecked()
        self.settings['dry_run'] = self.dry_run_check.isChecked()
        
        if self.conflict_overwrite.isChecked():
            self.settings['conflict_action'] = 'overwrite'
        elif self.conflict_skip.isChecked():
            self.settings['conflict_action'] = 'skip'
        else:
            self.settings['conflict_action'] = 'suffix'
        
        self.settings['supported_extensions'] = []
        if self.ext_mp3.isChecked(): self.settings['supported_extensions'].append('.mp3')
        if self.ext_flac.isChecked(): self.settings['supported_extensions'].append('.flac')
        if self.ext_m4a.isChecked(): self.settings['supported_extensions'].append('.m4a')
        if self.ext_ogg.isChecked(): self.settings['supported_extensions'].append('.ogg')
        if self.ext_ape.isChecked(): self.settings['supported_extensions'].append('.ape')
        if self.ext_wv.isChecked(): self.settings['supported_extensions'].append('.wv')
        
        self.settings['log_level'] = self.log_level_combo.currentText()
        
        QMessageBox.information(self, "设置", "设置已保存!")
        self.log("info", "应用程序设置已更新")

    def log(self, level, message):
        if level == 'debug' and self.settings['log_level'] != 'debug':
            return
        elif level == 'info' and self.settings['log_level'] not in ['debug', 'info']:
            return
        elif level == 'warning' and self.settings['log_level'] not in ['debug', 'info', 'warning']:
            return
            
        level_color = {
            'debug': 'gray',
            'info': 'black',
            'warning': 'orange',
            'error': 'red'
        }.get(level, 'black')
        
        self.log_view.append(f"""
        <div style="color:{level_color}">
            [{QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')}] {message}
        </div>
        """)

    def clear_log(self):
        self.log_view.clear()

    def save_log(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存日志", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_view.toPlainText())
                self.log("info", f"日志已保存到: {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"保存日志失败: {str(e)}")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MusicRenamer()
    window.show()
    sys.exit(app.exec())