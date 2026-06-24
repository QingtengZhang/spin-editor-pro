import csv
import difflib
import os
import re
import shutil
import sys
import time
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "SPIN 参数编辑器 Pro"
APP_VERSION = "1.0"
CHECKED = "☑"
UNCHECKED = "☐"

PARAM_LINE_RE = re.compile(
    r"^(?P<pre>\s*)"
    r"(?P<key>[A-Za-z0-9_.\-]+)"
    r"(?P<sp1>\s*)="
    r"(?P<sp2>\s*)"
    r"(?P<value>[^#]*?)"
    r"(?P<rest>\s*(?:#.*)?)$"
)


@dataclass
class ParamLine:
    pre: str
    key: str
    sp1: str
    sp2: str
    value: str
    rest: str
    newline: str
    line_no: int


@dataclass
class MetaLine:
    raw: str


@dataclass
class SpinDocument:
    path: Path
    encoding: str
    params: OrderedDict
    line_info: list


class SpinParser:
    ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1")

    @classmethod
    def read_text(cls, path):
        last_error = None
        for encoding in cls.ENCODINGS:
            try:
                return Path(path).read_text(encoding=encoding), encoding
            except UnicodeDecodeError as exc:
                last_error = exc
        raise last_error

    @classmethod
    def parse(cls, path):
        text, encoding = cls.read_text(path)
        line_info = []
        params = OrderedDict()

        for line_no, raw in enumerate(text.splitlines(keepends=True), start=1):
            body = raw.rstrip("\r\n")
            newline = raw[len(body):] or "\n"
            match = PARAM_LINE_RE.match(body)
            if match:
                data = match.groupdict()
                key = data["key"].strip()
                value = data["value"].strip()
                params[key] = {
                    "value": value,
                    "comment": data["rest"].strip(),
                    "line_no": line_no,
                }
                line_info.append(
                    ParamLine(
                        pre=data["pre"],
                        key=data["key"],
                        sp1=data["sp1"],
                        sp2=data["sp2"],
                        value=data["value"],
                        rest=data["rest"],
                        newline=newline,
                        line_no=line_no,
                    )
                )
            else:
                line_info.append(MetaLine(raw=raw))

        return SpinDocument(Path(path), encoding, params, line_info)

    @staticmethod
    def render(doc, new_params, delete_keys=None, add_missing_to_end=True):
        delete_keys = set(delete_keys or [])
        seen = set()
        lines = []

        for item in doc.line_info:
            if isinstance(item, ParamLine):
                key = item.key.strip()
                if key in delete_keys:
                    seen.add(key)
                    continue
                if key in new_params:
                    value = str(new_params[key])
                    lines.append(
                        f"{item.pre}{item.key}{item.sp1}={item.sp2}{value}{item.rest}{item.newline}"
                    )
                    seen.add(key)
                else:
                    lines.append(
                        f"{item.pre}{item.key}{item.sp1}={item.sp2}{item.value}{item.rest}{item.newline}"
                    )
            else:
                lines.append(item.raw)

        if add_missing_to_end:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += "\n"
            for key, value in new_params.items():
                if key not in seen and key not in delete_keys:
                    lines.append(f"{key}={value}\n")

        return "".join(lines)

    @staticmethod
    def write(path, text, encoding="utf-8", backup=True, backup_dir=None):
        path = Path(path)
        if backup and path.exists():
            stamp = time.strftime("%Y%m%d-%H%M%S")
            if backup_dir:
                backup_dir = Path(backup_dir)
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{path.name}.{stamp}.bak"
            else:
                backup_path = path.with_name(f"{path.name}.{stamp}.bak")
            shutil.copy2(path, backup_path)
        path.write_text(text, encoding=encoding)


