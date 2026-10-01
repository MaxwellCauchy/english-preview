"""Tkinter 界面。读取在工作线程中执行；Tk 操作只发生在主线程。"""

import logging
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from core.exporter import save_markdown
from core.models import AnalysisConfig, AnalysisResult, ConversionResult, Document, ReaderConfig
from core.pdf_reader import CancelledError, PDFReadError, PasswordRequiredError, read_pdf
from .widgets import DropZone, MarkdownEditor
from .analysis_panel import AnalysisPanel
from .study_panel import StudyPanel

LOG = logging.getLogger(__name__)


def create_root() -> tk.Tk:
    try:
        from tkinterdnd2 import TkinterDnD
    except ImportError:
        return tk.Tk()
    previous_root = getattr(tk, "_default_root", None)
    try:
        return TkinterDnD.Tk()
    except (RuntimeError, tk.TclError):
        # TkinterDnD 在初始化 Tk 后才加载扩展；失败时清理已创建的空窗口。
        orphan = getattr(tk, "_default_root", None)
        if orphan is not None and orphan is not previous_root:
            orphan.destroy()
        return tk.Tk()


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.path: Path | None = None
        self.result: ConversionResult | None = None
        self.analysis_result: AnalysisResult | None = None
        self.study_result = None
        self._analysis_config_at_result: AnalysisConfig | None = None
        self._pending_analysis_config: AnalysisConfig | None = None
        self.busy = False
        self.closed = False
        self.password: str | None = None
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.status = tk.StringVar(value="请选择 PDF。读取完成后可编辑并保存 Markdown。")
        self.progress = tk.DoubleVar(value=0)
        self.columns = tk.StringVar(value="自动识别")
        self.remove_headers = tk.BooleanVar(value=True)
        self.dehyphenate = tk.BooleanVar(value=True)
        self.extract_images = tk.BooleanVar(value=True)
        self._build()
        self.drop_zone.enable_drop()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_id = self.root.after(80, self._poll)

    def _build(self) -> None:
        root = self.root
        root.title("English Preview v0.3 · 读取、分析与预习单")
        root.geometry("1180x900")
        root.minsize(1040, 780)
        root.configure(bg="#eef2f7")
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        families = {family.casefold(): family for family in tkfont.families(root)}
        ui_family = next(
            (families[name.casefold()] for name in (
                "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                "Noto Sans CJK SC", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
                "WenQuanYi", "WenQuanYi Bitmap Song", "WenQuanYi WenQuanYiSong",
            ) if name.casefold() in families),
            tkfont.nametofont("TkDefaultFont", root).actual("family"),
        )
        style.configure(".", font=(ui_family, 10))
        style.configure("TFrame", background="#eef2f7")
        style.configure("TLabel", background="#eef2f7", foreground="#24344d")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", background="#ffffff", foreground="#63728a")
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#17243a", font=(ui_family, 15, "bold"))
        style.configure("Title.TLabel", font=(ui_family, 22, "bold"), foreground="#17243a")
        style.configure("TButton", padding=(14, 8))
        style.configure("Accent.TButton", background="#2563eb", foreground="white")
        style.map("Accent.TButton", background=[("disabled", "#c7d2e1"), ("active", "#1d4ed8")])
        style.configure("TCheckbutton", background="#eef2f7", foreground="#24344d")
        style.configure("TProgressbar", background="#2563eb", troughcolor="#dce4ef")

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame = ttk.Frame(root, padding=24)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        ttk.Label(frame, text="English Preview", style="Title.TLabel").grid(row=0, sticky="w")
        ttk.Label(frame, text="整理课堂 PDF · 离线分析 · 生成预习清单").grid(row=1, sticky="w", pady=(4, 18))
        self.drop_zone = DropZone(frame, self._accept_files, self.choose_file)
        self.drop_zone.grid(row=2, sticky="ew")

        options = ttk.Frame(frame)
        options.grid(row=3, sticky="ew", pady=14)
        ttk.Label(options, text="阅读顺序").pack(side="left", padx=(0, 8))
        self.column_combo = ttk.Combobox(
            options, textvariable=self.columns, values=("自动识别", "单栏", "双栏"),
            state="readonly", width=10,
        )
        self.column_combo.pack(side="left", padx=(0, 16))
        self.option_checks = [
            ttk.Checkbutton(options, text="去页眉页脚", variable=self.remove_headers),
            ttk.Checkbutton(options, text="修复断词", variable=self.dehyphenate),
            ttk.Checkbutton(options, text="保留图片", variable=self.extract_images),
        ]
        for check in self.option_checks:
            check.pack(side="left", padx=(0, 12))

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=4, sticky="ew", pady=(0, 10))
        self.start_button = ttk.Button(
            toolbar, text="开始读取", style="Accent.TButton", command=self.start, state="disabled"
        )
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(toolbar, text="取消", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(toolbar, text="保存 Markdown", command=self.save, state="disabled")
        self.save_button.pack(side="right")
        self.copy_button = ttk.Button(toolbar, text="复制文本", command=self.copy, state="disabled")
        self.copy_button.pack(side="right", padx=8)
        self.notebook = ttk.Notebook(frame)
        self.notebook.grid(row=5, sticky="nsew")
        self.editor = MarkdownEditor(self.notebook)
        self.notebook.add(self.editor, text="Markdown")
        self.analysis_panel = AnalysisPanel(self.notebook, self.analyze, self.choose_targets,
                                            self.copy_analysis, self.save_analysis)
        self.notebook.add(self.analysis_panel, text="分析")
        self.study_panel = StudyPanel(self.notebook, self.build_study, self.status.set)
        self.notebook.add(self.study_panel, text="预习单")
        self.editor.text.configure(state="disabled")
        ttk.Progressbar(frame, variable=self.progress, maximum=100).grid(row=6, sticky="ew", pady=(14, 6))
        ttk.Label(frame, textvariable=self.status, wraplength=950).grid(row=7, sticky="w")

    def choose_file(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(
            parent=self.root, title="选择 PDF",
            filetypes=[("PDF 文件", "*.pdf *.PDF"), ("所有文件", "*.*")],
        )
        if path:
            self._accept_files([path])

    def _accept_files(self, paths: list[str]) -> None:
        if self.busy:
            self.status.set("正在读取，请先等待完成或取消。")
            return
        if len(paths) != 1:
            messagebox.showwarning("选择文件", "每次请选择一份 PDF。", parent=self.root)
            return
        path = Path(paths[0]).expanduser()
        if path.suffix.lower() != ".pdf" or not path.is_file():
            messagebox.showwarning("选择文件", "请选择存在的 .pdf 文件。", parent=self.root)
            return
        self.path = path.resolve()
        self.password = None
        self.result = None
        self.analysis_result = None
        self._analysis_config_at_result = None
        self.study_result = None
        self.analysis_panel.clear_result()
        self.study_panel.clear()
        self.drop_zone.set_path(str(self.path))
        self.editor.set_text("")
        self.editor.text.configure(state="disabled")
        self.progress.set(0)
        self.status.set(f"已选择 {path.name}，点击「开始读取」。")
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.drop_zone.choose_button.configure(state="disabled" if busy else "normal")
        self.column_combo.configure(state="disabled" if busy else "readonly")
        for check in self.option_checks:
            check.configure(state="disabled" if busy else "normal")
        self.start_button.configure(state="normal" if self.path and not busy else "disabled")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        for button in (self.save_button, self.copy_button):
            button.configure(state="normal" if self.result and not busy else "disabled")
        self.analysis_panel.set_state(self.result is not None, busy)
        self.study_panel.set_state(self.result is not None, busy)

    def start(self) -> None:
        if self.busy or self.path is None:
            return
        config = ReaderConfig(
            columns={"自动识别": "auto", "单栏": "single", "双栏": "double"}[self.columns.get()],
            remove_headers=self.remove_headers.get(),
            dehyphenate=self.dehyphenate.get(),
            extract_images=self.extract_images.get(),
        )
        self.result = None
        self.analysis_result = None
        self._analysis_config_at_result = None
        self.study_result = None
        self.analysis_panel.clear_result()
        self.study_panel.clear()
        self.editor.set_text("")
        self.editor.text.configure(state="disabled")
        self.cancel_event = threading.Event()
        self.progress.set(0)
        self.status.set("正在打开 PDF…")
        self._set_busy(True)
        self.worker = threading.Thread(
            target=self._read_worker, args=(self.path, config, self.password, self.cancel_event), daemon=True
        )
        self.worker.start()

    def _read_worker(self, path: Path, config: ReaderConfig, password: str | None, cancel_event: threading.Event) -> None:
        def progress(done: int, total: int, message: str) -> None:
            self.events.put(("progress", (done, total, message)))
        try:
            result = read_pdf(path, config=config, password=password, progress_callback=progress, cancel_event=cancel_event)
            self.events.put(("done", result))
        except PasswordRequiredError as exc:
            self.events.put(("password", str(exc)))
        except CancelledError as exc:
            self.events.put(("cancelled", str(exc)))
        except PDFReadError as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            LOG.exception("PDF 读取失败")
            self.events.put(("error", "读取失败。请尝试重新导出 PDF，或检查文件格式。"))

    def _poll(self) -> None:
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind in ("done", "analysis_done", "study_done") and self.cancel_event.is_set():
                    self._set_busy(False)
                    self.progress.set(0)
                    self.status.set("已取消本次处理。")
                    continue
                if kind == "progress":
                    done, total, message = payload
                    self.progress.set(done / max(1, total) * 90)
                    self.status.set(message)
                elif kind == "done":
                    self.result = payload
                    self.editor.set_text(payload.markdown)
                    self.progress.set(100)
                    self._set_busy(False)
                    self.notebook.select(self.editor)
                    self.status.set(f"读取完成 · {payload.page_count} 页 · 可编辑 Markdown，或在分析页点击「分析正文」")
                    if payload.warnings:
                        warnings = list(dict.fromkeys(payload.warnings))
                        display = "\n".join(warnings[:12])
                        if len(warnings) > 12:
                            display += f"\n另有 {len(warnings) - 12} 条提示。"
                        messagebox.showwarning("请核对这些内容", display, parent=self.root)
                elif kind == "analysis_done":
                    self.analysis_result = payload
                    self._analysis_config_at_result = self._pending_analysis_config
                    self.analysis_panel.show_result(payload)
                    self.progress.set(100)
                    self._set_busy(False)
                    self.notebook.select(self.analysis_panel)
                    self.status.set("分析完成。选择左侧分类查看结果，或复制/保存完整报告。")
                elif kind == "study_done":
                    analysis, study, config = payload
                    self.analysis_result = analysis
                    self._analysis_config_at_result = config
                    self.analysis_panel.show_result(analysis)
                    self.study_result = study
                    self.study_panel.show_study_list(study)
                    self.progress.set(100)
                    self._set_busy(False)
                    self.notebook.select(self.study_panel)
                    self.status.set("预习单生成完成。选择词或句子查看详情，或保存 Markdown / HTML。")
                else:
                    self._set_busy(False)
                    self.progress.set(0)
                    self.status.set(payload)
                    if kind == "password":
                        password = simpledialog.askstring(
                            "PDF 打开密码", payload, show="*", parent=self.root
                        )
                        if password is not None:
                            self.password = password
                            self.start()
                    elif kind == "error":
                        messagebox.showerror("处理失败", payload, parent=self.root)
        except queue.Empty:
            pass
        self._poll_id = self.root.after(80, self._poll)

    def cancel(self) -> None:
        if self.busy:
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status.set("正在取消，会在当前处理步骤完成后停止…")

    def choose_targets(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.root, title="导入目标词清单",
                                          filetypes=[("目标词清单", "*.txt *.csv")])
        if not path:
            return
        try:
            from core.analyzer import load_target_words
            words = load_target_words(path)
            self.analysis_panel.set_targets(words, Path(path))
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror("清单导入失败", str(exc), parent=self.root)

    def analyze(self) -> None:
        if self.busy or self.result is None:
            return
        try:
            config = self.analysis_panel.config()
        except ValueError as exc:
            messagebox.showerror("分析选项", str(exc), parent=self.root)
            return
        self.analysis_result = None
        self._analysis_config_at_result = None
        self._pending_analysis_config = config
        self.study_result = None
        self.analysis_panel.clear_result()
        self.study_panel.clear()
        self.cancel_event = threading.Event()
        self.progress.set(0)
        self.status.set("正在开始分析正文…")
        self._set_busy(True)
        self.worker = threading.Thread(target=self._analysis_worker,
                                       args=(self.result.document, config, self.cancel_event), daemon=True)
        self.worker.start()

    def _analysis_worker(self, document: Document, config: AnalysisConfig, cancel_event: threading.Event) -> None:
        try:
            from core.analyzer import AnalysisCancelled, AnalysisError, analyze_document
        except ImportError:
            self.events.put(("error", "缺少分析依赖。请运行 python -m pip install -r requirements.txt。"))
            return
        try:
            def progress(done: int, total: int, message: str) -> None:
                self.events.put(("progress", (done, total, message)))
            result = analyze_document(document, config, progress_callback=progress, cancel_event=cancel_event)
            self.events.put(("analysis_done", result))
        except AnalysisCancelled as exc:
            self.events.put(("cancelled", str(exc)))
        except (AnalysisError, ValueError) as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            LOG.exception("正文分析失败")
            self.events.put(("error", "分析失败。请检查分析资源是否完整，或尝试降低分析范围。"))

    def copy_analysis(self) -> None:
        if self.analysis_result is not None and not self.busy:
            from core.analysis.report import analysis_to_markdown
            self.root.clipboard_clear()
            self.root.clipboard_append(analysis_to_markdown(self.analysis_result))
            self.status.set("完整分析报告已复制。")

    def build_study(self) -> None:
        """分析选项变化或尚未分析时先分析，否则复用缓存。"""
        if self.busy or self.result is None:
            return
        try:
            study_config = self.study_panel.config()
            analysis_config = self.analysis_panel.config()
        except ValueError as exc:
            messagebox.showerror("预习选项", str(exc), parent=self.root)
            return
        cached = self.analysis_result if self._analysis_config_at_result == analysis_config else None
        self.study_result = None
        self.study_panel.clear()
        self.cancel_event = threading.Event()
        self.progress.set(0)
        self.status.set("正在生成预习单…" if cached is not None else "先分析正文，再生成预习单…")
        self._set_busy(True)
        self.worker = threading.Thread(target=self._study_worker,
            args=(self.result.document, cached, analysis_config, study_config, self.cancel_event), daemon=True)
        self.worker.start()

    def _study_worker(self, document: Document, cached: AnalysisResult | None,
                      analysis_config: AnalysisConfig, study_config, cancel_event: threading.Event) -> None:
        """后台只执行核心操作，进度和结果通过队列回传。"""
        try:
            from core.analyzer import AnalysisCancelled, AnalysisError, analyze_document
            from core.study.builder import StudyCancelled, build_study_list
        except ImportError:
            self.events.put(("error", "缺少分析依赖。请运行 python -m pip install -r requirements.txt。"))
            return
        try:
            def check_cancel() -> None:
                if cancel_event.is_set():
                    raise StudyCancelled("预习单生成已取消。")

            def analysis_progress(done: int, total: int, message: str) -> None:
                check_cancel()
                self.events.put(("progress", (done, total * 2, message)))

            def study_progress(done: int, total: int, message: str) -> None:
                check_cancel()
                self.events.put(("progress", (done + total if cached is None else done,
                                             total * 2 if cached is None else total, message)))

            check_cancel()
            analysis = cached if cached is not None else analyze_document(document, analysis_config,
                progress_callback=analysis_progress, cancel_event=cancel_event)
            check_cancel()
            study = build_study_list(analysis, study_config, progress_callback=study_progress,
                                     document=document, analysis_config=analysis_config)
            check_cancel()
            self.events.put(("study_done", (analysis, study, analysis_config)))
        except (AnalysisCancelled, StudyCancelled) as exc:
            self.events.put(("cancelled", str(exc)))
        except (AnalysisError, ValueError) as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            LOG.exception("预习单生成失败")
            self.events.put(("error", "预习单生成失败，请检查资源文件或重新分析正文。"))

    def save_analysis(self) -> None:
        if self.analysis_result is None or self.busy:
            return
        destination = filedialog.asksaveasfilename(parent=self.root, title="保存分析报告", defaultextension=".md",
            initialfile=(self.path.stem if self.path else "document") + "_analysis.md",
            filetypes=[("Markdown 报告", "*.md"), ("JSON 数据", "*.json")])
        if destination:
            try:
                from core.analysis.report import save_analysis
                saved = save_analysis(self.analysis_result, destination)
                self.status.set(f"分析报告已保存：{saved}")
            except (OSError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=self.root)

    def save(self) -> None:
        if self.result is None or self.busy:
            return
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="保存 Markdown", defaultextension=".md",
            initialfile=(self.path.stem if self.path else "document") + ".md",
            filetypes=[("Markdown 文件", "*.md")],
        )
        if not destination:
            return
        try:
            saved = save_markdown(self.result, destination, markdown=self.editor.get_text())
        except (OSError, ValueError):
            messagebox.showerror("保存失败", "文件或图片无法保存，请检查目录权限。", parent=self.root)
            return
        self.editor.text.edit_modified(False)
        self.status.set(f"已保存：{saved}（图片会保存到旁边的资源文件夹）")

    def copy(self) -> None:
        if self.result is not None and not self.busy:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.editor.get_text())
            self.status.set("Markdown 文本已复制。")

    def close(self) -> None:
        if self.result is not None and self.editor.text.edit_modified():
            if not messagebox.askyesno("关闭窗口", "有尚未保存的修改，仍要关闭吗？", parent=self.root):
                return
        self.closed = True
        self.cancel_event.set()
        self.password = None
        self.root.after_cancel(self._poll_id)
        self.root.destroy()


def launch() -> None:
    root = create_root()
    MainWindow(root)
    root.mainloop()
