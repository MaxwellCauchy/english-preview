"""组装分析配置、展示结果；分析规则留在 core。"""

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from core.analysis.report import report_sections
from core.models import AnalysisConfig, AnalysisResult
from .widgets import MarkdownEditor


class AnalysisPanel(ttk.Frame):
    def __init__(self, parent, on_analyze: Callable[[], None], on_targets: Callable[[], None],
                 on_copy: Callable[[], None], on_save: Callable[[], None]):
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.mode = tk.StringVar(value="自动识别")
        self.max_words = tk.StringVar(value="25")
        self.min_frequency = tk.StringVar(value="2")
        self.include_lists = tk.BooleanVar(value=False)
        self.target_words: list[str] | None = None
        self.target_label = tk.StringVar(value="未导入目标词清单；词汇模式会显示候选词")
        self.summary = tk.StringVar(value="先读取 PDF，再点击「分析正文」。调整选项后需重新分析。")
        self.result: AnalysisResult | None = None
        self.sections: dict[str, str] = {}
        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="ew")
        ttk.Label(controls, text="材料类型").pack(side="left", padx=(0, 6))
        self.mode_combo = ttk.Combobox(controls, textvariable=self.mode, width=10, state="readonly",
                                      values=("自动识别", "通用文章", "词汇材料"))
        self.mode_combo.pack(side="left", padx=(0, 12))
        ttk.Label(controls, text="长句阈值").pack(side="left")
        self.max_spin = ttk.Spinbox(controls, from_=1, to=200, width=4, textvariable=self.max_words)
        self.max_spin.pack(side="left", padx=6)
        ttk.Label(controls, text="关键词最低频次").pack(side="left", padx=(6, 0))
        self.freq_spin = ttk.Spinbox(controls, from_=1, to=100, width=4, textvariable=self.min_frequency)
        self.freq_spin.pack(side="left", padx=6)
        self.list_check = ttk.Checkbutton(controls, text="计入列表", variable=self.include_lists)
        self.list_check.pack(side="left", padx=6)
        self.analyze_button = ttk.Button(controls, text="分析正文", command=on_analyze, state="disabled")
        self.analyze_button.pack(side="right")
        targets = ttk.Frame(self)
        targets.grid(row=1, sticky="ew", pady=(8, 6))
        self.import_button = ttk.Button(targets, text="导入目标词 TXT/CSV", command=on_targets)
        self.import_button.pack(side="left")
        self.clear_button = ttk.Button(targets, text="清除清单", command=self.clear_targets)
        self.clear_button.pack(side="left", padx=6)
        ttk.Label(targets, textvariable=self.target_label).pack(side="left", padx=8)
        ttk.Label(self, textvariable=self.summary, wraplength=900).grid(row=2, sticky="w", pady=(0, 8))
        content = ttk.Panedwindow(self, orient="horizontal")
        content.grid(row=3, sticky="nsew")
        self.categories = tk.Listbox(content, exportselection=False, width=19, relief="flat",
                                     bg="#ffffff", fg="#17243a", selectbackground="#2563eb", activestyle="none")
        self.categories.bind("<<ListboxSelect>>", self._select)
        content.add(self.categories, weight=0)
        self.viewer = MarkdownEditor(content)
        self.viewer.text.configure(state="disabled")
        content.add(self.viewer, weight=1)
        bottom = ttk.Frame(self)
        bottom.grid(row=4, sticky="ew", pady=(8, 0))
        ttk.Label(bottom, text="以 PDF 正文为准；Markdown 编辑不会改变分析输入。").pack(side="left")
        self.save_button = ttk.Button(bottom, text="保存报告", command=on_save, state="disabled")
        self.save_button.pack(side="right")
        self.copy_button = ttk.Button(bottom, text="复制报告", command=on_copy, state="disabled")
        self.copy_button.pack(side="right", padx=6)

    def config(self) -> AnalysisConfig:
        try:
            max_words, min_frequency = int(self.max_words.get()), int(self.min_frequency.get())
        except ValueError as exc:
            raise ValueError("长句阈值和最低频次应填写正整数。") from exc
        return AnalysisConfig(
            mode={"自动识别": "auto", "通用文章": "article", "词汇材料": "vocabulary"}[self.mode.get()],
            max_words_per_sentence=max_words, min_frequency=min_frequency,
            target_words=list(self.target_words) if self.target_words is not None else None,
            include_lists=self.include_lists.get(),
        )

    def set_targets(self, words: list[str], path: Path) -> None:
        self.target_words = list(words)
        self.target_label.set(f"目标清单：{len(words)} 词 · {path.name}（重新分析生效）")

    def clear_targets(self) -> None:
        self.target_words = None
        self.target_label.set("未导入目标词清单；显示候选词（重新分析生效）")

    def clear_result(self) -> None:
        self.result = None
        self.sections = {}
        self.categories.delete(0, "end")
        self.viewer.set_text("")
        self.viewer.text.configure(state="disabled")
        self.summary.set("先读取 PDF，再点击「分析正文」。调整选项后需重新分析。")

    def set_state(self, ready: bool, busy: bool) -> None:
        self.mode_combo.configure(state="disabled" if busy else "readonly")
        for widget in (self.max_spin, self.freq_spin, self.list_check, self.import_button, self.clear_button):
            widget.configure(state="disabled" if busy else "normal")
        self.analyze_button.configure(state="normal" if ready and not busy else "disabled")
        for button in (self.copy_button, self.save_button):
            button.configure(state="normal" if self.result and not busy else "disabled")

    def show_result(self, result: AnalysisResult) -> None:
        self.result = result
        self.sections = report_sections(result)
        self.categories.delete(0, "end")
        for name in self.sections:
            self.categories.insert("end", name)
        self.categories.selection_set(0)
        self._select()
        stats = result.stats
        detail = "通用文章" if result.mode == "article" else "词汇材料"
        if result.mode == "vocabulary":
            progress = result.vocabulary_progress
            detail += (f" · 目标词已出现 {progress.seen_targets}/{progress.total_targets}" if progress.total_targets is not None
                       else f" · 候选词 {len(result.target_words)} 个")
        self.summary.set(f"{detail} · {stats.total_words} 词 · {stats.total_sentences} 句 · {stats.total_paragraphs} 段")

    def _select(self, event=None) -> None:
        selection = self.categories.curselection()
        if not selection:
            return
        name = self.categories.get(selection[0])
        self.viewer.set_text(f"## {name}\n\n{self.sections[name]}")
        self.viewer.text.configure(state="disabled")
