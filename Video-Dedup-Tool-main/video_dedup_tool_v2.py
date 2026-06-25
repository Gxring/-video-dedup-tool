"""
搬运视频工具 - 美化版
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import random
import string
from pathlib import Path
import threading
import re
import hashlib
import json
import time
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum


# ============ 配置 ============

class Preset(Enum):
    QUICK = "快速"
    STANDARD = "标准"
    AGGRESSIVE = "强力"
    CUSTOM = "自定义"


@dataclass
class ProcessingConfig:
    mirror: bool = False
    rgb_shift: bool = False
    time_jump: bool = True
    md5_change: bool = True
    mask_invert: bool = False
    mask_invert_value: float = 0.03
    frame_sampling: bool = False
    frame_sampling_interval: int = 5
    frame_sampling_random: bool = True
    noise_add: bool = False
    noise_level: int = 10
    color_adjust: bool = False
    brightness: float = 1.0
    contrast: float = 1.0
    speed_change: bool = False
    speed_factor: float = 1.02

    @classmethod
    def from_preset(cls, preset: Preset) -> 'ProcessingConfig':
        presets = {
            Preset.QUICK: cls(
                md5_change=True
            ),
            Preset.STANDARD: cls(
                md5_change=True,
                time_jump=True,
                noise_add=True,
                noise_level=5
            ),
            Preset.AGGRESSIVE: cls(
                md5_change=True,
                time_jump=True,
                rgb_shift=True,
                noise_add=True,
                noise_level=12,
                color_adjust=True,
                brightness=1.02,
                contrast=1.02
            ),
            Preset.CUSTOM: cls(),
        }
        return presets.get(preset, cls())


@dataclass
class AppConfig:
    ffmpeg_path: str = "D:/ffmpeg/bin/ffmpeg.exe"
    ffprobe_path: str = "D:/ffmpeg/bin/ffprobe.exe"
    last_input_dir: str = ""
    last_output_dir: str = ""

    def save(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, indent=2)

    @classmethod
    def load(cls, path: str) -> 'AppConfig':
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return cls(**json.load(f))
            except Exception:
                pass
        return cls()


# ============ 颜色主题 ============

COLORS = {
    'bg': '#0d1117',
    'bg_card': '#161b22',
    'bg_hover': '#1c2128',
    'bg_input': '#0d1117',
    'border': '#30363d',
    'border_focus': '#58a6ff',
    'text': '#e6edf3',
    'text_dim': '#8b949e',
    'accent': '#238636',
    'accent_hover': '#2ea043',
    'danger': '#da3633',
    'danger_hover': '#f85149',
    'blue': '#58a6ff',
    'purple': '#bc8cff',
    'orange': '#d29922',
    'pink': '#f778ba',
    'cyan': '#39d2c0',
}


# ============ FFmpeg封装 ============

class FFmpegWrapper:
    def __init__(self, ffmpeg_path: str, ffprobe_path: str):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def get_duration(self, video_path: str) -> float:
        try:
            cmd = [self.ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
                   '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            return float(result.stdout.strip()) if result.returncode == 0 else 0
        except Exception:
            return 0

    def get_resolution(self, video_path: str) -> tuple:
        try:
            cmd = [self.ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
                   '-show_entries', 'stream=width,height', '-of', 'csv=p=0', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(',')
                return (int(parts[0]), int(parts[1]))
        except Exception:
            pass
        return (0, 0)

    def build_command(self, input_path: str, output_path: str, config: ProcessingConfig) -> list:
        cmd = [self.ffmpeg_path, '-y', '-i', input_path]
        filters = []

        if config.mirror:
            filters.append("hflip")
        if config.rgb_shift:
            filters.append("rgbashift=rh=2:gh=-1:bh=1:rv=1:gv=-2:bv=2")
        if config.time_jump:
            filters.append("minterpolate=fps=30:mi_mode=blend:mc_mode=aobmc:me_mode=bidir:mb_size=16:search_param=32")
        if config.mask_invert:
            filters.append(f"colorchannelmixer=aa={config.mask_invert_value}")
        if config.frame_sampling:
            interval = config.frame_sampling_interval
            if config.frame_sampling_random:
                filters.append(f"select='not(mod(n,{interval}+floor(random(0)*6)))'")
            else:
                filters.append(f"select='not(mod(n,{interval}))'")
        if config.noise_add:
            filters.append(f"noise=alls={config.noise_level}:allf=t")
        if config.color_adjust:
            filters.append(f"eq=brightness={config.brightness - 1}:contrast={config.contrast}")
        if config.speed_change:
            filters.append(f"setpts={1/config.speed_factor}*PTS")

        if filters:
            cmd.extend(['-vf', ','.join(filters)])

        if config.md5_change or filters:
            rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            cmd.extend([
                '-metadata', f"title=Processed_{rand_str}",
                '-metadata', f"comment=Video processed at {datetime.now().isoformat()}",
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
            ])
        else:
            cmd.extend(['-c', 'copy'])

        cmd.append(output_path)
        return cmd

    def execute_with_progress(self, cmd: list, input_path: str,
                              progress_cb=None, log_cb=None) -> bool:
        duration = self.get_duration(input_path)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, encoding='utf-8', bufsize=1)

        while True:
            output = process.stderr.readline() if process.stderr else ''
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                if log_cb:
                    log_cb(line)
                if progress_cb and duration > 0:
                    time_match = re.search(r"time=([0-9:.]+)", line)
                    if time_match:
                        current = self._parse_time(time_match.group(1))
                        if current >= 0:
                            progress_cb(min(100, int((current / duration) * 100)))
        return process.returncode == 0

    @staticmethod
    def _parse_time(time_str: str) -> float:
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except Exception:
            pass
        return -1


# ============ 现代化UI组件 ============

class RoundedFrame(tk.Canvas):
    """圆角卡片"""
    def __init__(self, parent, bg=COLORS['bg_card'], radius=12, **kwargs):
        super().__init__(parent, bg=parent['bg'], highlightthickness=0, **kwargs)
        self._bg = bg
        self._radius = radius
        self.bind('<Configure>', self._draw)

    def _draw(self, event=None):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        r = self._radius
        # 绘制圆角矩形
        self.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=self._bg, outline='')
        self.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=self._bg, outline='')
        self.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill=self._bg, outline='')
        self.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=self._bg, outline='')
        self.create_rectangle(r, 0, w-r, h, fill=self._bg, outline='')
        self.create_rectangle(0, r, w, h-r, fill=self._bg, outline='')


class GlowButton(tk.Canvas):
    """发光按钮"""
    def __init__(self, parent, text="", command=None, color=COLORS['accent'],
                 hover_color=COLORS['accent_hover'], width=140, height=44, **kwargs):
        self.btn_width = int(width)
        self.btn_height = int(height)
        super().__init__(parent, width=self.btn_width, height=self.btn_height,
                        bg=parent['bg'], highlightthickness=0, **kwargs)
        self.command = command
        self.color = color
        self.hover_color = hover_color
        self.text = text
        self._enabled = True
        self._draw()
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<ButtonPress-1>', lambda e: self._click())

    def _draw(self, hover=False):
        self.delete('all')
        w = self.btn_width
        h = self.btn_height
        r = 8
        c = self.hover_color if hover else self.color
        # 圆角矩形
        self.create_arc(0, 0, 2*r, 2*r, start=90, extent=90, fill=c, outline='')
        self.create_arc(w-2*r, 0, w, 2*r, start=0, extent=90, fill=c, outline='')
        self.create_arc(0, h-2*r, 2*r, h, start=180, extent=90, fill=c, outline='')
        self.create_arc(w-2*r, h-2*r, w, h, start=270, extent=90, fill=c, outline='')
        self.create_rectangle(r, 0, w-r, h, fill=c, outline='')
        self.create_rectangle(0, r, w, h-r, fill=c, outline='')
        # 文字
        self.create_text(w/2, h/2, text=self.text, fill='#ffffff',
                        font=('Microsoft YaHei UI', 10, 'bold'))

    def _hover(self, enter):
        if self._enabled:
            self._draw(enter)
            self.config(cursor='hand2' if enter else '')

    def _click(self):
        if self._enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.color = COLORS['accent'] if enabled else '#484f58'
        self._draw()


class ModernSwitch(tk.Canvas):
    """开关"""
    def __init__(self, parent, variable=None, width=44, height=24, **kwargs):
        self.variable = variable or tk.BooleanVar()
        self.sw_width = int(width)
        self.sw_height = int(height)
        super().__init__(parent, width=self.sw_width, height=self.sw_height,
                        bg=kwargs.pop('bg', COLORS['bg_card']), highlightthickness=0, **kwargs)
        self.bind('<ButtonPress-1>', lambda e: self._toggle())
        # 延迟绘制，确保widget已初始化
        self.after(10, self._draw)

    def _draw(self):
        try:
            self.delete('all')
        except tk.TclError:
            return
        w = self.sw_width
        h = self.sw_height
        r = h // 2
        bg = COLORS['accent'] if self.variable.get() else '#484f58'
        # 背景
        self.create_arc(0, 0, h, h, start=90, extent=180, fill=bg, outline='')
        self.create_arc(w-h, 0, w, h, start=270, extent=180, fill=bg, outline='')
        self.create_rectangle(r, 0, w-r, h, fill=bg, outline='')
        # 滑块
        x = w - h + 2 if self.variable.get() else 2
        self.create_oval(x, 2, x + h - 4, h - 2, fill='#ffffff', outline='')

    def _toggle(self):
        self.variable.set(not self.variable.get())
        self._draw()

    def refresh(self):
        self._draw()


class LogArea(tk.Frame):
    """日志区域"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=parent['bg'], **kwargs)
        self.text = tk.Text(self, font=('Cascadia Code', 9), bg=COLORS['bg_input'],
                           fg=COLORS['text'], wrap=tk.WORD, relief='flat',
                           insertbackground=COLORS['text'], selectbackground=COLORS['blue'])
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.config(state='disabled')

        # 日志颜色
        self.text.tag_config('info', foreground=COLORS['text_dim'])
        self.text.tag_config('success', foreground=COLORS['accent'])
        self.text.tag_config('warning', foreground=COLORS['orange'])
        self.text.tag_config('error', foreground=COLORS['danger'])

    def log(self, message: str, level: str = 'info'):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text.config(state='normal')
        self.text.insert(tk.END, f" {timestamp} ", 'time')
        self.text.insert(tk.END, f"{message}\n", level)
        self.text.see(tk.END)
        self.text.config(state='disabled')

    def clear(self):
        self.text.config(state='normal')
        self.text.delete(1.0, tk.END)
        self.text.config(state='disabled')


