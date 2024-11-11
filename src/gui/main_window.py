from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QComboBox, QProgressBar, QFileDialog, QMessageBox,
                            QTextEdit, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import sys
import os
from pathlib import Path
from src.utils.pdf_converter import PDFConverter
from src.api.ocr_service import OCRService
# 在类的开头添加
import platform

class ProcessingThread(QThread):
    """处理线程，避免GUI卡死"""
    progress_updated = pyqtSignal(int, str)  # 进度, 日志消息
    finished = pyqtSignal(bool, str)
    log_updated = pyqtSignal(str)  # 新增日志信号

    def __init__(self, pdf_path, output_path, api_key, model):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.api_key = api_key
        self.model = model
        self.pdf_converter = PDFConverter()
        self.ocr_service = OCRService()

    def run(self):
        try:
            # 创建临时目录
            temp_dir = Path(self.pdf_path).parent / "temp_images"
            
            # 转换PDF
            self.log_updated.emit("开始转换PDF...")
            image_paths = self.pdf_converter.convert_pdf(self.pdf_path, temp_dir)
            self.log_updated.emit(f"PDF转换完成，共 {len(image_paths)} 页")
            
            # OCR处理
            self.log_updated.emit("开始OCR处理...")
            
            # 设置进度回调
            def progress_callback(current, total, message):
                progress = int((current / total) * 100)
                self.progress_updated.emit(progress, message)
                self.log_updated.emit(message)
            
            results = self.ocr_service.process_images(
                image_paths,
                self.api_key,
                self.model,
                progress_callback=progress_callback  # 传入进度回调函数
            )
            
            # 保存结果
            self.log_updated.emit("正在保存结果...")
            self.ocr_service.save_results(results, self.output_path)
            
            # 清理临时文件
            self.log_updated.emit("清理临时文件...")
            try:
                self.pdf_converter.cleanup_temp_files(image_paths)
                if temp_dir.exists():
                    temp_dir.rmdir()
            except Exception as e:
                self.log_updated.emit(f"清理临时文件时出现警告: {str(e)}")
            
            self.finished.emit(True, "处理完成")
            
        except Exception as e:
            self.log_updated.emit(f"错误: {str(e)}")
            self.finished.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF OCR 工具")
        # Windows下的缩放优化
        if platform.system() == 'Windows':
            self.setMinimumWidth(900)  # Windows下略微增加宽度
            self.setMinimumHeight(650)
        else:
            self.setMinimumWidth(800)
            self.setMinimumHeight(600)
        self._setup_ui()

    def _setup_ui(self):
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 创建分割器，上部分是控制面板，下部分是日志
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)
        
        # 上部分 - 控制面板
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(10)
        
        # PDF文件选择
        pdf_layout = QHBoxLayout()
        self.pdf_path_edit = QLineEdit()
        self.pdf_path_edit.setPlaceholderText("选择PDF文件...")
        pdf_button = QPushButton("浏览")
        pdf_button.clicked.connect(self._select_pdf)
        pdf_layout.addWidget(QLabel("PDF文件:"))
        pdf_layout.addWidget(self.pdf_path_edit)
        pdf_layout.addWidget(pdf_button)
        control_layout.addLayout(pdf_layout)

        # API Key输入
        api_layout = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("输入API Key...")
        api_layout.addWidget(QLabel("API Key:"))
        api_layout.addWidget(self.api_key_edit)
        control_layout.addLayout(api_layout)

        # 模型选择
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.addItems(["qwen-vl-plus-0809", "qwen-vl-max-0809"])
        model_layout.addWidget(QLabel("选择模型:"))
        model_layout.addWidget(self.model_combo)
        control_layout.addLayout(model_layout)

        # 输出路径选择
        output_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("选择输出位置...")
        output_button = QPushButton("浏览")
        output_button.clicked.connect(self._select_output)
        output_layout.addWidget(QLabel("输出位置:"))
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(output_button)
        control_layout.addLayout(output_layout)

        # 进度条和状态
        self.progress_bar = QProgressBar()
        control_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.status_label)

        # 开始按钮
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self._start_processing)
        control_layout.addWidget(self.start_button)
        
        # 下部分 - 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        
        # 添加到分割器
        splitter.addWidget(control_panel)
        splitter.addWidget(self.log_text)
        
        # 设置分割器的初始大小
        splitter.setSizes([300, 300])

    def _append_log(self, message):
        self.log_text.append(message)
        # 滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def _select_pdf(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择PDF文件",
            "",
            "PDF文件 (*.pdf)"
        )
        if filename:
            self.pdf_path_edit.setText(filename)
            # 自动设置输出路径
            output_path = str(Path(filename).with_suffix('.md'))
            self.output_path_edit.setText(output_path)

    def _select_output(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "选择保存位置",
            "",
            "Markdown文件 (*.md)"
        )
        if filename:
            self.output_path_edit.setText(filename)

    def _validate_inputs(self):
        if not self.pdf_path_edit.text():
            QMessageBox.warning(self, "错误", "请选择PDF文件")
            return False
        if not self.api_key_edit.text():
            QMessageBox.warning(self, "错误", "请输入API Key")
            return False
        if not self.output_path_edit.text():
            QMessageBox.warning(self, "错误", "请选择输出位置")
            return False
        return True

    def _start_processing(self):
        if not self._validate_inputs():
            return

        # 清空日志
        self.log_text.clear()
        
        # 禁用开始按钮
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)

        # 创建并启动处理线程
        self.processing_thread = ProcessingThread(
            self.pdf_path_edit.text(),
            self.output_path_edit.text(),
            self.api_key_edit.text(),
            self.model_combo.currentText()
        )
        self.processing_thread.progress_updated.connect(self._update_progress)
        self.processing_thread.finished.connect(self._process_finished)
        self.processing_thread.log_updated.connect(self._append_log)
        self.processing_thread.start()

    def _update_progress(self, value, status):
        self.progress_bar.setValue(value)
        self.status_label.setText(status)

    def _process_finished(self, success, message):
        self.start_button.setEnabled(True)
        self.progress_bar.setValue(100 if success else 0)
        
        if success:
            if os.path.exists(self.output_path_edit.text()):
                QMessageBox.information(self, "完成", "文件处理完成！")
                self._append_log("处理完成！")
            else:
                QMessageBox.warning(self, "警告", "文件可能未完全处理，请检查输出文件。")
                self._append_log("警告：文件可能未完全处理")
        else:
            if "Directory not empty" in message and os.path.exists(self.output_path_edit.text()):
                QMessageBox.information(self, "完成", "文件处理完成！\n(清理临时文件时出现警告，但不影响结果)")
                self._append_log("处理完成（清理临时文件时出现警告）")
            else:
                QMessageBox.critical(self, "错误", f"处理失败：{message}")
                self._append_log(f"处理失败：{message}")
        
        self.status_label.setText("就绪" if success else "处理失败")