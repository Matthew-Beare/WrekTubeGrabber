import json
import queue
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "WrekTube Grabber"
BASE_DIR = Path(r"D:/hifi")
DEFAULT_INCOMING_DIR = BASE_DIR / "incoming"
SETTINGS_FILE = BASE_DIR / "yt_dlp_gui_settings.json"
LOG_FILE = BASE_DIR / "yt_dlp_gui_history.json"
YT_DLP_EXE = "yt-dlp"

SINGLE_SUBPATH = r"%(artist,uploader)s/%(title)s.%(ext)s"
PLAYLIST_SUBPATH = r"%(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s"

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")

# Dark theme colors
BG = "#121417"
PANEL = "#1B1F24"
PANEL_ALT = "#20252B"
BORDER = "#2B3139"
TEXT = "#E8EDF2"
TEXT_MUTED = "#9AA7B4"
ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"
ENTRY_BG = "#0F1317"
TREE_BG = "#161A20"
TREE_SEL = "#2D5BFF"


@dataclass
class DownloadRecord:
    url: str
    mode: str
    status: str
    detail: str


class DownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1340x860")
        self.root.minsize(1100, 700)
        self.root.configure(bg=BG)

        self.msg_queue = queue.Queue()
        self.history = self.load_history()
        self.settings = self.load_settings()

        self.active_jobs = 0
        self.job_counter = 0
        self.current_rows = {}
        self.job_processes = {}
        self.row_to_job = {}
        self.stopped_jobs = set()

        DEFAULT_INCOMING_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="auto")
        self.save_dir_var = tk.StringVar(
            value=self.settings.get("save_dir", str(DEFAULT_INCOMING_DIR))
        )
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="0%")

        self.setup_dark_theme()
        self.build_ui()
        self.populate_history()

        self.root.after(120, self.process_queue)

    def setup_dark_theme(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=BG, foreground=TEXT, fieldbackground=ENTRY_BG)

        style.configure("App.TFrame", background=BG)

        style.configure(
            "App.TLabel",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Muted.TLabel",
            background=BG,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Title.TLabel",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI", 22, "bold")
        )
        style.configure(
            "Subtitle.TLabel",
            background=BG,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 11)
        )
        style.configure(
            "SidebarTitle.TLabel",
            background=PANEL,
            foreground=TEXT,
            font=("Segoe UI", 18, "bold")
        )
        style.configure(
            "SidebarMuted.TLabel",
            background=PANEL,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 10)
        )

        style.configure(
            "App.TLabelframe",
            background=BG,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            borderwidth=1,
            relief="solid"
        )
        style.configure(
            "App.TLabelframe.Label",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI", 10, "bold")
        )

        style.configure(
            "App.TButton",
            background=PANEL_ALT,
            foreground=TEXT,
            bordercolor=BORDER,
            focusthickness=0,
            focuscolor=PANEL_ALT,
            padding=(12, 8),
            font=("Segoe UI", 10)
        )
        style.map(
            "App.TButton",
            background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
            foreground=[("active", TEXT), ("pressed", TEXT)]
        )

        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground=TEXT,
            bordercolor=ACCENT,
            focusthickness=0,
            focuscolor=ACCENT,
            padding=(14, 8),
            font=("Segoe UI", 10, "bold")
        )
        style.map(
            "Primary.TButton",
            background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)]
        )

        style.configure(
            "Danger.TButton",
            background="#7F1D1D",
            foreground=TEXT,
            bordercolor="#991B1B",
            focusthickness=0,
            focuscolor="#991B1B",
            padding=(12, 8),
            font=("Segoe UI", 10, "bold")
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#991B1B"), ("pressed", "#991B1B")]
        )

        style.configure(
            "App.TRadiobutton",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI", 10)
        )
        style.map(
            "App.TRadiobutton",
            foreground=[("active", TEXT)],
            background=[("active", BG)]
        )

        style.configure(
            "App.TEntry",
            fieldbackground=ENTRY_BG,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=6
        )

        style.configure(
            "App.Treeview",
            background=TREE_BG,
            fieldbackground=TREE_BG,
            foreground=TEXT,
            bordercolor=BORDER,
            rowheight=30,
            font=("Segoe UI", 10)
        )
        style.map(
            "App.Treeview",
            background=[("selected", TREE_SEL)],
            foreground=[("selected", "#FFFFFF")]
        )
        style.configure(
            "App.Treeview.Heading",
            background=PANEL_ALT,
            foreground=TEXT,
            bordercolor=BORDER,
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padding=(8, 8)
        )
        style.map(
            "App.Treeview.Heading",
            background=[("active", "#2A313A")]
        )

        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=ENTRY_BG,
            background=ACCENT,
            bordercolor=BORDER,
            lightcolor=ACCENT,
            darkcolor=ACCENT
        )

    def build_ui(self):
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        self.app_canvas = tk.Canvas(
            shell,
            bg=BG,
            highlightthickness=0,
            bd=0
        )
        self.app_canvas.pack(side="left", fill="both", expand=True)

        shell_scrollbar = ttk.Scrollbar(
            shell,
            orient="vertical",
            command=self.app_canvas.yview
        )
        shell_scrollbar.pack(side="right", fill="y")

        self.app_canvas.configure(yscrollcommand=shell_scrollbar.set)

        self.scrollable_frame = ttk.Frame(self.app_canvas, style="App.TFrame", padding=16)
        self.canvas_window = self.app_canvas.create_window(
            (0, 0),
            window=self.scrollable_frame,
            anchor="nw"
        )

        self.scrollable_frame.bind("<Configure>", self.on_frame_configure)
        self.app_canvas.bind("<Configure>", self.on_canvas_configure)

        self.bind_mousewheel(self.root)

        outer = self.scrollable_frame
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        sidebar = tk.Frame(
            outer,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1,
            width=280
        )
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        sidebar.grid_propagate(False)

        sidebar_inner = tk.Frame(sidebar, bg=PANEL)
        sidebar_inner.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(
            sidebar_inner,
            text=APP_TITLE,
            style="SidebarTitle.TLabel"
        ).pack(anchor="w")

        ttk.Label(
            sidebar_inner,
            text="YouTube audio snatching tool.",
            style="SidebarMuted.TLabel",
            justify="left"
        ).pack(anchor="w", pady=(8, 0))

        main = ttk.Frame(outer, style="App.TFrame")
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)

        ttk.Label(main, text=APP_TITLE, style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            main,
            text="Dark mode saves lives.",
            style="Subtitle.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        controls = ttk.LabelFrame(
            main,
            text="New Download",
            style="App.TLabelframe",
            padding=12
        )
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        controls.columnconfigure(0, weight=1)

        ttk.Label(controls, text="URL", style="App.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        self.url_entry = ttk.Entry(
            controls,
            textvariable=self.url_var,
            style="App.TEntry"
        )
        self.url_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 12))
        self.url_entry.bind("<Return>", self.handle_submit)
        self.make_entry_context_menu(self.url_entry)

        ttk.Label(controls, text="Save Folder", style="App.TLabel").grid(
            row=2, column=0, sticky="w"
        )

        save_frame = ttk.Frame(controls, style="App.TFrame")
        save_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 12))
        save_frame.columnconfigure(0, weight=1)

        self.save_dir_entry = ttk.Entry(
            save_frame,
            textvariable=self.save_dir_var,
            style="App.TEntry"
        )
        self.save_dir_entry.grid(row=0, column=0, sticky="ew")
        self.make_entry_context_menu(self.save_dir_entry)

        ttk.Button(
            save_frame,
            text="Browse",
            command=self.choose_folder,
            style="App.TButton"
        ).grid(row=0, column=1, padx=(10, 0))

        bottom_controls = ttk.Frame(controls, style="App.TFrame")
        bottom_controls.grid(row=4, column=0, columnspan=4, sticky="ew")
        bottom_controls.columnconfigure(0, weight=1)
        bottom_controls.columnconfigure(1, weight=0)

        left_mode = ttk.Frame(bottom_controls, style="App.TFrame")
        left_mode.grid(row=0, column=0, sticky="w")

        ttk.Label(left_mode, text="Mode", style="App.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 16)
        )

        for i, (label, value) in enumerate([
            ("Auto", "auto"),
            ("Single", "single"),
            ("Playlist", "playlist"),
        ]):
            ttk.Radiobutton(
                left_mode,
                text=label,
                value=value,
                variable=self.mode_var,
                style="App.TRadiobutton"
            ).grid(row=0, column=i + 1, padx=(0, 14), sticky="w")

        right_buttons = ttk.Frame(bottom_controls, style="App.TFrame")
        right_buttons.grid(row=0, column=1, sticky="e")

        ttk.Button(
            right_buttons,
            text="Open Save Folder",
            command=self.open_folder,
            style="App.TButton"
        ).grid(row=0, column=0, padx=(0, 10))

        ttk.Button(
            right_buttons,
            text="Download",
            command=self.handle_submit,
            style="Primary.TButton"
        ).grid(row=0, column=1)

        current_frame = ttk.LabelFrame(
            main,
            text="Current Downloads",
            style="App.TLabelframe",
            padding=10
        )
        current_frame.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        current_frame.columnconfigure(0, weight=1)

        current_buttons = ttk.Frame(current_frame, style="App.TFrame")
        current_buttons.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ttk.Button(
            current_buttons,
            text="Stop Selected",
            command=self.stop_selected_downloads,
            style="Danger.TButton"
        ).grid(row=0, column=0)

        self.current_tree = self.make_tree(current_frame, height=6)
        self.current_tree.grid(row=1, column=0, sticky="ew")
        self.add_tree_scrollbar(current_frame, self.current_tree, row=1)

        history_frame = ttk.LabelFrame(
            main,
            text="Download History",
            style="App.TLabelframe",
            padding=10
        )
        history_frame.grid(row=4, column=0, sticky="ew", pady=(0, 14))
        history_frame.columnconfigure(0, weight=1)

        history_buttons = ttk.Frame(history_frame, style="App.TFrame")
        history_buttons.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ttk.Button(
            history_buttons,
            text="Clear Finished",
            command=self.clear_finished_history,
            style="App.TButton"
        ).grid(row=0, column=0, padx=(0, 8))

        ttk.Button(
            history_buttons,
            text="Clear Selected",
            command=self.clear_selected_history,
            style="App.TButton"
        ).grid(row=0, column=1, padx=(0, 8))

        ttk.Button(
            history_buttons,
            text="Clear All History",
            command=self.clear_all_history,
            style="App.TButton"
        ).grid(row=0, column=2)

        self.history_tree = self.make_tree(history_frame, height=10)
        self.history_tree.grid(row=1, column=0, sticky="ew")
        self.add_tree_scrollbar(history_frame, self.history_tree, row=1)

        status_card = tk.Frame(
            main,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        status_card.grid(row=5, column=0, sticky="ew")
        status_card.columnconfigure(0, weight=1)

        tk.Label(
            status_card,
            textvariable=self.status_var,
            bg=PANEL,
            fg=TEXT,
            anchor="w",
            font=("Segoe UI", 10)
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))

        progress_row = tk.Frame(status_card, bg=PANEL)
        progress_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        progress_row.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(
            progress_row,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
            style="App.Horizontal.TProgressbar"
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")

        tk.Label(
            progress_row,
            textvariable=self.progress_text_var,
            bg=PANEL,
            fg=TEXT_MUTED,
            width=6,
            anchor="e",
            font=("Segoe UI", 10, "bold")
        ).grid(row=0, column=1, padx=(10, 0))

        self.url_entry.focus_set()

    def make_entry_context_menu(self, widget):
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=PANEL_ALT,
            fg=TEXT,
            activebackground=ACCENT_HOVER,
            activeforeground=TEXT
        )
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self.select_all_in_entry(widget))

        def show_menu(event):
            try:
                widget.focus_set()
                insert_index = widget.index(f"@{event.x}")
                widget.icursor(insert_index)
            except Exception:
                pass
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_menu)

    def select_all_in_entry(self, widget):
        widget.focus_set()
        try:
            widget.select_range(0, "end")
            widget.icursor("end")
        except Exception:
            pass

    def on_frame_configure(self, event=None):
        self.app_canvas.configure(scrollregion=self.app_canvas.bbox("all"))

    def on_canvas_configure(self, event):
        self.app_canvas.itemconfig(self.canvas_window, width=event.width)

    def bind_mousewheel(self, widget):
        widget.bind_all("<MouseWheel>", self.on_mousewheel)
        widget.bind_all("<Button-4>", self.on_mousewheel)
        widget.bind_all("<Button-5>", self.on_mousewheel)

    def on_mousewheel(self, event):
        if event.num == 4:
            self.app_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.app_canvas.yview_scroll(1, "units")
        else:
            self.app_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def make_tree(self, parent, height: int):
        columns = ("status", "mode", "url", "detail")

        tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            height=height,
            selectmode="extended",
            style="App.Treeview"
        )

        tree.heading("status", text="Status")
        tree.heading("mode", text="Mode")
        tree.heading("url", text="URL")
        tree.heading("detail", text="Detail")

        tree.column("status", width=120, anchor="center")
        tree.column("mode", width=100, anchor="center")
        tree.column("url", width=430)
        tree.column("detail", width=420)

        return tree

    def add_tree_scrollbar(self, parent, tree, row=0):
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=row, column=1, sticky="ns", padx=(8, 0))

    def load_settings(self):
        if SETTINGS_FILE.exists():
            try:
                return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"save_dir": str(DEFAULT_INCOMING_DIR)}

    def save_settings(self):
        SETTINGS_FILE.write_text(
            json.dumps({"save_dir": self.save_dir_var.get()}, indent=2),
            encoding="utf-8"
        )

    def load_history(self):
        if LOG_FILE.exists():
            try:
                return json.loads(LOG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def save_history(self):
        LOG_FILE.write_text(
            json.dumps(self.history, indent=2),
            encoding="utf-8"
        )

    def populate_history(self):
        for item in reversed(self.history):
            self.history_tree.insert(
                "",
                0,
                values=(
                    item["status"],
                    item["mode"],
                    item["url"],
                    item["detail"]
                )
            )

    def refresh_history_tree(self):
        for item_id in self.history_tree.get_children():
            self.history_tree.delete(item_id)
        self.populate_history()

    def add_history(self, record: DownloadRecord):
        row = {
            "status": record.status,
            "mode": record.mode,
            "url": record.url,
            "detail": record.detail,
        }

        self.history.append(row)
        self.save_history()

        self.history_tree.insert(
            "",
            0,
            values=(
                row["status"],
                row["mode"],
                row["url"],
                row["detail"]
            )
        )

    def clear_finished_history(self):
        original_count = len(self.history)
        self.history = [
            item for item in self.history
            if item.get("status") != "Done"
        ]
        removed = original_count - len(self.history)
        self.save_history()
        self.refresh_history_tree()
        self.status_var.set(
            f"Cleared {removed} finished entr{'y' if removed == 1 else 'ies'}"
        )

    def clear_selected_history(self):
        selected = self.history_tree.selection()
        if not selected:
            self.status_var.set("No history entries selected")
            return

        selected_values = [
            self.history_tree.item(item_id, "values")
            for item_id in selected
        ]

        def matches(history_item, tree_values):
            return (
                history_item.get("status") == tree_values[0]
                and history_item.get("mode") == tree_values[1]
                and history_item.get("url") == tree_values[2]
                and history_item.get("detail") == tree_values[3]
            )

        new_history = []
        removed_count = 0
        remaining_selected = list(selected_values)

        for history_item in self.history:
            match_index = None
            for idx, values in enumerate(remaining_selected):
                if matches(history_item, values):
                    match_index = idx
                    break

            if match_index is not None:
                removed_count += 1
                remaining_selected.pop(match_index)
            else:
                new_history.append(history_item)

        self.history = new_history
        self.save_history()
        self.refresh_history_tree()
        self.status_var.set(
            f"Cleared {removed_count} selected entr{'y' if removed_count == 1 else 'ies'}"
        )

    def clear_all_history(self):
        count = len(self.history)
        self.history = []
        self.save_history()
        self.refresh_history_tree()
        self.status_var.set(
            f"Cleared all history ({count} entr{'y' if count == 1 else 'ies'})"
        )

    def choose_folder(self):
        folder = filedialog.askdirectory(
            initialdir=self.save_dir_var.get()
        )
        if folder:
            self.save_dir_var.set(folder)
            self.save_settings()

    def open_folder(self):
        folder = Path(self.save_dir_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(folder)])

    def validate_folder(self):
        try:
            folder = Path(self.save_dir_var.get())
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        except Exception as exc:
            messagebox.showerror(
                "Bad Save Folder",
                f"Could not use save folder:\n{exc}"
            )
            return None

    def detect_mode(self, url: str):
        if "list=" in url.lower():
            return "playlist"
        return "single"

    def output_template(self, folder: Path, mode: str):
        if mode == "playlist":
            return str(folder / PLAYLIST_SUBPATH)
        return str(folder / SINGLE_SUBPATH)

    def stop_selected_downloads(self):
        selected_rows = self.current_tree.selection()
        if not selected_rows:
            self.status_var.set("No active downloads selected")
            return

        stopped_count = 0

        for row_id in selected_rows:
            job_id = self.row_to_job.get(row_id)
            if not job_id:
                continue

            process = self.job_processes.get(job_id)
            if process and process.poll() is None:
                self.stopped_jobs.add(job_id)
                try:
                    process.terminate()
                    stopped_count += 1
                except Exception:
                    try:
                        process.kill()
                        stopped_count += 1
                    except Exception:
                        pass

        if stopped_count == 0:
            self.status_var.set("Selected downloads were already finished or unavailable")
        else:
            self.status_var.set(f"Stopping {stopped_count} download{'s' if stopped_count != 1 else ''}...")

    def handle_submit(self, event=None):
        url = self.url_var.get().strip()

        if not url:
            return

        if not URL_RE.match(url):
            messagebox.showerror(
                "Bad URL",
                "Paste a full http or https URL."
            )
            return

        folder = self.validate_folder()
        if not folder:
            return

        self.save_settings()

        mode = self.mode_var.get()
        if mode == "auto":
            mode = self.detect_mode(url)

        self.url_var.set("")

        self.job_counter += 1
        self.active_jobs += 1
        job_id = f"job-{self.job_counter}"

        self.progress_var.set(0.0)
        self.progress_text_var.set("0%")

        row_id = self.current_tree.insert(
            "",
            0,
            values=("Queued", mode, url, "Waiting to start")
        )

        self.current_rows[job_id] = row_id
        self.row_to_job[row_id] = job_id
        self.update_status()

        thread = threading.Thread(
            target=self.download_worker,
            args=(job_id, url, mode, folder),
            daemon=True
        )
        thread.start()

    def download_worker(self, job_id: str, url: str, mode: str, folder: Path):
        process = None
        try:
            self.msg_queue.put(
                ("progress", job_id, DownloadRecord(
                    url, mode, "Downloading", "Starting yt-dlp..."
                ))
            )

            cmd = [
                YT_DLP_EXE,
                "--newline",
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", "m4a",
                "--embed-metadata",
                "--embed-thumbnail",
                "-o", self.output_template(folder, mode),
                url
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.job_processes[job_id] = process

            last_detail = "Talking to yt-dlp..."
            last_percent = 0.0

            for raw_line in process.stdout:
                if job_id in self.stopped_jobs:
                    break

                line = raw_line.strip()
                if not line:
                    continue

                last_detail = line[:300]
                match = PERCENT_RE.search(line)

                if match:
                    percent = float(match.group(1))
                    percent = max(0.0, min(100.0, percent))
                    last_percent = percent

                    self.msg_queue.put(
                        ("percent", job_id, mode, url, percent, last_detail)
                    )
                else:
                    self.msg_queue.put(
                        ("detail", job_id, mode, url, last_percent, last_detail)
                    )

            process.wait()

            if job_id in self.stopped_jobs:
                self.msg_queue.put(
                    ("done", job_id, DownloadRecord(
                        url, mode, "Stopped", "Download stopped by user"
                    ))
                )
            elif process.returncode == 0:
                self.msg_queue.put(
                    ("done", job_id, DownloadRecord(
                        url, mode, "Done", "Completed successfully"
                    ))
                )
            else:
                self.msg_queue.put(
                    ("done", job_id, DownloadRecord(
                        url, mode, "Failed", last_detail if last_detail else "Unknown failure"
                    ))
                )

        except Exception as exc:
            if job_id in self.stopped_jobs:
                self.msg_queue.put(
                    ("done", job_id, DownloadRecord(
                        url, mode, "Stopped", "Download stopped by user"
                    ))
                )
            else:
                self.msg_queue.put(
                    ("done", job_id, DownloadRecord(
                        url, mode, "Failed", str(exc)
                    ))
                )
        finally:
            self.job_processes.pop(job_id, None)

    def process_queue(self):
        try:
            while True:
                message = self.msg_queue.get_nowait()
                kind = message[0]

                if kind == "percent":
                    _, job_id, mode, url, percent, detail = message
                    row_id = self.current_rows.get(job_id)

                    if row_id and self.current_tree.exists(row_id):
                        self.current_tree.item(
                            row_id,
                            values=(f"{percent:.1f}%", mode, url, detail)
                        )

                    self.progress_var.set(percent)
                    self.progress_text_var.set(f"{percent:.0f}%")
                    self.status_var.set(f"Downloading... {percent:.1f}%")

                elif kind == "detail":
                    _, job_id, mode, url, percent, detail = message
                    row_id = self.current_rows.get(job_id)

                    if row_id and self.current_tree.exists(row_id):
                        self.current_tree.item(
                            row_id,
                            values=(f"{percent:.1f}%", mode, url, detail)
                        )

                    self.status_var.set(detail)

                else:
                    _, job_id, record = message
                    row_id = self.current_rows.get(job_id)

                    if row_id and self.current_tree.exists(row_id):
                        if kind == "progress":
                            self.current_tree.item(
                                row_id,
                                values=(
                                    record.status,
                                    record.mode,
                                    record.url,
                                    record.detail
                                )
                            )

                        elif kind == "done":
                            self.current_tree.delete(row_id)
                            self.current_rows.pop(job_id, None)
                            self.row_to_job.pop(row_id, None)

                            self.active_jobs = max(0, self.active_jobs - 1)
                            self.add_history(record)
                            self.stopped_jobs.discard(job_id)

                            if self.active_jobs == 0:
                                if record.status == "Done":
                                    self.progress_var.set(100.0)
                                    self.progress_text_var.set("100%")
                                else:
                                    self.progress_var.set(0.0)
                                    self.progress_text_var.set("0%")

                            self.update_status(record)

        except queue.Empty:
            pass

        self.root.after(120, self.process_queue)

    def update_status(self, latest=None):
        if latest:
            self.status_var.set(f"{latest.status}: {latest.detail}")
            return

        if self.active_jobs > 0:
            self.status_var.set(f"Working... active jobs: {self.active_jobs}")
        else:
            self.status_var.set("Ready")


def main():
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()