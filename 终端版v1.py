#!/usr/bin/env python3
import os
import sys
import re
from mutagen import File
from mutagen.id3 import ID3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4
from mutagen.asf import ASF
from mutagen.apev2 import APEv2
from pathlib import Path
import logging
from typing import Dict, List, Optional, Tuple
import questionary
from questionary import Style
from colorama import init, Fore, Back, Style as ColoramaStyle
from tabulate import tabulate

# 初始化颜色支持
init(autoreset=True)

# 自定义样式
custom_style = Style([
    ('qmark', 'fg:#34eb9b bold'),       # 问题标记颜色
    ('question', 'bold'),              # 问题文本
    ('answer', 'fg:#34ebd9 bold'),     # 答案文本
    ('pointer', 'fg:#eb4034 bold'),    # 指针颜色
    ('selected', 'fg:#cc5454'),        # 选中项颜色
    ('separator', 'fg:#cc5454'),       # 分隔线颜色
])

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('music_renamer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class InteractiveMusicRenamer:
    def __init__(self):
        self.supported_extensions = {
            '.mp3', '.flac', '.ogg', '.m4a', '.wma', '.wav', '.aac', '.ape', '.wv'
        }
        self.default_pattern = "%artist% - %title%"
        self.dry_run = False
        self.max_filename_length = 255
        self.selected_files = []
        self.current_directory = ""
        
        # 颜色定义
        self.COLOR_PROMPT = Fore.CYAN
        self.COLOR_INFO = Fore.GREEN
        self.COLOR_WARNING = Fore.YELLOW
        self.COLOR_ERROR = Fore.RED
        self.COLOR_HEADER = Fore.MAGENTA
        self.COLOR_RESET = ColoramaStyle.RESET_ALL

    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_header(self, title):
        """打印标题"""
        self.clear_screen()
        print(f"\n{self.COLOR_HEADER}=== {title} ==={self.COLOR_RESET}\n")

    def print_success(self, message):
        """打印成功消息"""
        print(f"{self.COLOR_INFO}[✓] {message}{self.COLOR_RESET}")

    def print_warning(self, message):
        """打印警告消息"""
        print(f"{self.COLOR_WARNING}[!] {message}{self.COLOR_RESET}")

    def print_error(self, message):
        """打印错误消息"""
        print(f"{self.COLOR_ERROR}[✗] {message}{self.COLOR_RESET}")

    def extract_metadata(self, file_path: str) -> Dict[str, str]:
        """提取音乐文件的元数据"""
        metadata = {
            'title': '',
            'artist': '',
            'album': '',
            'track': '',
            'year': '',
            'genre': ''
        }

        try:
            ext = os.path.splitext(file_path)[1].lower()
            audio = File(file_path, easy=True)

            if audio is not None:
                # 通用元数据提取
                if 'title' in audio:
                    metadata['title'] = self._get_first_value(audio['title'])
                if 'artist' in audio:
                    metadata['artist'] = self._get_first_value(audio['artist'])
                if 'album' in audio:
                    metadata['album'] = self._get_first_value(audio['album'])
                if 'tracknumber' in audio:
                    metadata['track'] = self._get_first_value(audio['tracknumber'])
                if 'date' in audio:
                    metadata['year'] = self._get_first_value(audio['date'])
                if 'genre' in audio:
                    metadata['genre'] = self._get_first_value(audio['genre'])

                # 格式特定元数据提取
                if ext == '.mp3':
                    if hasattr(audio, 'tags') and audio.tags is not None:
                        id3 = audio.tags
                        metadata['title'] = self._get_first_value(id3.get('TIT2', [metadata['title']]))
                        metadata['artist'] = self._get_first_value(id3.get('TPE1', [metadata['artist']]))
                        metadata['album'] = self._get_first_value(id3.get('TALB', [metadata['album']]))
                        metadata['track'] = str(self._get_first_value(id3.get('TRCK', [metadata['track']]))).split('/')[0]
                        metadata['year'] = self._get_first_value(id3.get('TDRC', [metadata['year']]))
                        metadata['genre'] = self._get_first_value(id3.get('TCON', [metadata['genre']]))
                elif ext == '.m4a':
                    if hasattr(audio, 'tags'):
                        metadata['title'] = self._get_first_value(audio.tags.get('\xa9nam', [metadata['title']]))
                        metadata['artist'] = self._get_first_value(audio.tags.get('\xa9ART', [metadata['artist']]))
                        metadata['album'] = self._get_first_value(audio.tags.get('\xa9alb', [metadata['album']]))
                        metadata['track'] = str(self._get_first_value(audio.tags.get('trkn', [[metadata['track']]]))[0])
                        metadata['year'] = self._get_first_value(audio.tags.get('\xa9day', [metadata['year']]))
                        metadata['genre'] = self._get_first_value(audio.tags.get('\xa9gen', [metadata['genre']]))

        except Exception as e:
            logger.error(f"读取 {file_path} 元数据时出错: {e}")
            self.print_error(f"读取 {os.path.basename(file_path)} 元数据时出错: {e}")

        # 清理元数据
        for key in metadata:
            if metadata[key] and isinstance(metadata[key], str):
                metadata[key] = metadata[key].strip()

        return metadata

    def _get_first_value(self, value) -> str:
        """从可能的多值中获取第一个值"""
        if isinstance(value, list):
            return str(value[0]) if value else ''
        return str(value) if value is not None else ''

    def generate_new_name(self, metadata: Dict[str, str], pattern: str) -> Optional[str]:
        """根据模板生成新文件名"""
        try:
            # 替换模板中的占位符
            new_name = pattern
            new_name = new_name.replace('%title%', metadata['title'] or '未知标题')
            new_name = new_name.replace('%artist%', metadata['artist'] or '未知艺术家')
            new_name = new_name.replace('%album%', metadata['album'] or '未知专辑')
            new_name = new_name.replace('%track%', metadata['track'] or '')
            new_name = new_name.replace('%year%', metadata['year'] or '')
            new_name = new_name.replace('%genre%', metadata['genre'] or '')

            # 清理文件名
            new_name = self.clean_filename(new_name)
            
            # 移除可能的多余分隔符
            new_name = re.sub(r'[-_]{2,}', '-', new_name)
            new_name = new_name.strip('-_ ')
            
            # 限制文件名长度
            if len(new_name) > self.max_filename_length:
                new_name = new_name[:self.max_filename_length]
                self.print_warning(f"文件名过长，已截断为: {new_name}")
            
            return new_name if new_name else None
        except Exception as e:
            logger.error(f"生成新名称时出错: {e}")
            self.print_error(f"生成新名称时出错: {e}")
            return None

    def clean_filename(self, name: str) -> str:
        """清理文件名中的非法字符"""
        if not name:
            return ''
        # 替换非法字符
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 替换控制字符
        name = re.sub(r'[\x00-\x1f\x7f]', '_', name)
        # 替换特殊空格
        name = name.replace('\u2028', '_').replace('\u2029', '_')
        # 移除首尾空格
        return name.strip()

    def rename_file(self, file_path: str, new_name: str, dry_run: bool = False) -> bool:
        """重命名文件"""
        try:
            dirname = os.path.dirname(file_path)
            ext = os.path.splitext(file_path)[1]
            new_path = os.path.join(dirname, new_name + ext)
            
            # 避免文件名冲突
            counter = 1
            while os.path.exists(new_path):
                new_path = os.path.join(dirname, f"{new_name}_{counter}{ext}")
                counter += 1
            
            if dry_run:
                self.print_info(f"[预览] 将重命名: {os.path.basename(file_path)} -> {os.path.basename(new_path)}")
                return True
            
            os.rename(file_path, new_path)
            self.print_success(f"已重命名: {os.path.basename(file_path)} -> {os.path.basename(new_path)}")
            return True
        except Exception as e:
            logger.error(f"重命名 {file_path} 时出错: {e}")
            self.print_error(f"重命名 {os.path.basename(file_path)} 时出错: {e}")
            return False

    def scan_directory(self, directory: str, extensions: Optional[set] = None) -> List[str]:
        """扫描目录中的音乐文件"""
        if not extensions:
            extensions = self.supported_extensions
        
        music_files = []
        
        for root, _, files in os.walk(directory):
            for file in files:
                if any(file.lower().endswith(ext) for ext in extensions):
                    file_path = os.path.join(root, file)
                    music_files.append(file_path)
        
        return music_files

    def process_files(
        self,
        files: List[str],
        pattern: str,
        dry_run: bool = False
    ) -> Tuple[int, int]:
        """处理音乐文件"""
        success_count = 0
        fail_count = 0
        total_files = len(files)
        
        self.print_info(f"开始处理 {total_files} 个文件...")
        
        for i, file_path in enumerate(files, 1):
            try:
                self.print_info(f"正在处理文件 {i}/{total_files}: {os.path.basename(file_path)}")
                
                metadata = self.extract_metadata(file_path)
                new_name = self.generate_new_name(metadata, pattern)
                
                if not new_name:
                    self.print_warning(f"无法为文件生成新名称: {os.path.basename(file_path)}")
                    fail_count += 1
                    continue
                
                if self.rename_file(file_path, new_name, dry_run):
                    success_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                logger.error(f"处理文件 {file_path} 时出错: {e}")
                self.print_error(f"处理文件 {os.path.basename(file_path)} 时出错: {e}")
                fail_count += 1
        
        return success_count, fail_count

    def print_info(self, message):
        """打印信息消息"""
        print(f"{self.COLOR_PROMPT}[*] {message}{self.COLOR_RESET}")

    def show_metadata_table(self, files: List[str]):
        """显示文件元数据表格"""
        table_data = []
        for file_path in files:
            metadata = self.extract_metadata(file_path)
            table_data.append([
                os.path.basename(file_path),
                metadata['title'],
                metadata['artist'],
                metadata['album'],
                metadata['track'],
                metadata['year'],
                metadata['genre']
            ])
        
        headers = [
            f"{self.COLOR_HEADER}文件名{self.COLOR_RESET}",
            f"{self.COLOR_HEADER}标题{self.COLOR_RESET}",
            f"{self.COLOR_HEADER}艺术家{self.COLOR_RESET}",
            f"{self.COLOR_HEADER}专辑{self.COLOR_RESET}",
            f"{self.COLOR_HEADER}音轨{self.COLOR_RESET}",
            f"{self.COLOR_HEADER}年份{self.COLOR_RESET}",
            f"{self.COLOR_HEADER}流派{self.COLOR_RESET}"
        ]
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))

    async def select_directory(self):
        """选择目录"""
        while True:
            self.print_header("选择音乐文件夹")
            default_dir = self.current_directory or os.path.expanduser("~")
            dir_path = await questionary.text(
                "请输入音乐文件夹路径:",
                default=default_dir,
                style=custom_style
            ).ask_async()
            
            if not dir_path:
                continue
                
            if not os.path.isdir(dir_path):
                self.print_error("目录不存在，请重新输入!")
                continue
                
            self.current_directory = dir_path
            return dir_path

    async def select_extensions(self):
        """选择文件扩展名"""
        self.print_header("选择文件类型")
        choices = [
            {"name": "MP3 (.mp3)", "checked": True},
            {"name": "FLAC (.flac)", "checked": True},
            {"name": "OGG (.ogg)", "checked": True},
            {"name": "M4A (.m4a)", "checked": True},
            {"name": "APE (.ape)", "checked": False},
            {"name": "WV (.wv)", "checked": False},
            {"name": "WMA (.wma)", "checked": False},
            {"name": "AAC (.aac)", "checked": False},
            {"name": "WAV (.wav)", "checked": False}
        ]
        
        selected = await questionary.checkbox(
            "选择要处理的文件类型:",
            choices=choices,
            style=custom_style
        ).ask_async()
        
        extensions = []
        for item in selected:
            ext = re.search(r'\(\.(\w+)\)', item).group(1)
            extensions.append(f".{ext.lower()}")
        
        return extensions

    async def select_pattern(self):
        """选择命名模式"""
        self.print_header("选择命名模式")
        patterns = [
            "%artist% - %title%",
            "%title% - %artist%",
            "%track% - %title%",
            "%artist% - %album% - %track% - %title%",
            "%year% - %artist% - %title%",
            "自定义..."
        ]
        
        pattern = await questionary.select(
            "选择命名模式:",
            choices=patterns,
            style=custom_style
        ).ask_async()
        
        if pattern == "自定义...":
            pattern = await questionary.text(
                "输入自定义命名模式 (可用占位符: %title%, %artist%, %album%, %track%, %year%, %genre%):",
                default=self.default_pattern,
                style=custom_style
            ).ask_async()
        
        return pattern.strip()

    async def confirm_dry_run(self):
        """确认是否使用预览模式"""
        self.print_header("预览模式")
        return await questionary.confirm(
            "启用预览模式(只显示将要执行的操作而不实际重命名文件)?",
            default=True,
            style=custom_style
        ).ask_async()

    async def select_files(self, files: List[str]):
        """选择要处理的文件"""
        self.print_header("选择文件")
        choices = [
            {"name": f"{os.path.basename(f)}", "checked": True}
            for f in files
        ]
        
        selected = await questionary.checkbox(
            "选择要处理的文件:",
            choices=choices,
            style=custom_style
        ).ask_async()
        
        return [f for f in files if os.path.basename(f) in selected]

    async def show_main_menu(self):
        """显示主菜单"""
        while True:
            self.print_header("音乐文件重命名工具")
            
            if self.current_directory:
                print(f"{self.COLOR_INFO}当前目录: {self.current_directory}{self.COLOR_RESET}")
            
            if self.selected_files:
                print(f"{self.COLOR_INFO}已选择 {len(self.selected_files)} 个文件{self.COLOR_RESET}")
            
            choices = [
                "选择文件夹",
                "选择文件类型",
                "扫描音乐文件",
                "查看文件元数据",
                "设置命名模式",
                "设置预览模式",
                "执行重命名",
                "退出"
            ]
            
            action = await questionary.select(
                "请选择操作:",
                choices=choices,
                style=custom_style
            ).ask_async()
            
            if action == "选择文件夹":
                self.current_directory = await self.select_directory()
                self.selected_files = []
                
            elif action == "选择文件类型":
                extensions = await self.select_extensions()
                self.supported_extensions = set(extensions)
                self.selected_files = []
                
            elif action == "扫描音乐文件":
                if not self.current_directory:
                    self.print_error("请先选择文件夹!")
                    continue
                    
                self.selected_files = self.scan_directory(self.current_directory)
                if not self.selected_files:
                    self.print_error("在指定目录中未找到匹配的音乐文件")
                else:
                    self.print_success(f"找到 {len(self.selected_files)} 个音乐文件")
                    
            elif action == "查看文件元数据":
                if not self.selected_files:
                    self.print_error("没有可显示的文件，请先扫描文件!")
                    continue
                    
                self.show_metadata_table(self.selected_files)
                input("\n按Enter键继续...")
                
            elif action == "设置命名模式":
                self.default_pattern = await self.select_pattern()
                self.print_success(f"命名模式已设置为: {self.default_pattern}")
                
            elif action == "设置预览模式":
                self.dry_run = await self.confirm_dry_run()
                mode = "启用" if self.dry_run else "禁用"
                self.print_success(f"{mode}预览模式")
                
            elif action == "执行重命名":
                if not self.selected_files:
                    self.print_error("没有可处理的文件，请先扫描文件!")
                    continue
                    
                # 确认选择要处理的文件
                files_to_process = await self.select_files(self.selected_files)
                if not files_to_process:
                    continue
                    
                success, fail = self.process_files(
                    files_to_process,
                    self.default_pattern,
                    self.dry_run
                )
                
                self.print_info(f"处理完成! 成功: {success}, 失败: {fail}")
                input("\n按Enter键继续...")
                
            elif action == "退出":
                self.print_info("感谢使用音乐文件重命名工具，再见!")
                sys.exit(0)

async def main():
    renamer = InteractiveMusicRenamer()
    await renamer.show_main_menu()

if __name__ == "__main__":
    import asyncio
    try:
        # 检查必要依赖
        try:
            import questionary
            from colorama import init
            from tabulate import tabulate
        except ImportError as e:
            print(f"错误: 缺少必要依赖 {e}")
            print("请使用以下命令安装依赖:")
            print("pip install questionary colorama tabulate mutagen")
            sys.exit(1)
            
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n操作已取消")
        sys.exit(0)