class AddParamDialog(tk.Toplevel):
    def __init__(self, master, title="新增参数", key="", value=""):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.transient(master)
        self.grab_set()

        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="参数名").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=6)
        self.key_var = tk.StringVar(value=key)
        key_entry = ttk.Entry(frame, textvariable=self.key_var, width=40)
        key_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="参数值").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=6)
        self.value_var = tk.StringVar(value=value)
        value_entry = ttk.Entry(frame, textvariable=self.value_var, width=40)
        value_entry.grid(row=1, column=1, sticky="ew", pady=6)

        btns = ttk.Frame(frame)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="确定", style="Accent.TButton", command=self.accept).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _event: self.accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        key_entry.focus_set()
        self.wait_visibility()
        self.center_on_parent(master)
        self.wait_window()

    def center_on_parent(self, parent):
        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def accept(self):
        key = self.key_var.get().strip()
        value = self.value_var.get().strip()
        if not key:
            messagebox.showwarning(APP_TITLE, "参数名不能为空。", parent=self)
            return
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", key):
            messagebox.showwarning(APP_TITLE, "参数名只能包含字母、数字、下划线、点和短横线。", parent=self)
            return
        self.result = (key, value)
        self.destroy()


class SpinEditorPro:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_TITLE} {APP_VERSION}")
        self.root.minsize(1100, 680)

        self.folder = None
        self.files = []
        self.current_doc = None
        self.current_file = None
        self.visible_param_iids = []
        self.param_rows = OrderedDict()
        self.recent_folders = []
        self.dirty = False

        self.file_search_var = tk.StringVar()
        self.param_search_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.autobackup_var = tk.BooleanVar(value=True)
        self.only_checked_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="就绪")

        self.configure_style()
        self.build_ui()
        self.bind_shortcuts()
        self.center_window(1380, 820)

    def configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.colors = {
            "bg": "#f6f7fb",
            "panel": "#ffffff",
            "text": "#172033",
            "muted": "#667085",
            "line": "#d9dee8",
            "accent": "#2563eb",
            "accent_hover": "#1d4ed8",
            "warn": "#b45309",
            "danger": "#b91c1c",
        }
        self.root.configure(bg=self.colors["bg"])
        style.configure(".", font=("Microsoft YaHei UI", 10), background=self.colors["bg"])
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"], relief="solid", borderwidth=1)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"), foreground=self.colors["text"])
        style.configure("Muted.TLabel", foreground=self.colors["muted"])
        style.configure("Status.TLabel", foreground=self.colors["muted"])
        style.configure("Accent.TButton", foreground="#ffffff", background=self.colors["accent"])
        style.map("Accent.TButton", background=[("active", self.colors["accent_hover"])])
        style.configure("Danger.TButton", foreground="#ffffff", background=self.colors["danger"])
        style.configure("Treeview", rowheight=28, background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))

    def center_window(self, width, height):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max((sw - width) // 2, 0)
        y = max((sh - height) // 2, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self):
        self.build_topbar()

        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        left = ttk.Frame(main, style="Panel.TFrame", padding=10)
        center = ttk.Frame(main, style="Panel.TFrame", padding=10)
        right = ttk.Frame(main, style="Panel.TFrame", padding=10)
        main.add(left, weight=1)
        main.add(center, weight=3)
        main.add(right, weight=1)

        self.build_file_panel(left)
        self.build_table_panel(center)
        self.build_action_panel(right)

        status = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        status.pack(fill=tk.X)
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.LEFT)
        ttk.Label(status, text="提示：勾选参数后可批量应用、批量删除或批量导出。", style="Muted.TLabel").pack(side=tk.RIGHT)

    def build_topbar(self):
        bar = ttk.Frame(self.root, padding=(12, 12, 12, 8))
        bar.pack(fill=tk.X)

        title_box = ttk.Frame(bar)
        title_box.pack(side=tk.LEFT)
        ttk.Label(title_box, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="用于查看、编辑、批量同步和导出 .SPIN 参数文件", style="Muted.TLabel").pack(anchor="w")

        tools = ttk.Frame(bar)
        tools.pack(side=tk.RIGHT)
        ttk.Button(tools, text="打开文件夹", style="Accent.TButton", command=self.open_folder).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(tools, text="打开文件", command=self.open_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools, text="刷新", command=self.refresh_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools, text="帮助", command=self.show_help).pack(side=tk.LEFT, padx=(3, 0))

    def build_file_panel(self, parent):
        ttk.Label(parent, text="文件", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="支持多选，批量操作只作用于左侧选中的文件。", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))

        search_row = ttk.Frame(parent)
        search_row.pack(fill=tk.X)
        ttk.Entry(search_row, textvariable=self.file_search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(search_row, text="清空", command=lambda: self.file_search_var.set("")).pack(side=tk.LEFT, padx=(6, 0))
        self.file_search_var.trace_add("write", lambda *_: self.refresh_file_list())

        options = ttk.Frame(parent)
        options.pack(fill=tk.X, pady=8)
        ttk.Checkbutton(options, text="包含子文件夹", variable=self.recursive_var, command=self.refresh_files).pack(side=tk.LEFT)
        ttk.Checkbutton(options, text="自动备份", variable=self.autobackup_var).pack(side=tk.LEFT, padx=(12, 0))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.file_list = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["line"],
            activestyle="none",
            font=("Consolas", 10),
        )
        file_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=file_scroll.set)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        file_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.bind("<<ListboxSelect>>", self.on_file_select)

        btns = ttk.Frame(parent)
        btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btns, text="全选", command=self.select_all_files).pack(side=tk.LEFT)
        ttk.Button(btns, text="全不选", command=self.clear_file_selection).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="导出清单", command=self.export_file_index).pack(side=tk.LEFT)

    def build_table_panel(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill=tk.X)
        ttk.Label(header, text="参数表", style="Title.TLabel").pack(side=tk.LEFT)
        self.current_file_label = ttk.Label(header, text="未加载文件", style="Muted.TLabel")
        self.current_file_label.pack(side=tk.RIGHT)

        filter_row = ttk.Frame(parent)
        filter_row.pack(fill=tk.X, pady=(8, 8))
        self.param_search_entry = ttk.Entry(filter_row, textvariable=self.param_search_var)
        self.param_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(filter_row, text="清空", command=lambda: self.param_search_var.set("")).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Checkbutton(filter_row, text="只看勾选", variable=self.only_checked_var, command=self.refresh_param_table).pack(side=tk.LEFT, padx=(12, 0))
        self.param_search_var.trace_add("write", lambda *_: self.refresh_param_table())

        table_frame = ttk.Frame(parent)
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("apply", "key", "value", "comment", "line")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        self.table.heading("apply", text="批量")
        self.table.heading("key", text="参数名")
        self.table.heading("value", text="参数值")
        self.table.heading("comment", text="注释")
        self.table.heading("line", text="行号")
        self.table.column("apply", width=64, minwidth=52, anchor=tk.CENTER, stretch=False)
        self.table.column("key", width=260, minwidth=160, anchor=tk.W)
        self.table.column("value", width=300, minwidth=160, anchor=tk.W)
        self.table.column("comment", width=220, minwidth=120, anchor=tk.W)
        self.table.column("line", width=70, minwidth=60, anchor=tk.CENTER, stretch=False)
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.table.bind("<Button-1>", self.on_table_click)
        self.table.bind("<Double-1>", self.on_table_double_click)
        self.table.bind("<<TreeviewSelect>>", self.on_param_select)

        quick = ttk.Frame(parent)
        quick.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(quick, text="勾选全部", command=self.check_all_params).pack(side=tk.LEFT)
        ttk.Button(quick, text="取消勾选", command=self.uncheck_all_params).pack(side=tk.LEFT, padx=6)
        ttk.Button(quick, text="反选", command=self.invert_checked_params).pack(side=tk.LEFT)
        ttk.Button(quick, text="新增", command=self.add_param).pack(side=tk.LEFT, padx=(18, 6))
        ttk.Button(quick, text="编辑", command=self.edit_selected_param).pack(side=tk.LEFT)
        ttk.Button(quick, text="从表格移除", command=self.remove_selected_params).pack(side=tk.LEFT, padx=6)
        ttk.Button(quick, text="导出 CSV", command=self.export_params_csv).pack(side=tk.RIGHT)

    def build_action_panel(self, parent):
        ttk.Label(parent, text="操作", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="保存前可以先预览差异；自动备份默认开启。", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))

        buttons = [
            ("保存当前文件", self.save_current, "Accent.TButton"),
            ("另存为...", self.export_current_as, None),
            ("预览当前差异", self.preview_current_diff, None),
            ("重新载入当前文件", self.reload_current, None),
            ("批量应用勾选参数", self.apply_checked_to_selected_files, "Accent.TButton"),
            ("批量删除勾选参数", self.delete_checked_from_selected_files, "Danger.TButton"),
            ("批量导出到文件夹", self.export_selected_files_to_folder, None),
            ("生成参数对照表", self.show_compare_matrix, None),
        ]
        for text, command, style in buttons:
            ttk.Button(parent, text=text, command=command, style=style or "TButton").pack(fill=tk.X, pady=4)

        sep = ttk.Separator(parent)
        sep.pack(fill=tk.X, pady=14)

        ttk.Label(parent, text="当前选中参数", style="Title.TLabel").pack(anchor="w")
        form = ttk.Frame(parent)
        form.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(form, text="参数名").grid(row=0, column=0, sticky="w", pady=3)
        self.key_var = tk.StringVar()
        self.value_var = tk.StringVar()
        self.comment_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.key_var).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(form, text="参数值").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.value_var).grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(form, text="注释").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.comment_var, state="readonly").grid(row=5, column=0, sticky="ew")
        ttk.Button(form, text="应用到表格", command=self.apply_inspector_to_row).grid(row=6, column=0, sticky="ew", pady=(10, 0))
        form.columnconfigure(0, weight=1)

        sep2 = ttk.Separator(parent)
        sep2.pack(fill=tk.X, pady=14)
        ttk.Label(parent, text="键盘快捷键", style="Title.TLabel").pack(anchor="w")
        shortcuts = "Ctrl+O 打开文件夹\nCtrl+S 保存当前\nCtrl+F 搜索参数\nDelete 从表格移除\nF5 刷新文件"
        ttk.Label(parent, text=shortcuts, style="Muted.TLabel", justify=tk.LEFT).pack(anchor="w", pady=(6, 0))

    def bind_shortcuts(self):
        self.root.bind("<Control-o>", lambda _event: self.open_folder())
        self.root.bind("<Control-s>", lambda _event: self.save_current())
        self.root.bind("<Control-f>", lambda _event: self.focus_param_search())
        self.root.bind("<Delete>", lambda _event: self.remove_selected_params())
        self.root.bind("<F5>", lambda _event: self.refresh_files())

    def focus_param_search(self):
        self.param_search_entry.focus_set()
        self.param_search_entry.select_range(0, tk.END)

    def set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def mark_dirty(self, dirty=True):
        self.dirty = dirty
        suffix = "*" if dirty else ""
        if self.current_file:
            self.current_file_label.configure(text=f"{self.current_file.name}{suffix}")

    def open_folder(self):
        folder = filedialog.askdirectory(title="选择包含 .SPIN 文件的文件夹")
        if not folder:
            return
        self.folder = Path(folder)
        self.refresh_files()

    def open_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 .SPIN 文件",
            filetypes=[("SPIN files", "*.spin *.SPIN"), ("All files", "*.*")],
        )
        if not paths:
            return
        self.folder = Path(paths[0]).parent
        existing = {Path(p).resolve() for p in self.files}
        for path in paths:
            p = Path(path).resolve()
            if p not in existing:
                self.files.append(p)
        self.files.sort(key=lambda p: str(p).lower())
        self.refresh_file_list()
        self.set_status(f"已添加 {len(paths)} 个文件。")

    def refresh_files(self):
        if not self.folder:
            return
        pattern = "**/*.spin" if self.recursive_var.get() else "*.spin"
        self.files = sorted(self.folder.glob(pattern), key=lambda p: str(p).lower())
        self.refresh_file_list()
        self.set_status(f"发现 {len(self.files)} 个 .SPIN 文件。")

    def refresh_file_list(self):
        query = self.file_search_var.get().strip().lower()
        selected_paths = set(self.get_selected_files())
        self.file_list.delete(0, tk.END)
        self.display_files = []
        for path in self.files:
            text = path.name if not self.folder else str(path.relative_to(self.folder))
            if query and query not in text.lower():
                continue
            self.display_files.append(path)
            self.file_list.insert(tk.END, text)
            if path in selected_paths:
                self.file_list.select_set(tk.END)

    def get_selected_files(self):
        return [self.display_files[i] for i in self.file_list.curselection()] if hasattr(self, "display_files") else []

    def select_all_files(self):
        self.file_list.select_set(0, tk.END)

    def clear_file_selection(self):
        self.file_list.select_clear(0, tk.END)

    def on_file_select(self, _event=None):
        selected = self.get_selected_files()
        if len(selected) == 1:
            if self.dirty and not messagebox.askyesno(APP_TITLE, "当前表格有未保存修改，仍然切换文件吗？"):
                return
            self.load_file(selected[0])
        else:
            self.current_file_label.configure(text=f"已选择 {len(selected)} 个文件")

    def load_file(self, path):
        try:
            doc = SpinParser.parse(path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"读取失败：\n{path}\n\n{exc}")
            return

        self.current_doc = doc
        self.current_file = doc.path
        self.param_rows.clear()
        for key, meta in doc.params.items():
            self.param_rows[key] = {
                "checked": False,
                "key": key,
                "value": meta["value"],
                "comment": meta["comment"],
                "line": meta["line_no"],
            }
        self.refresh_param_table()
        self.mark_dirty(False)
        self.set_status(f"已加载 {doc.path.name}，参数 {len(self.param_rows)} 个，编码 {doc.encoding}。")

    def refresh_param_table(self):
        self.table.delete(*self.table.get_children())
        query = self.param_search_var.get().strip().lower()
        only_checked = self.only_checked_var.get()
        self.visible_param_iids = []
        for key, row in self.param_rows.items():
            text = " ".join([row["key"], row["value"], row["comment"]]).lower()
            if query and query not in text:
                continue
            if only_checked and not row["checked"]:
                continue
            iid = row["key"]
            values = (
                CHECKED if row["checked"] else UNCHECKED,
                row["key"],
                row["value"],
                row["comment"],
                row["line"] or "",
            )
            self.table.insert("", tk.END, iid=iid, values=values)
            self.visible_param_iids.append(iid)

    def on_table_click(self, event):
        region = self.table.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.table.identify_row(event.y)
        col_id = self.table.identify_column(event.x)
        if row_id and col_id == "#1":
            self.toggle_param(row_id)
            return "break"

    def on_table_double_click(self, event):
        region = self.table.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.table.identify_row(event.y)
        col_id = self.table.identify_column(event.x)
        if not row_id:
            return
        if col_id in ("#2", "#3"):
            column = "key" if col_id == "#2" else "value"
            self.inline_edit(row_id, column)

    def inline_edit(self, row_id, column):
        bbox = self.table.bbox(row_id, column)
        if not bbox:
            return
        x, y, width, height = bbox
        old_value = self.table.set(row_id, column)
        entry = ttk.Entry(self.table)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, old_value)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def save(_event=None):
            new_value = entry.get().strip()
            entry.destroy()
            if column == "key":
                self.rename_param(row_id, new_value)
            else:
                self.set_param_value(row_id, new_value)

        entry.bind("<Return>", save)
        entry.bind("<FocusOut>", save)
        entry.bind("<Escape>", lambda _event: entry.destroy())

    def toggle_param(self, key):
        if key in self.param_rows:
            self.param_rows[key]["checked"] = not self.param_rows[key]["checked"]
            self.refresh_param_table()

    def on_param_select(self, _event=None):
        selected = self.table.selection()
        if len(selected) != 1:
            self.key_var.set("")
            self.value_var.set("")
            self.comment_var.set("")
            return
        row = self.param_rows.get(selected[0])
        if row:
            self.key_var.set(row["key"])
            self.value_var.set(row["value"])
            self.comment_var.set(row["comment"])

    def rename_param(self, old_key, new_key):
        new_key = new_key.strip()
        if not new_key or old_key not in self.param_rows:
            return
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", new_key):
            messagebox.showwarning(APP_TITLE, "参数名只能包含字母、数字、下划线、点和短横线。")
            self.refresh_param_table()
            return
        if new_key != old_key and new_key in self.param_rows:
            messagebox.showwarning(APP_TITLE, f"参数名 {new_key} 已存在。")
            self.refresh_param_table()
            return
        original_rows = list(self.param_rows.items())
        row = self.param_rows[old_key]
        row["key"] = new_key
        updated = OrderedDict()
        for key, value in original_rows:
            if key == old_key:
                updated[new_key] = row
            else:
                updated[key] = value
        self.param_rows = updated
        self.mark_dirty()
        self.refresh_param_table()

    def set_param_value(self, key, value):
        if key in self.param_rows:
            self.param_rows[key]["value"] = value
            self.mark_dirty()
            self.refresh_param_table()

    def apply_inspector_to_row(self):
        selected = self.table.selection()
        if len(selected) != 1:
            messagebox.showinfo(APP_TITLE, "请先选择一个参数。")
            return
        old_key = selected[0]
        new_key = self.key_var.get().strip()
        new_value = self.value_var.get().strip()
        self.rename_param(old_key, new_key)
        self.set_param_value(new_key, new_value)

    def check_all_params(self):
        for key in self.visible_param_iids or self.param_rows.keys():
            self.param_rows[key]["checked"] = True
        self.refresh_param_table()

    def uncheck_all_params(self):
        for row in self.param_rows.values():
            row["checked"] = False
        self.refresh_param_table()

    def invert_checked_params(self):
        for key in self.visible_param_iids or self.param_rows.keys():
            self.param_rows[key]["checked"] = not self.param_rows[key]["checked"]
        self.refresh_param_table()

    def add_param(self):
        dialog = AddParamDialog(self.root)
        if not dialog.result:
            return
        key, value = dialog.result
        if key in self.param_rows:
            messagebox.showwarning(APP_TITLE, f"参数名 {key} 已存在。")
            return
        self.param_rows[key] = {
            "checked": False,
            "key": key,
            "value": value,
            "comment": "",
            "line": "",
        }
        self.mark_dirty()
        self.refresh_param_table()

    def edit_selected_param(self):
        selected = self.table.selection()
        if len(selected) != 1:
            messagebox.showinfo(APP_TITLE, "请先选择一个参数。")
            return
        row = self.param_rows[selected[0]]
        dialog = AddParamDialog(self.root, title="编辑参数", key=row["key"], value=row["value"])
        if not dialog.result:
            return
        new_key, new_value = dialog.result
        self.rename_param(selected[0], new_key)
        self.set_param_value(new_key, new_value)

    def remove_selected_params(self):
        selected = list(self.table.selection())
        if not selected:
            return
        if not messagebox.askyesno(APP_TITLE, f"确定从表格移除 {len(selected)} 个参数吗？保存后才会写入磁盘。"):
            return
        for key in selected:
            self.param_rows.pop(key, None)
        self.mark_dirty()
        self.refresh_param_table()

    def collect_all_params(self):
        return OrderedDict((row["key"], row["value"]) for row in self.param_rows.values())

    def collect_checked_params(self):
        return OrderedDict((row["key"], row["value"]) for row in self.param_rows.values() if row["checked"])

    def collect_checked_keys(self):
        return {row["key"] for row in self.param_rows.values() if row["checked"]}

    def deleted_original_keys(self):
        if not self.current_doc:
            return set()
        original_keys = {item.key.strip() for item in self.current_doc.line_info if isinstance(item, ParamLine)}
        current_keys = set(self.param_rows.keys())
        return original_keys - current_keys

    def save_current(self):
        if not self.current_doc:
            messagebox.showinfo(APP_TITLE, "请先打开一个 .SPIN 文件。")
            return
        try:
            text = SpinParser.render(self.current_doc, self.collect_all_params(), delete_keys=self.deleted_original_keys())
            SpinParser.write(
                self.current_doc.path,
                text,
                encoding=self.current_doc.encoding,
                backup=self.autobackup_var.get(),
            )
            self.load_file(self.current_doc.path)
            self.set_status(f"已保存 {self.current_doc.path.name}。")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"保存失败：\n{exc}")

    def export_current_as(self):
        if not self.current_doc:
            messagebox.showinfo(APP_TITLE, "请先打开一个 .SPIN 文件。")
            return
        out_path = filedialog.asksaveasfilename(
            title="另存为",
            defaultextension=".SPIN",
            filetypes=[("SPIN files", "*.SPIN"), ("All files", "*.*")],
        )
        if not out_path:
            return
        try:
            text = SpinParser.render(self.current_doc, self.collect_all_params(), delete_keys=self.deleted_original_keys())
            SpinParser.write(out_path, text, encoding=self.current_doc.encoding, backup=False)
            self.set_status(f"已导出 {out_path}。")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出失败：\n{exc}")

    def reload_current(self):
        if self.current_doc:
            self.load_file(self.current_doc.path)

    def preview_current_diff(self):
        if not self.current_doc:
            messagebox.showinfo(APP_TITLE, "请先打开一个 .SPIN 文件。")
            return
        old_text, _encoding = SpinParser.read_text(self.current_doc.path)
        new_text = SpinParser.render(self.current_doc, self.collect_all_params(), delete_keys=self.deleted_original_keys())
        self.show_diff_window(old_text, new_text, self.current_doc.path.name)

    def show_diff_window(self, old_text, new_text, title):
        win = tk.Toplevel(self.root)
        win.title(f"差异预览 - {title}")
        win.geometry("980x640")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(frame, wrap=tk.NONE, font=("Consolas", 10), bg="#0f172a", fg="#e5e7eb", insertbackground="#e5e7eb")
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        diff = difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile="原文件",
            tofile="修改后",
            lineterm="",
        )
        content = "\n".join(diff) or "没有差异。"
        text.insert("1.0", content)
        text.tag_configure("add", foreground="#86efac")
        text.tag_configure("del", foreground="#fca5a5")
        text.tag_configure("hunk", foreground="#93c5fd")
        for index, line in enumerate(content.splitlines(), start=1):
            tag = None
            if line.startswith("+") and not line.startswith("+++"):
                tag = "add"
            elif line.startswith("-") and not line.startswith("---"):
                tag = "del"
            elif line.startswith("@@"):
                tag = "hunk"
            if tag:
                text.tag_add(tag, f"{index}.0", f"{index}.end")
        text.configure(state=tk.DISABLED)

    def apply_checked_to_selected_files(self):
        targets = self.get_selected_files()
        checked = self.collect_checked_params()
        if not targets:
            messagebox.showinfo(APP_TITLE, "请先在左侧选择要批量处理的文件。")
            return
        if not checked:
            messagebox.showinfo(APP_TITLE, "请先在参数表中勾选需要批量应用的参数。")
            return
        if not messagebox.askyesno(APP_TITLE, f"确定将 {len(checked)} 个参数应用到 {len(targets)} 个文件吗？"):
            return
        ok, fail = self.batch_update(targets, checked_params=checked)
        self.report_batch_result("批量应用", ok, fail)

    def delete_checked_from_selected_files(self):
        targets = self.get_selected_files()
        keys = self.collect_checked_keys()
        if not targets:
            messagebox.showinfo(APP_TITLE, "请先在左侧选择要批量处理的文件。")
            return
        if not keys:
            messagebox.showinfo(APP_TITLE, "请先在参数表中勾选需要批量删除的参数。")
            return
        sample = ", ".join(sorted(keys)[:12])
        if len(keys) > 12:
            sample += " ..."
        if not messagebox.askyesno(APP_TITLE, f"确定从 {len(targets)} 个文件中删除这些参数吗？\n\n{sample}"):
            return
        ok, fail = self.batch_update(targets, delete_keys=keys)
        self.report_batch_result("批量删除", ok, fail)

    def export_selected_files_to_folder(self):
        targets = self.get_selected_files()
        checked = self.collect_checked_params()
        if not targets:
            messagebox.showinfo(APP_TITLE, "请先在左侧选择要导出的文件。")
            return
        if not checked:
            messagebox.showinfo(APP_TITLE, "请先勾选要写入导出文件的参数。")
            return
        folder = filedialog.askdirectory(title="选择导出目标文件夹")
        if not folder:
            return
        ok, fail = self.batch_update(targets, checked_params=checked, export_folder=Path(folder))
        self.report_batch_result("批量导出", ok, fail)

    def batch_update(self, targets, checked_params=None, delete_keys=None, export_folder=None):
        checked_params = OrderedDict(checked_params or {})
        delete_keys = set(delete_keys or [])
        ok = 0
        fail = []
        backup_dir = None
        if self.autobackup_var.get() and not export_folder:
            backup_dir = (self.folder or Path(targets[0]).parent) / "_spin_backups"

        for path in targets:
            try:
                doc = SpinParser.parse(path)
                params = OrderedDict((key, meta["value"]) for key, meta in doc.params.items())
                for key in delete_keys:
                    params.pop(key, None)
                params.update(checked_params)
                out_text = SpinParser.render(doc, params, delete_keys=delete_keys)
                out_path = Path(export_folder) / Path(path).name if export_folder else path
                SpinParser.write(out_path, out_text, encoding=doc.encoding, backup=not export_folder and self.autobackup_var.get(), backup_dir=backup_dir)
                ok += 1
            except Exception as exc:
                fail.append((Path(path).name, str(exc)))
        return ok, fail

    def report_batch_result(self, action, ok, fail):
        self.set_status(f"{action}完成：成功 {ok} 个，失败 {len(fail)} 个。")
        if fail:
            details = "\n".join(f"{name}: {err}" for name, err in fail[:10])
            messagebox.showwarning(APP_TITLE, f"{action}完成，但部分文件失败：\n\n{details}")
        else:
            messagebox.showinfo(APP_TITLE, f"{action}完成：成功处理 {ok} 个文件。")
        if self.current_doc:
            self.reload_current()

    def export_params_csv(self):
        if not self.param_rows:
            messagebox.showinfo(APP_TITLE, "当前没有可导出的参数。")
            return
        out_path = filedialog.asksaveasfilename(
            title="导出参数表 CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not out_path:
            return
        try:
            with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["checked", "key", "value", "comment", "line"])
                for row in self.param_rows.values():
                    writer.writerow([row["checked"], row["key"], row["value"], row["comment"], row["line"]])
            self.set_status(f"已导出参数 CSV：{out_path}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出 CSV 失败：\n{exc}")

    def export_file_index(self):
        if not getattr(self, "display_files", None):
            messagebox.showinfo(APP_TITLE, "当前没有文件清单。")
            return
        out_path = filedialog.asksaveasfilename(
            title="导出文件清单 CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not out_path:
            return
        try:
            with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["file", "full_path", "size_bytes", "modified_time"])
                for path in self.display_files:
                    stat = path.stat()
                    writer.writerow([path.name, str(path), stat.st_size, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))])
            self.set_status(f"已导出文件清单：{out_path}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出文件清单失败：\n{exc}")

    def show_compare_matrix(self):
        targets = self.get_selected_files()
        if not targets:
            messagebox.showinfo(APP_TITLE, "请先在左侧选择要对照的文件。")
            return
        rows = OrderedDict()
        file_names = [Path(p).name for p in targets]
        try:
            for path in targets:
                doc = SpinParser.parse(path)
                for key, meta in doc.params.items():
                    rows.setdefault(key, {})[Path(path).name] = meta["value"]
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"生成对照表失败：\n{exc}")
            return

        win = tk.Toplevel(self.root)
        win.title("参数对照表")
        win.geometry("1100x620")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(toolbar, text=f"{len(targets)} 个文件，{len(rows)} 个参数", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Button(toolbar, text="导出 CSV", command=lambda: self.export_matrix_csv(rows, file_names)).pack(side=tk.RIGHT)

        tree = ttk.Treeview(frame, columns=["key"] + file_names, show="headings")
        tree.heading("key", text="参数名")
        tree.column("key", width=220, minwidth=160)
        for name in file_names:
            tree.heading(name, text=name)
            tree.column(name, width=180, minwidth=120)
        yscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)

        for key, value_map in rows.items():
            tree.insert("", tk.END, values=[key] + [value_map.get(name, "") for name in file_names])

    def export_matrix_csv(self, rows, file_names):
        out_path = filedialog.asksaveasfilename(
            title="导出参数对照表 CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not out_path:
            return
        try:
            with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["key"] + file_names)
                for key, value_map in rows.items():
                    writer.writerow([key] + [value_map.get(name, "") for name in file_names])
            self.set_status(f"已导出参数对照表：{out_path}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出参数对照表失败：\n{exc}")

    def show_help(self):
        guide_path = Path(__file__).with_name("SPIN_Editor_User_Guide.md")
        message = (
            "基本流程：\n"
            "1. 打开包含 .SPIN 文件的文件夹。\n"
            "2. 左侧选择一个文件查看和编辑参数。\n"
            "3. 在参数表勾选需要批量处理的参数。\n"
            "4. 保存当前文件，或对左侧多选文件执行批量应用/删除/导出。\n\n"
            f"完整说明见：\n{guide_path}"
        )
        messagebox.showinfo(APP_TITLE, message)


def main():
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.1)
    except tk.TclError:
        pass
    app = SpinEditorPro(root)
    root.protocol("WM_DELETE_WINDOW", lambda: on_close(root, app))
    root.mainloop()


def on_close(root, app):
    if app.dirty and not messagebox.askyesno(APP_TITLE, "当前表格有未保存修改，确定退出吗？"):
        return
    root.destroy()


if __name__ == "__main__":
    main()
