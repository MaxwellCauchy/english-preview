"""预习单面板：只组装配置、展示与保存结果；生成由主窗口调度。"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from core.study.models import StudyConfig, StudyList
from core.study.render import save_study_list, study_list_to_markdown
from .study_preferences import DEFAULT_PATH, load_preferences, save_preferences


class StudyPanel(ttk.Frame):
    """可滚动的预习内容；选择词、句子或段落可查看完整文字。"""

    def __init__(self, master, on_build: Callable[[], None], on_status: Callable[[str], None] | None = None):
        super().__init__(master, padding=10)
        self.study: StudyList | None = None
        self._on_status = on_status or (lambda message: None)
        self.preferences_path = DEFAULT_PATH
        preferences = load_preferences(self.preferences_path)
        self.exam_level = tk.StringVar(value=preferences.get("exam_level", "四级"))
        self.max_phrases = tk.StringVar(value="12")
        self.translation_enabled = tk.BooleanVar(value=preferences.get("translate_sentences", True))
        self.model_dir = tk.StringVar(value=preferences.get("model_dir", ""))
        self.top_words = tk.StringVar(value="15")
        self.max_sentences = tk.StringVar(value="5")
        self.max_paragraphs = tk.StringVar(value="8")
        self.overview = tk.StringVar(value="先读取 PDF，再生成预习单；尚未分析时会自动分析。")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        controls = ttk.Frame(self)
        controls.grid(row=0, sticky="ew", pady=(0, 8))
        self.option_widgets = []
        extra = ttk.Frame(controls)
        extra.pack(fill="x", pady=(0, 8))
        ttk.Label(extra, text="考试目标").pack(side="left")
        self.exam_combo = ttk.Combobox(extra, textvariable=self.exam_level, values=("四级", "六级"), state="readonly", width=6)
        self.exam_combo.pack(side="left", padx=6)
        self.option_widgets.append(self.exam_combo)
        check = ttk.Checkbutton(extra, text="OPUS-MT 离线参考译文", variable=self.translation_enabled)
        check.pack(side="left", padx=6); self.option_widgets.append(check)
        self.model_button = ttk.Button(extra, text="选择模型目录", command=self.choose_model)
        self.model_button.pack(side="left", padx=6); self.option_widgets.append(self.model_button)
        self.help_button = ttk.Button(extra, text="翻译安装说明", command=self.translation_help)
        self.help_button.pack(side="left", padx=6)
        counts = ttk.Frame(controls); counts.pack(fill="x")
        for label, variable in (("必学词数量", self.top_words), ("重点句上限", self.max_sentences), ("关键段上限", self.max_paragraphs), ("短语上限", self.max_phrases)):
            ttk.Label(counts, text=label).pack(side="left", padx=(0, 6))
            spin = ttk.Spinbox(counts, from_=1, to=1000, width=4, textvariable=variable)
            spin.pack(side="left", padx=(0, 14))
            self.option_widgets.append(spin)
        self.build_button = ttk.Button(counts, text="生成预习单", command=on_build, state="disabled")
        self.build_button.pack(side="right")
        scrolling = ttk.Frame(self)
        scrolling.grid(row=1, sticky="nsew")
        scrolling.rowconfigure(0, weight=1)
        scrolling.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(scrolling, bg="#eef2f7", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(scrolling, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body = ttk.Frame(self.canvas)
        self.body.columnconfigure(0, weight=1)
        body_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(body_id, width=event.width))
        ttk.Label(self.body, text="文章速览").grid(row=0, sticky="w")
        label = ttk.Label(self.body, textvariable=self.overview, wraplength=930)
        label.grid(row=1, sticky="ew", pady=(4, 12))
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(100, event.width - 10)))
        ttk.Label(self.body, text="必学词 · 选择一项查看完整释义").grid(row=2, sticky="w", pady=(0, 4))
        self.words = self._tree(("word", "pos", "meaning", "count"), ("词", "词性", "释义", "次数"), (150, 65, 580, 65), 5, 3)
        self.words.bind("<<TreeviewSelect>>", self._show_word)
        ttk.Label(self.body, text="重点句与参考译文 · 主干为规则候选").grid(row=6, sticky="w", pady=(12, 4))
        ttk.Label(self.body, text="重点短语 · 选择一项查看原文用法").grid(row=4, sticky="w", pady=(12,4))
        self.phrases = self._tree(("phrase", "meaning", "count"), ("短语", "释义", "次数"), (280, 500, 65), 4, 5)
        self.phrases.bind("<<TreeviewSelect>>", self._show_phrase)
        self.sentences = self._tree(("paragraph", "count", "clause"), ("段落", "词数", "主干"), (70, 70, 700), 3, 7)
        self.sentences.bind("<<TreeviewSelect>>", self._show_sentence)
        detail_frame = ttk.Frame(self.body)
        detail_frame.grid(row=8, sticky="ew", pady=(6, 12))
        detail_frame.columnconfigure(0, weight=1)
        self.detail = tk.Text(detail_frame, height=6, wrap="word", relief="flat", bg="#ffffff", fg="#17243a",
                              padx=12, pady=8, state="disabled")
        self.detail.grid(row=0, column=0, sticky="ew")
        detail_scroll = ttk.Scrollbar(detail_frame, command=self.detail.yview)
        detail_scroll.grid(row=0, column=1, sticky="ns")
        self.detail.configure(yscrollcommand=detail_scroll.set)
        ttk.Label(self.body, text="关键段 · 按阅读优先级排序").grid(row=9, sticky="w", pady=(0, 4))
        self.paragraphs = self._listbox(4, 10)
        self.paragraphs.bind("<<ListboxSelect>>", self._show_paragraph)
        ttk.Label(self.body, text="文章结构").grid(row=11, sticky="w", pady=(12, 4))
        self.outline = self._listbox(5, 12)
        self.outline.bind("<<ListboxSelect>>", self._show_outline)
        ttk.Label(self.body, text="行动清单").grid(row=13, sticky="w", pady=(12, 4))
        self.actions = ttk.Frame(self.body)
        self.actions.grid(row=14, sticky="ew")
        self.action_vars: list[tk.BooleanVar] = []
        self.warnings = tk.StringVar(value="")
        ttk.Label(self.body, textvariable=self.warnings, wraplength=900).grid(row=15, sticky="w", pady=(10, 4))
        bottom = ttk.Frame(self)
        bottom.grid(row=2, sticky="ew", pady=(8, 0))
        ttk.Label(bottom, text="以 PDF 正文为准；HTML 可离线打开。").pack(side="left")
        self.html_button = ttk.Button(bottom, text="保存 HTML", command=lambda: self.save("html"), state="disabled")
        self.html_button.pack(side="right")
        self.md_button = ttk.Button(bottom, text="保存 Markdown", command=lambda: self.save("md"), state="disabled")
        self.md_button.pack(side="right", padx=6)
        self.copy_button = ttk.Button(bottom, text="复制", command=self.copy, state="disabled")
        self.copy_button.pack(side="right")

    def _tree(self, columns, headings, widths, height, row):
        frame = ttk.Frame(self.body)
        frame.grid(row=row, sticky="ew")
        frame.columnconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
        for column, title, width in zip(columns, headings, widths):
            tree.heading(column, text=title)
            tree.column(column, width=width, minwidth=45, stretch=column in ("meaning", "clause"))
        tree.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        return tree

    def _listbox(self, height, row):
        frame = ttk.Frame(self.body)
        frame.grid(row=row, sticky="ew")
        frame.columnconfigure(0, weight=1)
        listing = tk.Listbox(frame, height=height, relief="flat", exportselection=False,
                             bg="#ffffff", fg="#17243a", selectbackground="#2563eb")
        listing.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(frame, command=listing.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        listing.configure(yscrollcommand=scroll.set)
        return listing

    def config(self) -> StudyConfig:
        """组装配置，不触发分析。"""
        try:
            config = StudyConfig(top_study_words=int(self.top_words.get()), max_long_sentences=int(self.max_sentences.get()),
                               max_key_paragraphs=int(self.max_paragraphs.get()), max_phrases=int(self.max_phrases.get()),
                               exam_level={"四级":"cet4", "六级":"cet6", "通用":"general"}[self.exam_level.get()],
                               translate_sentences=bool(self.translation_enabled.get()), translation_model_dir=self.model_dir.get())
            if self.preferences_path is not None:
                try:
                    save_preferences({"exam_level": self.exam_level.get(), "model_dir": self.model_dir.get(),
                        "translate_sentences": bool(self.translation_enabled.get())}, self.preferences_path)
                except OSError:
                    self._on_status("本次选项有效，但无法保存为下次默认值。")
            return config
        except (ValueError, KeyError) as exc:
            raise ValueError("考试目标应为四级或六级，各项数量应填写 1 到 1000 的整数。") from exc

    def set_state(self, ready: bool, busy: bool) -> None:
        """工作时冻结配置，结果存在时启用导出。"""
        for widget in self.option_widgets:
            widget.configure(state="disabled" if busy else ("readonly" if widget is self.exam_combo else "normal"))
        self.build_button.configure(state="normal" if ready and not busy else "disabled")
        for widget in (self.copy_button, self.md_button, self.html_button):
            widget.configure(state="normal" if self.study is not None and not busy else "disabled")

    def show_study_list(self, study: StudyList) -> None:
        """展示已生成的数据。"""
        self.clear()
        self.study = study
        self.overview.set(study.overview or "暂无正文。")
        for index, word in enumerate(study.study_words):
            meaning = " ".join((word.meaning_cn or word.meaning_en or "暂无释义").split())
            self.words.insert("", "end", iid=str(index), values=(word.display or word.word, word.pos, meaning, word.count))
        for index, phrase in enumerate(study.study_phrases):
            self.phrases.insert("", "end", iid=str(index), values=(phrase.phrase, phrase.meaning_cn, phrase.count))
        for index, sentence in enumerate(study.sentence_breakdowns):
            self.sentences.insert("", "end", iid=str(index), values=(sentence.paragraph_index, sentence.word_count, sentence.main_clause))
        for paragraph in study.key_paragraphs:
            self.paragraphs.insert("end", f"第 {paragraph.index} 段 · {paragraph.reason} · {paragraph.first_sentence}")
        for block in study.outline.blocks:
            first, last = block.paragraph_range
            self.outline.insert("end", f"{block.title} · 第 {first}–{last} 段 · {block.word_count} 词")
        for index, action in enumerate(study.action_items):
            variable = tk.BooleanVar(value=False)
            self.action_vars.append(variable)
            ttk.Checkbutton(self.actions, text=action, variable=variable, state="disabled").grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 18))
        self.warnings.set("\n".join(study.warnings))
        self.canvas.yview_moveto(0)

    def clear(self) -> None:
        """清除上一份文件的结果。"""
        self.study = None
        self.overview.set("先读取 PDF，再生成预习单；尚未分析时会自动分析。")
        for tree in (self.words, self.phrases, self.sentences):
            tree.delete(*tree.get_children())
        for listing in (self.paragraphs, self.outline):
            listing.delete(0, "end")
        for child in self.actions.winfo_children():
            child.destroy()
        self.action_vars.clear()
        self._set_detail("")
        self.warnings.set("")
        for button in (self.copy_button, self.md_button, self.html_button):
            button.configure(state="disabled")

    def _set_detail(self, value: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")
        self.detail.yview_moveto(0)

    def _show_word(self, event=None) -> None:
        selected = self.words.selection()
        if self.study is not None and selected:
            word = self.study.study_words[int(selected[0])]
            self._set_detail(f"{word.display or word.word} · {word.pos} · {word.count} 次 · 第 {', '.join(map(str, word.locations))} 段\n\n"
                             f"{word.meaning_cn or '暂无中文释义'}\n{word.meaning_en}\n\n" + " / ".join(word.collocations) + "\n入选原因：" + "；".join(word.selection_reasons))

    def _show_sentence(self, event=None) -> None:
        selected = self.sentences.selection()
        if self.study is not None and selected:
            sentence = self.study.sentence_breakdowns[int(selected[0])]
            self._set_detail(f"原句：{sentence.text}\n\n参考译文：{sentence.translation or '尚未取得译文'}\n"
                             f"翻译状态：{sentence.translation_status} · {sentence.translation_note}\n"
                             f"前文参考：{sentence.context_before}\n入选原因：{'；'.join(sentence.selection_reasons)}\n\n主干候选：{sentence.main_clause}\n"
                             + "\n".join(sentence.modifiers) + f"\n\n{sentence.note}")

    def _show_paragraph(self, event=None) -> None:
        selected = self.paragraphs.curselection()
        if self.study is not None and selected:
            item = self.study.key_paragraphs[selected[0]]
            self._set_detail(f"第 {item.index} 段 · {item.reason}\n\n{item.first_sentence}\n\n主题词：" + " / ".join(item.topic_words))

    def _show_outline(self, event=None) -> None:
        selected = self.outline.curselection()
        if self.study is not None and selected:
            item = self.study.outline.blocks[selected[0]]
            self._set_detail(f"{item.title} · 第 {item.paragraph_range[0]}–{item.paragraph_range[1]} 段\n\n{item.summary}")

    def copy(self) -> None:
        """复制完整 Markdown。"""
        if self.study is not None and not self.copy_button.instate(["disabled"]):
            self.clipboard_clear()
            self.clipboard_append(study_list_to_markdown(self.study))
            self._on_status("预习清单已复制。")

    def save(self, fmt: str = "md") -> None:
        """选择保存位置，调用核心保存入口。"""
        if self.study is None or self.md_button.instate(["disabled"]):
            return
        destination = filedialog.asksaveasfilename(parent=self.winfo_toplevel(), title="保存预习单",
            initialfile=f"study_list.{fmt}", defaultextension=f".{fmt}",
            filetypes=[("Markdown 文件" if fmt == "md" else "HTML 文件", f"*.{fmt}")])
        if destination:
            try:
                saved = save_study_list(self.study, Path(destination), fmt)
                self._on_status(f"预习单已保存：{saved}")
            except (OSError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=self.winfo_toplevel())

    def _show_phrase(self, event=None) -> None:
        selected=self.phrases.selection()
        if self.study is not None and selected:
            phrase=self.study.study_phrases[int(selected[0])]
            self._set_detail(f"{phrase.phrase} · {phrase.count} 次 · 第 {', '.join(map(str,phrase.locations))} 段\n"
                f"{phrase.meaning_cn}\n原文形式：{' / '.join(phrase.forms)}\n\n"
                + "\n".join(phrase.examples) + f"\n\n来源：{phrase.source}\n入选原因：{'；'.join(phrase.selection_reasons)}")

    def choose_model(self) -> None:
        directory=filedialog.askdirectory(parent=self.winfo_toplevel(),title="选择 OPUS-MT 模型文件夹")
        if directory:
            self.model_dir.set(directory)
            self._on_status("翻译模型目录已选择；下次生成时核验。")

    def translation_help(self) -> None:
        messagebox.showinfo("离线翻译准备", "在项目目录运行：\n"
            "py -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu\n"
            "py -m pip install -r requirements-translation.txt\n"
            "py tools/download_translation_model.py\n\n"
            "只在首次安装时联网。安装完成后重启程序；日常翻译只读本地模型。\n"
            "未安装模型仍可生成词汇和短语。选中句子查看参考译文及状态。",
            parent=self.winfo_toplevel())
