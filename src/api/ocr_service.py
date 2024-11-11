from dashscope import MultiModalConversation
from typing import List, Dict
import logging
from pathlib import Path
import time
import concurrent.futures
from threading import Lock

class OCRService:
    def __init__(self):
        self.logger = logging.getLogger('OCRService')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self.prompt = """请将这张图片转化为文本。我的目的是使其可以被语言模型直接读取。要求：
1. 公式使用LaTeX给出；
2. 表格、标题等结构使用Markdown给出；
3. 图片使用Markdown占位符给出；
4. 除了OCR结果之外，不要输出任何其他字符；
5. 用`$`和`$$`而不是`\[`和`\]`来给出公式；
6. 不要将页眉和页脚的内容包含在内。"""
        
        # 添加线程锁用于日志同步
        self.log_lock = Lock()
        # 添加进度追踪
        self.total_images = 0
        self.processed_images = 0
        self.progress_lock = Lock()

    def _update_progress(self) -> None:
        """更新处理进度"""
        with self.progress_lock:
            self.processed_images += 1
            progress = (self.processed_images / self.total_images) * 100
            return progress

    def process_images(self, image_paths: List[str], api_key: str, model: str = "qwen-vl-plus-0809", 
                    max_workers: int = 3, progress_callback=None) -> List[str]:
        """
        并行处理图片列表，返回OCR结果列表
        max_workers: 最大并行处理线程数
        progress_callback: 进度回调函数，接收三个参数：当前处理数，总数，消息
        """
        self.total_images = len(image_paths)
        self.processed_images = 0
        results = [None] * len(image_paths)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_index = {
                    executor.submit(
                        self._process_single_image_with_retry, 
                        image_path, 
                        api_key, 
                        model,
                        index
                    ): index 
                    for index, image_path in enumerate(image_paths)
                }

                for future in concurrent.futures.as_completed(future_to_index):
                    index = future_to_index[future]
                    try:
                        result = future.result()
                        results[index] = result
                        self.processed_images += 1
                        
                        if progress_callback:
                            progress_callback(
                                self.processed_images,
                                self.total_images,
                                f"正在处理第 {self.processed_images}/{self.total_images} 页"
                            )
                            
                    except Exception as e:
                        with self.log_lock:
                            self.logger.error(f"处理图片 {image_paths[index]} 失败: {str(e)}")
                        results[index] = f"[OCR失败: {str(e)}]"

            results = [r for r in results if r and not r.startswith("[OCR失败")]
            return results

        finally:
            # 清理临时文件的代码保持不变...
            try:
                temp_dir = Path(image_paths[0]).parent
                if temp_dir.exists():
                    for item in temp_dir.iterdir():
                        try:
                            if item.is_file():
                                item.unlink()
                        except Exception as e:
                            self.logger.warning(f"删除临时文件 {item} 时出现警告: {str(e)}")
                    try:
                        temp_dir.rmdir()
                    except Exception as e:
                        self.logger.warning(f"删除临时目录时出现警告: {str(e)}")
            except Exception as e:
                self.logger.warning(f"清理临时文件时出现警告: {str(e)}")

    def _process_single_image_with_retry(self, image_path: str, api_key: str, model: str, index: int, max_retries: int = 3) -> str:
        """
        处理单张图片，包含重试机制
        """
        for attempt in range(max_retries):
            try:
                with self.log_lock:
                    self.logger.info(f"处理图片 {index + 1}: {image_path} (尝试 {attempt + 1}/{max_retries})")
                
                result = self._process_single_image(image_path, api_key, model)
                return result
                
            except Exception as e:
                if attempt < max_retries - 1:
                    with self.log_lock:
                        self.logger.warning(f"处理失败，准备重试: {str(e)}")
                    time.sleep(2)  # 重试前等待
                else:
                    raise

    def _process_single_image(self, image_path: str, api_key: str, model: str) -> str:
        """
        处理单张图片
        """
        try:
            file_path = f"file://{image_path}"
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"image": file_path},
                        {"text": self.prompt}
                    ]
                }
            ]

            response = MultiModalConversation.call(
                model=model,
                messages=messages,
                api_key=api_key
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            return item['text']
                    if content:
                        return str(content[0])
                elif isinstance(content, dict):
                    return content.get('text', str(content))
                else:
                    return str(content)
            else:
                raise Exception(f"API调用失败: {response.code} - {response.message}")

        except Exception as e:
            with self.log_lock:
                self.logger.error(f"处理图片时出现错误: {str(e)}")
            raise

    def save_results(self, results: List[str], output_path: str):
        """
        将OCR结果保存为Markdown文件
        """
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            combined_text = "\n\n".join(results)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(combined_text)
                
            self.logger.info(f"结果已保存到: {output_file}")
            
        except Exception as e:
            self.logger.error(f"保存结果时出现错误: {str(e)}")
            raise