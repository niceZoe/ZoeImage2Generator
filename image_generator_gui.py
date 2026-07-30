"""
Zoe AI Image 生成器 GUI
支持文生图 (text2img) 和带参考图的图生图 (img2img) 两种模式
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import os
import sys
import time
import base64
from datetime import datetime


def _get_app_dir():
    """获取程序所在目录（兼容 PyInstaller 打包后的路径）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(_get_app_dir(), "config.json")

# ==================== 默认配置 ====================
DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://aihubmix.com/v1",
    "model": "gpt-image-2",
    "output_dir": "",
}

DEFAULT_SIZE_W = 1792
DEFAULT_SIZE_H = 1024
DEFAULT_N = 1
DEFAULT_QUALITY = "low"
MAX_SIZE = 2080


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class SettingsDialog(tk.Toplevel):
    """设置页面（弹窗）"""

    def __init__(self, parent, config, callback):
        super().__init__(parent)
        self.title("设置")
        self.geometry("520x350")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.config = config
        self.callback = callback

        pad = {"padx": 12, "pady": 6}

        # API Key
        ttk.Label(self, text="API Key").pack(anchor="w", **pad)
        self.api_key_var = tk.StringVar(value=config.get("api_key", ""))
        self.api_key_entry = ttk.Entry(self, textvariable=self.api_key_var, width=60)
        self.api_key_entry.pack(fill="x", **pad)

        # Base URL
        ttk.Label(self, text="Base URL").pack(anchor="w", **pad)
        self.base_url_var = tk.StringVar(value=config.get("base_url", ""))
        self.base_url_entry = ttk.Entry(self, textvariable=self.base_url_var, width=60)
        self.base_url_entry.pack(fill="x", **pad)

        # Model
        ttk.Label(self, text="Model").pack(anchor="w", **pad)
        self.model_var = tk.StringVar(value=config.get("model", ""))
        self.model_entry = ttk.Entry(self, textvariable=self.model_var, width=60)
        self.model_entry.pack(fill="x", **pad)

        # 输出路径
        ttk.Label(self, text="图片输出路径（留空则输出到程序同级目录）").pack(anchor="w", **pad)
        path_frame = ttk.Frame(self)
        path_frame.pack(fill="x", **pad)

        self.output_dir_var = tk.StringVar(value=config.get("output_dir", ""))
        self.path_entry = ttk.Entry(path_frame, textvariable=self.output_dir_var)
        self.path_entry.pack(side="left", fill="x", expand=True)

        ttk.Button(path_frame, text="浏览...", command=self._browse_path).pack(side="right", padx=(6, 0))

        # 按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=20)

        ttk.Button(btn_frame, text="保存", command=self._save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=6)

    def _browse_path(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir_var.set(path)

    def _save(self):
        api_key = self.api_key_var.get().strip()
        base_url = self.base_url_var.get().strip()
        model = self.model_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        if not base_url:
            messagebox.showerror("错误", "Base URL 不能为空")
            return
        if not model:
            messagebox.showerror("错误", "Model 不能为空")
            return

        self.config["api_key"] = api_key
        self.config["base_url"] = base_url
        self.config["model"] = model
        self.config["output_dir"] = output_dir

        save_config(self.config)
        if self.callback:
            self.callback(self.config)
        self.destroy()


class ImageGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ZoeImage生成器")
        self.root.geometry("660x740")
        self.root.minsize(600, 680)

        self.config = load_config()
        self.reference_image_paths = []  # 支持多张参考图
        self.start_time = None

        self._build_ui()
        self._apply_config()

    # ==================== 构建 UI ====================

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=10, pady=8)

        ttk.Label(toolbar, text="ZoeImage生成器", font=("", 14, "bold")).pack(side="left")
        ttk.Button(toolbar, text="⚙ 设置", command=self._open_settings).pack(side="right")

        # 主内容区
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        # ---- 参数区域 ----
        param_frame = ttk.LabelFrame(main, text="生成参数", padding=10)
        param_frame.pack(fill="x", pady=(0, 8))

        # 尺寸
        size_frame = ttk.Frame(param_frame)
        size_frame.pack(fill="x", pady=3)

        ttk.Label(size_frame, text="尺寸 (宽 x 高):", width=14).pack(side="left")
        self.size_w_var = tk.StringVar(value=str(DEFAULT_SIZE_W))
        self.size_h_var = tk.StringVar(value=str(DEFAULT_SIZE_H))

        vcmd_w = (self.root.register(self._validate_int), "%P")
        vcmd_h = (self.root.register(self._validate_int), "%P")

        self.size_w_entry = ttk.Entry(size_frame, textvariable=self.size_w_var, width=8, validate="key", validatecommand=vcmd_w)
        self.size_w_entry.pack(side="left")
        ttk.Label(size_frame, text=" x ").pack(side="left")
        self.size_h_entry = ttk.Entry(size_frame, textvariable=self.size_h_var, width=8, validate="key", validatecommand=vcmd_h)
        self.size_h_entry.pack(side="left")

        ttk.Label(size_frame, text="（宽高必须能被 16 整除，且 ≤ 2080）", foreground="#999", font=("", 9)).pack(side="left", padx=(8, 0))

        # 数量
        num_frame = ttk.Frame(param_frame)
        num_frame.pack(fill="x", pady=3)

        ttk.Label(num_frame, text="生成数量:", width=14).pack(side="left")
        self.n_var = tk.StringVar(value=str(DEFAULT_N))
        vcmd_n = (self.root.register(self._validate_n), "%P")
        self.n_entry = ttk.Entry(num_frame, textvariable=self.n_var, width=8, validate="key", validatecommand=vcmd_n)
        self.n_entry.pack(side="left")
        ttk.Label(num_frame, text=" (1-5)").pack(side="left", padx=(4, 0))

        # 质量（下拉选择 low / medium）
        quality_frame = ttk.Frame(param_frame)
        quality_frame.pack(fill="x", pady=3)

        ttk.Label(quality_frame, text="质量:", width=14).pack(side="left")
        self.quality_var = tk.StringVar(value=DEFAULT_QUALITY)
        self.quality_combo = ttk.Combobox(
            quality_frame, textvariable=self.quality_var,
            values=["low", "medium"],
            state="readonly", width=10
        )
        self.quality_combo.pack(side="left")

        # ---- 参考图 ----
        ref_frame = ttk.LabelFrame(main, text="参考图（可选，最多 5 张；不选则为文生图）", padding=10)
        ref_frame.pack(fill="x", pady=(0, 8))

        ref_btn_frame = ttk.Frame(ref_frame)
        ref_btn_frame.pack(fill="x")

        self.ref_count_var = tk.StringVar(value="（未选择参考图，将使用文生图模式）")
        self.ref_path_label = ttk.Label(ref_btn_frame, textvariable=self.ref_count_var, foreground="gray")
        self.ref_path_label.pack(side="left", fill="x", expand=True)

        ttk.Button(ref_btn_frame, text="选择图片...", command=self._select_references).pack(side="right", padx=(6, 0))
        ttk.Button(ref_btn_frame, text="清除", command=self._clear_references).pack(side="right")

        # ---- 提示词 ----
        prompt_frame = ttk.LabelFrame(main, text="提示词 (Prompt)", padding=10)
        prompt_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.prompt_text = tk.Text(prompt_frame, height=8, wrap="word")
        self.prompt_text.pack(fill="both", expand=True)

        # ---- 底部按钮 ----
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(0, 6))

        ttk.Button(btn_frame, text="🔄 重置参数", command=self._reset_params).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="✨ 生成图片", command=self._generate).pack(side="left")

        # ---- 状态/结果 ----
        status_frame = ttk.LabelFrame(main, text="生成结果", padding=8)
        status_frame.pack(fill="x")

        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, foreground="#555")
        self.status_label.pack(anchor="w")

        self.token_var = tk.StringVar(value="")
        self.token_label = ttk.Label(status_frame, textvariable=self.token_var, foreground="#888")
        self.token_label.pack(anchor="w")

        self.time_var = tk.StringVar(value="")
        self.time_label = ttk.Label(status_frame, textvariable=self.time_var, foreground="#888")
        self.time_label.pack(anchor="w")

    # ==================== 验证函数 ====================

    @staticmethod
    def _validate_int(value):
        if value == "":
            return True
        try:
            int(value)
            return True
        except ValueError:
            return False

    def _validate_n(self, value):
        if value == "":
            return True
        try:
            n = int(value)
            return 1 <= n <= 5
        except ValueError:
            return False

    # ==================== 功能方法 ====================

    def _open_settings(self):
        SettingsDialog(self.root, self.config, self._apply_config)

    def _apply_config(self, *_):
        """应用配置到界面"""
        pass

    def _select_references(self):
        paths = filedialog.askopenfilenames(
            title="选择参考图片（最多 5 张）",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.webp"), ("所有文件", "*.*")]
        )
        if paths:
            if len(paths) > 5:
                messagebox.showwarning("提示", "最多只能选择 5 张参考图，已自动取前 5 张")
                paths = paths[:5]
            self.reference_image_paths = list(paths)
            self._update_ref_label()

    def _update_ref_label(self):
        if not self.reference_image_paths:
            self.ref_count_var.set("（未选择参考图，将使用文生图模式）")
            self.ref_path_label.configure(foreground="gray")
        else:
            names = [os.path.basename(p) for p in self.reference_image_paths]
            self.ref_count_var.set(f"已选择 {len(self.reference_image_paths)} 张: {', '.join(names)}")
            self.ref_path_label.configure(foreground="black")

    def _clear_references(self):
        self.reference_image_paths = []
        self.ref_count_var.set("（未选择参考图，将使用文生图模式）")
        self.ref_path_label.configure(foreground="gray")

    def _reset_params(self):
        self.size_w_var.set(str(DEFAULT_SIZE_W))
        self.size_h_var.set(str(DEFAULT_SIZE_H))
        self.n_var.set(str(DEFAULT_N))
        self.quality_var.set(DEFAULT_QUALITY)
        self._clear_references()
        self.prompt_text.delete("1.0", "end")
        self.status_var.set("已重置为默认参数")
        self.status_label.configure(foreground="#555")
        self.token_var.set("")
        self.time_var.set("")

    def _generate(self):
        # 校验尺寸
        try:
            w = int(self.size_w_var.get())
            h = int(self.size_h_var.get())
            if w <= 0 or h <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "尺寸必须为正整数")
            return

        if w % 16 != 0 or h % 16 != 0:
            messagebox.showerror("参数错误", f"尺寸不合法（{w}x{h}）：宽和高必须都能被 16 整除\n\n"
                                            f"建议：{w - (w % 16)}x{h - (h % 16)} 或 {w + (16 - w % 16)}x{h + (16 - h % 16)}")
            return

        if w > MAX_SIZE or h > MAX_SIZE:
            messagebox.showerror("参数错误", f"尺寸不合法（{w}x{h}）：宽和高不能超过 {MAX_SIZE}")
            return

        try:
            n = int(self.n_var.get())
            if n < 1 or n > 5:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "生成数量必须在 1-5 之间")
            return

        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showerror("参数错误", "提示词不能为空")
            return

        quality = self.quality_var.get()
        if quality not in ("low", "medium"):
            messagebox.showerror("参数错误", "请选择有效的质量参数")
            return

        # 检查 API 配置
        api_key = self.config.get("api_key", "")
        base_url = self.config.get("base_url", "")
        model = self.config.get("model", "")
        if not api_key:
            messagebox.showerror("配置错误", "API Key 未填写，请先点击右上角「⚙ 设置」进行配置")
            return
        if not base_url or not model:
            messagebox.showerror("配置错误", "Base URL 或 Model 未填写，请先点击右上角「⚙ 设置」进行配置")
            return

        # ---- 确认弹窗 ----
        ref_info = "无（文生图模式）" if not self.reference_image_paths else f"{len(self.reference_image_paths)} 张参考图"
        prompt_preview = prompt[:120] + ("..." if len(prompt) > 120 else "")

        confirm_msg = (
            f"请确认以下生成参数：\n\n"
            f"📐 尺寸：{w} x {h}\n"
            f"🔢 数量：{n}\n"
            f"🎨 质量：{quality}\n"
            f"🖼 参考图：{ref_info}\n"
            f"📝 提示词：\n{prompt_preview}\n"
        )
        if not messagebox.askyesno("确认生成", confirm_msg):
            return

        # 确定输出目录
        output_dir = self.config.get("output_dir", "")
        if not output_dir:
            output_dir = _get_app_dir()

        # 禁用按钮，开始生成
        self._set_generating_state(True)

        # 在后台线程执行
        threading.Thread(
            target=self._do_generate,
            args=(api_key, base_url, model, prompt, w, h, n, quality, output_dir),
            daemon=True,
        ).start()

    def _set_generating_state(self, generating):
        """切换生成中/空闲状态"""
        state = "disabled" if generating else "normal"
        for child in self.root.winfo_children():
            self._set_widgets_state(child, state)

    def _set_widgets_state(self, widget, state):
        """递归设置控件状态"""
        if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, tk.Text)):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        for child in widget.winfo_children():
            self._set_widgets_state(child, state)

    def _do_generate(self, api_key, base_url, model, prompt, w, h, n, quality, output_dir):
        """在后台线程中执行 API 调用"""
        from openai import OpenAI, BadRequestError, APIError

        size = f"{w}x{h}"
        has_reference = len(self.reference_image_paths) > 0

        self._update_status("正在连接 API...", "#0078d4")
        self.start_time = time.time()

        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=2)

            if has_reference:
                # 图生图：支持多张参考图
                self._update_status(f"正在上传 {len(self.reference_image_paths)} 张参考图并生成...", "#0078d4")
                ref_files = [open(p, "rb") for p in self.reference_image_paths]
                try:
                    response = client.images.edit(
                        model=model,
                        image=ref_files if len(ref_files) > 1 else ref_files[0],
                        prompt=prompt,
                        n=n,
                        size=size,
                        quality=quality,
                    )
                finally:
                    for f in ref_files:
                        f.close()
            else:
                # 文生图
                self._update_status("正在生成图片...", "#0078d4")
                response = client.images.generate(
                    model=model,
                    prompt=prompt,
                    n=n,
                    size=size,
                    quality=quality,
                )

            elapsed = time.time() - self.start_time
            usage = response.usage

            # 保存图片
            os.makedirs(output_dir, exist_ok=True)
            saved_files = []

            for i, image_item in enumerate(response.data):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                prefix = "img2img" if has_reference else "text2img"
                file_name = f"{prefix}_{timestamp}_{i}.png"
                file_path = os.path.join(output_dir, file_name)

                if image_item.b64_json:
                    img_bytes = base64.b64decode(image_item.b64_json)
                    with open(file_path, "wb") as f:
                        f.write(img_bytes)
                elif image_item.url:
                    import requests
                    resp = requests.get(image_item.url)
                    resp.raise_for_status()
                    with open(file_path, "wb") as f:
                        f.write(resp.content)
                else:
                    continue

                saved_files.append(file_path)

            # 显示结果
            mode = "图生图" if has_reference else "文生图"
            status_text = f"✅ {mode}成功！生成 {len(saved_files)} 张图片"
            self._update_status(status_text, "green")

            if usage:
                token_info = (
                    f"Token 用量 | 输入: {usage.input_tokens} "
                    f"(图片: {getattr(usage.input_tokens_details, 'image_tokens', 0)}, "
                    f"文本: {getattr(usage.input_tokens_details, 'text_tokens', 0)}) "
                    f"| 输出: {usage.output_tokens} "
                    f"(图片: {getattr(usage.output_tokens_details, 'image_tokens', 0)}, "
                    f"文本: {getattr(usage.output_tokens_details, 'text_tokens', 0)}) "
                    f"| 总计: {usage.total_tokens}"
                )
                self.token_var.set(token_info)

            time_info = f"耗时: {elapsed:.2f} 秒"
            self.time_var.set(time_info)

            for f in saved_files:
                print(f"保存: {f}")

        except BadRequestError as e:
            self._update_status(f"❌ 请求失败: {e.message}", "red")
            self.root.after(0, lambda: messagebox.showerror("API 错误", f"请求失败:\n{e.message}"))
        except APIError as e:
            self._update_status(f"❌ API 错误: {str(e)}", "red")
            self.root.after(0, lambda: messagebox.showerror("API 错误", str(e)))
        except FileNotFoundError as e:
            self._update_status(f"❌ 文件未找到", "red")
            self.root.after(0, lambda: messagebox.showerror("文件错误", str(e)))
        except Exception as e:
            self._update_status(f"❌ 生成失败: {str(e)}", "red")
            self.root.after(0, lambda: messagebox.showerror("生成失败", str(e)))
        finally:
            self.root.after(0, lambda: self._set_generating_state(False))

    def _update_status(self, text, color="#555"):
        """更新状态栏（线程安全）"""
        self.root.after(0, lambda: self.status_var.set(text))
        self.root.after(0, lambda: self.status_label.configure(foreground=color))


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageGeneratorApp(root)
    root.mainloop()