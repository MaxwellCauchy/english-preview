"""文件选择区和 Markdown 编辑区。"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable


class DropZone(ttk.Frame):
    def __init__(self, parent, on_files: Callable[[list[str]], None], on_choose: Callable[[], None]):
        super().__init__(parent, style="Card.TFrame", padding=18)
        self.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            self, text="将 PDF 拖到这里", style="CardTitle.TLabel", anchor="center"
        )
        self.title_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.hint_label = ttk.Label(
            self, text="支持文字型 PDF · 文件在本机处理", style="Card.TLabel", anchor="center"
        )
        self.hint_label.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.choose_button = ttk.Button(self, text="选择 PDF 文件", command=on_choose)
        self.choose_button.grid(row=2, column=0)
        self.path_label = ttk.Label(
            self, text="尚未选择文件", style="Card.TLabel", anchor="center", wraplength=850
        )
        self.path_label.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self._on_files = on_files

    def enable_drop(self) -> bool:
        try:
            from tkinterdnd2 import DND_FILES
            for widget in (self, self.title_label, self.hint_label, self.path_label):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._drop)
            return True
        except (ImportError, AttributeError, tk.TclError):
            self.title_label.configure(text="选择一份 PDF 开始")
            self.hint_label.configure(text="拖拽不可用，可通过按钮选择文件")
            return False

    def _drop(self, event):
        try:
            # Tcl 的 splitlist 能正确处理含空格、中文和花括号的路径。
            paths = list(self.tk.splitlist(event.data))
        except tk.TclError:
            paths = []
        self._on_files(paths)
        return "copy"

    def set_path(self, path: str) -> None:
        self.path_label.configure(text=path)


class MarkdownEditor(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        families = {family.casefold(): family for family in tkfont.families(parent)}
        mono_family = next(
            (families[name.casefold()] for name in ("Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")
             if name.casefold() in families),
            tkfont.nametofont("TkFixedFont", parent).actual("family"),
        )
        self.text = tk.Text(
            self, wrap="word", undo=True, font=(mono_family, 12),
            bg="#ffffff", fg="#17243a", insertbackground="#2563eb",
            relief="flat", padx=18, pady=16, spacing1=2, spacing3=5,
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def set_text(self, text: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.text.yview_moveto(0)

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c")