# ============ 主应用 ============

class VideoDedupApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("搬运视频工具")
        self.root.geometry("1280x800")
        self.root.minsize(1100, 700)
        self.root.configure(bg=COLORS['bg'])

        # 启动时最大化
        try:
            self.root.state('zoomed')  # Windows最大化
        except Exception:
            try:
                self.root.attributes('-zoomed', True)  # Linux最大化
            except Exception:
                pass

        # DPI感知
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        # 配置
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        self.app_config = AppConfig.load(self.config_path)
        self.ffmpeg = FFmpegWrapper(self.app_config.ffmpeg_path, self.app_config.ffprobe_path)

        # 变量
        self.video_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.original_md5 = tk.StringVar(value="—")
        self.new_md5 = tk.StringVar(value="—")
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="就绪")

        # 功能开关变量
        self.switch_vars = {
            'mirror': tk.BooleanVar(),
            'rgb_shift': tk.BooleanVar(),
            'time_jump': tk.BooleanVar(value=True),
            'md5_change': tk.BooleanVar(value=True),
            'mask_invert': tk.BooleanVar(),
            'frame_sampling': tk.BooleanVar(),
            'noise_add': tk.BooleanVar(),
            'color_adjust': tk.BooleanVar(),
            'speed_change': tk.BooleanVar(),
        }

        # 参数变量
        self.mask_value = tk.DoubleVar(value=0.03)
        self.sampling_interval = tk.IntVar(value=5)
        self.sampling_random = tk.BooleanVar(value=True)
        self.noise_level = tk.IntVar(value=10)
        self.brightness = tk.DoubleVar(value=1.0)
        self.contrast = tk.DoubleVar(value=1.0)
        self.speed_factor = tk.DoubleVar(value=1.02)

        # 状态
        self.is_processing = False

        # 构建UI
        self._build_ui()
        self._check_deps()

        # 显示默认公告
        self._default_notice()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # 主容器
        main = tk.Frame(self.root, bg=COLORS['bg'])
        main.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)

        # 顶栏
        self._build_header(main)

        # 三栏布局
        body = tk.Frame(main, bg=COLORS['bg'])
        body.pack(fill=tk.BOTH, expand=True, pady=(16, 0))

        left = tk.Frame(body, bg=COLORS['bg'], width=320)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        left.pack_propagate(False)

        center = tk.Frame(body, bg=COLORS['bg'])
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = tk.Frame(body, bg=COLORS['bg'], width=300)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(16, 0))
        right.pack_propagate(False)

        self._build_file_panel(left)
        self._build_options_panel(center)
        self._build_log_panel(right)
        self._build_progress_bar(main)

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=COLORS['bg_card'], height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        inner = tk.Frame(header, bg=COLORS['bg_card'])
        inner.place(relx=0.5, rely=0.5, anchor='center')

        tk.Label(inner, text="⚡", font=('Arial', 20), bg=COLORS['bg_card'],
                fg=COLORS['orange']).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(inner, text="搬运视频工具", font=('Microsoft YaHei UI', 18, 'bold'),
                bg=COLORS['bg_card'], fg=COLORS['text']).pack(side=tk.LEFT)

    def _build_file_panel(self, parent):
        card = self._card(parent, "📁 文件")

        # 输入
        self._label(card, "输入文件")
        row1 = tk.Frame(card, bg=COLORS['bg_card'])
        row1.pack(fill=tk.X, pady=(2, 12))
        self.input_entry = self._entry(row1, self.video_path)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn_small(row1, "浏览", self._browse_input).pack(side=tk.RIGHT, padx=(8, 0))

        # MD5
        md5_row = tk.Frame(card, bg=COLORS['bg_card'])
        md5_row.pack(fill=tk.X, pady=(0, 12))
        self._md5_block(md5_row, "原始", self.original_md5).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._md5_block(md5_row, "处理后", self.new_md5).pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # 输出
        self._label(card, "输出路径")
        row2 = tk.Frame(card, bg=COLORS['bg_card'])
        row2.pack(fill=tk.X, pady=(2, 12))
        self.output_entry = self._entry(row2, self.output_path)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn_small(row2, "选择", self._browse_output).pack(side=tk.RIGHT, padx=(8, 0))

        # 视频信息
        self._label(card, "视频信息")
        self.info_label = tk.Label(card, text="未选择文件", font=('Cascadia Code', 8),
                                   bg=COLORS['bg_card'], fg=COLORS['text_dim'], anchor='w')
        self.info_label.pack(fill=tk.X, pady=(2, 0))

        # 预设
        preset_card = self._card(parent, "⚡ 预设")

        preset_frame = tk.Frame(preset_card, bg=COLORS['bg_card'])
        preset_frame.pack(fill=tk.X)

        presets = [
            ("快速", Preset.QUICK, COLORS['accent']),
            ("标准", Preset.STANDARD, COLORS['blue']),
            ("强力", Preset.AGGRESSIVE, COLORS['purple']),
            ("自定义", Preset.CUSTOM, COLORS['orange']),
        ]

        for i, (name, preset, color) in enumerate(presets):
            btn = tk.Button(preset_frame, text=name, font=('Microsoft YaHei UI', 9, 'bold'),
                           bg=color, fg='white', relief='flat', padx=12, pady=8,
                           activebackground=color, cursor='hand2',
                           command=lambda p=preset: self._apply_preset(p))
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4) if i < 3 else (0, 0))

        # 操作按钮
        btn_card = self._card(parent, "🎬 操作")

        self.start_btn = GlowButton(btn_card, text="🚀 开始处理", color=COLORS['accent'],
                                    hover_color=COLORS['accent_hover'], width=260, height=44,
                                    command=self._start_processing)
        self.start_btn.pack(fill=tk.X, pady=(0, 8))

        self.clear_btn = GlowButton(btn_card, text="🗑 清空", color=COLORS['border'],
                                    hover_color='#484f58', width=260, height=36,
                                    command=self._clear_all)
        self.clear_btn.pack(fill=tk.X)

        # 状态
        self.status_label = tk.Label(btn_card, textvariable=self.status_var,
                                    font=('Microsoft YaHei UI', 9),
                                    bg=COLORS['bg_card'], fg=COLORS['text_dim'])
        self.status_label.pack(pady=(8, 0))

    def _build_options_panel(self, parent):
        # 外框
        outer = tk.Frame(parent, bg=COLORS['bg'])
        outer.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # 标题
        header = tk.Frame(outer, bg=COLORS['bg_card'], highlightbackground=COLORS['border'], highlightthickness=1)
        header.pack(fill=tk.X)
        tk.Label(header, text="🔧 去重功能", font=('Microsoft YaHei UI', 11, 'bold'),
                bg=COLORS['bg_card'], fg=COLORS['text']).pack(anchor='w', padx=16, pady=(12, 8))

        # 可滚动区域
        container = tk.Frame(outer, bg=COLORS['bg_card'], highlightbackground=COLORS['border'], highlightthickness=1)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg=COLORS['bg_card'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)

        card = tk.Frame(canvas, bg=COLORS['bg_card'])
        card.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=card, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        canvas.bind('<MouseWheel>', _on_mousewheel)
        card.bind('<MouseWheel>', _on_mousewheel)

        # 内容填充

        # 基础功能
        self._section_label(card, "基础")
        basic = [
            ('mirror', '水平镜像', '左右翻转画面'),
            ('rgb_shift', 'RGB偏移', '颜色通道错位'),
            ('time_jump', '时间跳跃', '帧率微波动'),
            ('md5_change', '修改MD5', '重编码+元数据'),
        ]
        for key, name, desc in basic:
            self._option_row(card, key, name, desc)

        # 高级功能
        self._section_label(card, "高级")

        # 蒙版倒置
        self._option_row(card, 'mask_invert', '蒙版倒置', '透明度调整')
        mask_ctrl = tk.Frame(card, bg=COLORS['bg_card'])
        mask_ctrl.pack(fill=tk.X, padx=(36, 16), pady=(0, 8))
        tk.Label(mask_ctrl, text="强度", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT)
        tk.Scale(mask_ctrl, from_=0.01, to=0.5, resolution=0.01, orient=tk.HORIZONTAL,
                variable=self.mask_value, bg=COLORS['bg_card'], fg=COLORS['text'],
                highlightthickness=0, troughcolor=COLORS['bg_input'],
                length=180, showvalue=False).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(mask_ctrl, textvariable=self.mask_value, font=('Cascadia Code', 8),
                bg=COLORS['bg_card'], fg=COLORS['cyan'], width=4).pack(side=tk.LEFT)

        # 视频抽针
        self._option_row(card, 'frame_sampling', '视频抽针', '抽取特定帧')
        samp_ctrl = tk.Frame(card, bg=COLORS['bg_card'])
        samp_ctrl.pack(fill=tk.X, padx=(36, 16), pady=(0, 8))
        tk.Label(samp_ctrl, text="间隔", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT)
        tk.Spinbox(samp_ctrl, from_=2, to=30, textvariable=self.sampling_interval,
                  width=4, font=('Cascadia Code', 9), bg=COLORS['bg_input'],
                  fg=COLORS['text'], relief='flat').pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(samp_ctrl, text="帧", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT, padx=(4, 12))
        self._mini_switch(samp_ctrl, self.sampling_random, "随机").pack(side=tk.LEFT)

        # 新增功能
        self._section_label(card, "增强")

        # 噪点
        self._option_row(card, 'noise_add', '添加噪点', '随机噪点干扰')
        noise_ctrl = tk.Frame(card, bg=COLORS['bg_card'])
        noise_ctrl.pack(fill=tk.X, padx=(36, 16), pady=(0, 8))
        tk.Label(noise_ctrl, text="强度", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT)
        tk.Scale(noise_ctrl, from_=1, to=50, orient=tk.HORIZONTAL, variable=self.noise_level,
                bg=COLORS['bg_card'], fg=COLORS['text'], highlightthickness=0,
                troughcolor=COLORS['bg_input'], length=180, showvalue=False).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(noise_ctrl, textvariable=self.noise_level, font=('Cascadia Code', 8),
                bg=COLORS['bg_card'], fg=COLORS['cyan'], width=3).pack(side=tk.LEFT)

        # 色彩
        self._option_row(card, 'color_adjust', '色彩调整', '亮度对比度')
        color_ctrl = tk.Frame(card, bg=COLORS['bg_card'])
        color_ctrl.pack(fill=tk.X, padx=(36, 16), pady=(0, 8))
        tk.Label(color_ctrl, text="亮度", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT)
        tk.Scale(color_ctrl, from_=0.5, to=1.5, resolution=0.05, orient=tk.HORIZONTAL,
                variable=self.brightness, bg=COLORS['bg_card'], fg=COLORS['text'],
                highlightthickness=0, troughcolor=COLORS['bg_input'],
                length=100, showvalue=False).pack(side=tk.LEFT, padx=(8, 16))
        tk.Label(color_ctrl, text="对比度", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT)
        tk.Scale(color_ctrl, from_=0.5, to=1.5, resolution=0.05, orient=tk.HORIZONTAL,
                variable=self.contrast, bg=COLORS['bg_card'], fg=COLORS['text'],
                highlightthickness=0, troughcolor=COLORS['bg_input'],
                length=100, showvalue=False).pack(side=tk.LEFT, padx=(8, 0))

        # 速度
        self._option_row(card, 'speed_change', '速度微调', '播放速度变化')
        speed_ctrl = tk.Frame(card, bg=COLORS['bg_card'])
        speed_ctrl.pack(fill=tk.X, padx=(36, 16), pady=(0, 4))
        tk.Label(speed_ctrl, text="倍速", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT)
        tk.Scale(speed_ctrl, from_=0.95, to=1.05, resolution=0.01, orient=tk.HORIZONTAL,
                variable=self.speed_factor, bg=COLORS['bg_card'], fg=COLORS['text'],
                highlightthickness=0, troughcolor=COLORS['bg_input'],
                length=180, showvalue=False).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(speed_ctrl, textvariable=self.speed_factor, font=('Cascadia Code', 8),
                bg=COLORS['bg_card'], fg=COLORS['cyan'], width=4).pack(side=tk.LEFT)

    def _build_log_panel(self, parent):
        card = self._card(parent, "📋 日志")

        # 公告输入区
        notice_frame = tk.Frame(card, bg=COLORS['bg_card'])
        notice_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(notice_frame, text="发布公告", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(anchor='w')

        input_row = tk.Frame(notice_frame, bg=COLORS['bg_card'])
        input_row.pack(fill=tk.X, pady=(4, 0))

        self.notice_entry = tk.Entry(input_row, font=('Microsoft YaHei UI', 9),
                                    bg=COLORS['bg_input'], fg=COLORS['text'], relief='flat')
        self.notice_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.notice_entry.bind('<Return>', lambda e: self._post_notice())

        tk.Button(input_row, text="发布", font=('Microsoft YaHei UI', 8),
                 bg=COLORS['blue'], fg='white', relief='flat', padx=10,
                 cursor='hand2', command=self._post_notice).pack(side=tk.RIGHT, padx=(6, 0))

        # 日志区
        self.log_area = LogArea(card)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        btn_row = tk.Frame(card, bg=COLORS['bg_card'])
        btn_row.pack(fill=tk.X, pady=(8, 0))

        tk.Button(btn_row, text="清空日志", font=('Microsoft YaHei UI', 8),
                 bg=COLORS['border'], fg=COLORS['text_dim'], relief='flat',
                 cursor='hand2', command=self.log_area.clear).pack(side=tk.LEFT)

        tk.Button(btn_row, text="默认公告", font=('Microsoft YaHei UI', 8),
                 bg=COLORS['border'], fg=COLORS['text_dim'], relief='flat',
                 cursor='hand2', command=self._default_notice).pack(side=tk.RIGHT)

    def _build_progress_bar(self, parent):
        bottom = tk.Frame(parent, bg=COLORS['bg_card'], height=50)
        bottom.pack(fill=tk.X, pady=(16, 0))
        bottom.pack_propagate(False)

        inner = tk.Frame(bottom, bg=COLORS['bg_card'])
        inner.pack(fill=tk.BOTH, expand=True, padx=24, pady=10)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("green.Horizontal.TProgressbar",
                        background=COLORS['accent'], troughcolor=COLORS['bg_input'])

        self.progress_bar = ttk.Progressbar(inner, style="green.Horizontal.TProgressbar",
                                           variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress_label = tk.Label(inner, text="0%", font=('Cascadia Code', 10, 'bold'),
                                       bg=COLORS['bg_card'], fg=COLORS['text'], width=5)
        self.progress_label.pack(side=tk.RIGHT, padx=(12, 0))

    # ============ UI辅助方法 ============

    def _card(self, parent, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=COLORS['bg'])
        outer.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        card = tk.Frame(outer, bg=COLORS['bg_card'], highlightbackground=COLORS['border'],
                       highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(card, bg=COLORS['bg_card'])
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(header, text=title, font=('Microsoft YaHei UI', 11, 'bold'),
                bg=COLORS['bg_card'], fg=COLORS['text']).pack(anchor='w')

        content = tk.Frame(card, bg=COLORS['bg_card'])
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        return content

    def _label(self, parent, text: str):
        tk.Label(parent, text=text, font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(anchor='w')

    def _section_label(self, parent, text: str):
        tk.Label(parent, text=f"── {text} ──", font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['border']).pack(anchor='w', pady=(8, 4))

    def _entry(self, parent, variable) -> tk.Entry:
        return tk.Entry(parent, textvariable=variable, font=('Cascadia Code', 9),
                       bg=COLORS['bg_input'], fg=COLORS['text'], relief='flat',
                       insertbackground=COLORS['text'])

    def _btn_small(self, parent, text: str, command) -> tk.Button:
        return tk.Button(parent, text=text, font=('Microsoft YaHei UI', 8),
                        bg=COLORS['blue'], fg='white', relief='flat',
                        padx=12, pady=4, cursor='hand2', command=command)

    def _md5_block(self, parent, label: str, variable: tk.StringVar):
        frame = tk.Frame(parent, bg=COLORS['bg_card'])
        tk.Label(frame, text=label, font=('Microsoft YaHei UI', 7),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(anchor='w')
        tk.Label(frame, textvariable=variable, font=('Cascadia Code', 7),
                bg=COLORS['bg_card'], fg=COLORS['cyan'], wraplength=140).pack(anchor='w')
        return frame

    def _option_row(self, parent, key: str, name: str, desc: str):
        row = tk.Frame(parent, bg=COLORS['bg_card'])
        row.pack(fill=tk.X, pady=2)

        var = self.switch_vars[key]
        switch = ModernSwitch(row, variable=var)
        switch.pack(side=tk.LEFT, padx=(0, 10))

        text_frame = tk.Frame(row, bg=COLORS['bg_card'])
        text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(text_frame, text=name, font=('Microsoft YaHei UI', 9, 'bold'),
                bg=COLORS['bg_card'], fg=COLORS['text']).pack(anchor='w')
        tk.Label(text_frame, text=desc, font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(anchor='w')

    def _mini_switch(self, parent, variable: tk.BooleanVar, text: str):
        frame = tk.Frame(parent, bg=COLORS['bg_card'])
        ModernSwitch(frame, variable=variable, width=32, height=18).pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(frame, text=text, font=('Microsoft YaHei UI', 8),
                bg=COLORS['bg_card'], fg=COLORS['text_dim']).pack(side=tk.LEFT)
        return frame

    # ============ 功能方法 ============

    def _post_notice(self):
        """发布公告"""
        text = self.notice_entry.get().strip()
        if text:
            self.log_area.log(f"📢 公告: {text}", 'warning')
            self.notice_entry.delete(0, tk.END)

    def _default_notice(self):
        """发布默认公告"""
        self.log_area.log("=" * 40, 'warning')
        self.log_area.log("📢 欢迎使用搬运视频工具", 'warning')
        self.log_area.log("💬 QQ群: 1029378153", 'warning')
        self.log_area.log("🔔 有问题请加群咨询", 'warning')
        self.log_area.log("=" * 40, 'warning')

    def _check_deps(self):
        missing = []
        if not os.path.exists(self.app_config.ffmpeg_path):
            missing.append(f"FFmpeg: {self.app_config.ffmpeg_path}")
        if not os.path.exists(self.app_config.ffprobe_path):
            missing.append(f"FFprobe: {self.app_config.ffprobe_path}")
        if missing:
            self.log_area.log(f"缺少组件: {', '.join(missing)}", 'warning')

    def _apply_preset(self, preset: Preset):
        config = ProcessingConfig.from_preset(preset)
        self.switch_vars['mirror'].set(config.mirror)
        self.switch_vars['rgb_shift'].set(config.rgb_shift)
        self.switch_vars['time_jump'].set(config.time_jump)
        self.switch_vars['md5_change'].set(config.md5_change)
        self.switch_vars['mask_invert'].set(config.mask_invert)
        self.switch_vars['frame_sampling'].set(config.frame_sampling)
        self.switch_vars['noise_add'].set(config.noise_add)
        self.switch_vars['color_adjust'].set(config.color_adjust)
        self.switch_vars['speed_change'].set(config.speed_change)
        self.log_area.log(f"已应用预设: {preset.value}", 'info')

    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            initialdir=self.app_config.last_input_dir or "",
            filetypes=[("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm"), ("所有文件", "*.*")]
        )
        if path:
            self.video_path.set(path)
            self.app_config.last_input_dir = str(Path(path).parent)
            if not self.output_path.get():
                p = Path(path)
                ts = datetime.now().strftime("%H%M%S")
                self.output_path.set(str(p.parent / f"{p.stem}_dedup_{ts}{p.suffix}"))
            self._calc_md5(path, self.original_md5, "原始")
            self._update_info(path)
            self.log_area.log(f"已选择: {os.path.basename(path)}", 'info')

    def _browse_output(self):
        if not self.video_path.get():
            messagebox.showwarning("提示", "请先选择输入文件")
            return
        p = Path(self.video_path.get())
        path = filedialog.asksaveasfilename(
            title="选择输出位置", initialdir=str(p.parent),
            defaultextension=p.suffix, filetypes=[(f"{p.suffix} 文件", f"*{p.suffix}")]
        )
        if path:
            self.output_path.set(path)

    def _calc_md5(self, file_path: str, variable: tk.StringVar, label: str):
        def calc():
            try:
                self.root.after(0, lambda: variable.set("计算中..."))
                md5 = hashlib.md5()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        md5.update(chunk)
                self.root.after(0, lambda: variable.set(md5.hexdigest()))
                self.log_area.log(f"{label}MD5: {md5.hexdigest()}", 'success')
            except Exception as e:
                self.root.after(0, lambda: variable.set("失败"))
                self.log_area.log(f"计算MD5失败: {e}", 'error')
        threading.Thread(target=calc, daemon=True).start()

    def _update_info(self, file_path: str):
        def get():
            try:
                duration = self.ffmpeg.get_duration(file_path)
                w, h = self.ffmpeg.get_resolution(file_path)
                size = os.path.getsize(file_path) / (1024 * 1024)
                info = f"{w}×{h}  |  {duration:.1f}秒  |  {size:.1f}MB"
                self.root.after(0, lambda: self.info_label.config(text=info))
            except Exception:
                self.root.after(0, lambda: self.info_label.config(text="获取失败"))
        threading.Thread(target=get, daemon=True).start()

    def _start_processing(self):
        if self.is_processing:
            return
        if not self.video_path.get():
            messagebox.showwarning("提示", "请选择输入文件")
            return
        if not self.output_path.get():
            messagebox.showwarning("提示", "请设置输出路径")
            return

        config = self._build_config()
        if not any([config.mirror, config.rgb_shift, config.time_jump, config.md5_change,
                   config.mask_invert, config.frame_sampling, config.noise_add,
                   config.color_adjust, config.speed_change]):
            messagebox.showwarning("提示", "请至少选择一个功能")
            return

        self.is_processing = True
        self.start_btn.set_enabled(False)
        self.status_var.set("处理中...")
        self._process_start_time = time.time()

        threading.Thread(target=self._process, args=(config,), daemon=True).start()

    def _build_config(self) -> ProcessingConfig:
        return ProcessingConfig(
            mirror=self.switch_vars['mirror'].get(),
            rgb_shift=self.switch_vars['rgb_shift'].get(),
            time_jump=self.switch_vars['time_jump'].get(),
            md5_change=self.switch_vars['md5_change'].get(),
            mask_invert=self.switch_vars['mask_invert'].get(),
            mask_invert_value=self.mask_value.get(),
            frame_sampling=self.switch_vars['frame_sampling'].get(),
            frame_sampling_interval=self.sampling_interval.get(),
            frame_sampling_random=self.sampling_random.get(),
            noise_add=self.switch_vars['noise_add'].get(),
            noise_level=self.noise_level.get(),
            color_adjust=self.switch_vars['color_adjust'].get(),
            brightness=self.brightness.get(),
            contrast=self.contrast.get(),
            speed_change=self.switch_vars['speed_change'].get(),
            speed_factor=self.speed_factor.get(),
        )

    def _process(self, config: ProcessingConfig):
        try:
            input_path = self.video_path.get()
            output_path = self.output_path.get()

            self.log_area.log(f"开始处理: {os.path.basename(input_path)}", 'info')

            cmd = self.ffmpeg.build_command(input_path, output_path, config)
            self.log_area.log(f"命令: {' '.join(cmd[:6])}...", 'info')

            def prog_cb(p):
                self.root.after(0, lambda: self._set_progress(p))

            def log_cb(line):
                self.root.after(0, lambda: self.log_area.log(line, 'info'))

            success = self.ffmpeg.execute_with_progress(cmd, input_path, prog_cb, log_cb)

            if success and os.path.exists(output_path):
                self._calc_md5(output_path, self.new_md5, "新")
                elapsed = time.time() - self._process_start_time
                self.log_area.log(f"✅ 完成! 耗时 {elapsed:.1f}秒", 'success')
                self.root.after(0, lambda: self.status_var.set("处理完成"))
                self.root.after(0, lambda: messagebox.showinfo("成功", "视频处理完成!"))
            else:
                raise Exception("处理失败，输出文件未生成")

        except Exception as e:
            self.log_area.log(f"❌ 错误: {e}", 'error')
            self.root.after(0, lambda: self.status_var.set("处理失败"))
            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))

        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.start_btn.set_enabled(True))
            self.root.after(0, lambda: self._set_progress(0))

    def _set_progress(self, percent: int):
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{percent}%")

    def _clear_all(self):
        self.video_path.set("")
        self.output_path.set("")
        self.original_md5.set("—")
        self.new_md5.set("—")
        self.info_label.config(text="未选择文件")
        self.status_var.set("就绪")
        self._set_progress(0)
        self.log_area.clear()
        self.log_area.log("界面已清空", 'info')

    def _on_close(self):
        self.app_config.save(self.config_path)
        self.root.destroy()


def main():
    try:
        root = tk.Tk()
        app = VideoDedupApp(root)
        root.mainloop()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")


if __name__ == "__main__":
    main()
