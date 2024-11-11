from pdf2image import convert_from_path
from PIL import Image
import os
from typing import List, Generator, Tuple
import logging
from pathlib import Path
import sys

class PDFConverter:
    def __init__(self):
        self.dpi = 300
        self.logger = logging.getLogger('PDFConverter')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # 设置poppler路径
        if getattr(sys, 'frozen', False):
            # 如果是打包后的可执行文件
            application_path = os.path.dirname(sys.executable)
        else:
            # 如果是开发环境
            application_path = os.path.dirname(os.path.abspath(__file__))
        
        # 回退到项目根目录
        root_path = os.path.dirname(os.path.dirname(application_path))
        self.poppler_path = os.path.join(root_path, 'poppler', 'bin')
        
        self.logger.info(f"Poppler path: {self.poppler_path}")
        if not os.path.exists(self.poppler_path):
            self.logger.warning(f"Poppler directory not found at {self.poppler_path}")

    def convert_pdf(self, pdf_path: str, output_dir: str) -> List[str]:
        """
        转换PDF文件为JPEG图片，返回所有生成的图片路径列表
        """
        image_paths = []
        try:
            # 确保输出目录存在
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # 获取PDF文件名（不含扩展名）
            pdf_name = Path(pdf_path).stem

            self.logger.info(f"开始转换PDF文件: {pdf_path}")

            # Windows下使用poppler_path参数
            conversion_kwargs = {
                'pdf_path': pdf_path,
                'dpi': self.dpi,
                'fmt': 'jpeg',
                'thread_count': 2
            }
            
            if os.name == 'nt':  # Windows系统
                conversion_kwargs['poppler_path'] = self.poppler_path

            try:
                pages = convert_from_path(**conversion_kwargs)
            except Exception as e:
                self.logger.error(f"PDF转换失败: {str(e)}")
                self.logger.error(f"当前Poppler路径: {self.poppler_path}")
                self.logger.error("请确保正确安装了Poppler并设置了正确的路径")
                raise

            # 处理每一页
            for i, page in enumerate(pages, start=1):
                output_file = output_path / f"{pdf_name}_page_{i:03d}.jpg"
                page.save(str(output_file), 'JPEG', quality=95)
                image_paths.append(str(output_file))
                self.logger.info(f"已转换第 {i} 页: {output_file}")

            return image_paths

        except Exception as e:
            self.logger.error(f"PDF转换过程中出现错误: {str(e)}")
            raise

    def cleanup_temp_files(self, image_paths: List[str]) -> None:
        """
        清理临时图片文件
        """
        try:
            for image_path in image_paths:
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    self.logger.warning(f"删除临时文件 {image_path} 失败: {str(e)}")
        except Exception as e:
            self.logger.warning(f"清理临时文件时出现警告: {str(e)}")