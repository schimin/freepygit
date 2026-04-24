import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import subprocess
import threading
import json
import os
from datetime import datetime
import queue

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".gitmanager_repos.json")

# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def run_git(args, cwd, timeout=60):
    try:
        result = subprocess.run(
            ["git", "-c", "color.ui=false", "-c", "core.quotepath=false"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except FileNotFoundError:
        return -1, "", "git not found in PATH"
    except Exception as e:
        return -1, "", str(e)


def get_repo_info(path):
    info = {
        "branch": "?",
        "status": "unknown",
        "ahead": 0,
        "behind": 0,
        "has_changes": False,
        "remote_url": "",
        "last_commit": "",
        "last_commit_msg": "",
    }
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)
    if rc == 0:
        info["branch"] = out

    rc, out, _ = run_git(["remote", "get-url", "origin"], path)
    if rc == 0:
        info["remote_url"] = out

    rc, out, _ = run_git(["rev-list", "--left-right", "--count", "HEAD...@{u}"], path)
    if rc == 0:
        parts = out.split()
        if len(parts) == 2:
            info["ahead"] = int(parts[0])
            info["behind"] = int(parts[1])

    rc, out, _ = run_git(["status", "--porcelain"], path)
    if rc == 0:
        info["has_changes"] = bool(out.strip())

    rc, out, _ = run_git(["log", "-1", "--format=%cr|%s"], path)
    if rc == 0 and "|" in out:
        when, msg = out.split("|", 1)
        info["last_commit"] = when.strip()
        info["last_commit_msg"] = msg.strip()

    if info["has_changes"]:
        info["status"] = "modified"
    elif info["behind"] > 0 and info["ahead"] > 0:
        info["status"] = "diverged"
    elif info["behind"] > 0:
        info["status"] = "behind"
    elif info["ahead"] > 0:
        info["status"] = "ahead"
    else:
        info["status"] = "clean"

    return info


def get_commit_log(path, max_count=80):
    rc, out, _ = run_git(
        ["log", f"--max-count={max_count}", "--format=%H|%ar|%s|%an", "--date=relative"],
        path,
    )
    commits = []
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash":     parts[0],          # full 40-char hash
                    "hash_short": parts[0][:8],
                    "date":     parts[1],
                    "msg":      parts[2],
                    "author":   parts[3],
                })
    return commits


def get_commit_files(repo_path, commit_hash):
    """Return list of (status, filepath) for files changed in a commit."""
    rc, out, _ = run_git(
        ["diff-tree", "--no-commit-id", "-r", "--name-status", commit_hash],
        repo_path,
    )
    files = []
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files.append((parts[0].strip(), parts[1].strip()))
    return files


def get_commit_file_diff(repo_path, commit_hash, filepath):
    """Return unified diff of a single file as it changed in a specific commit."""
    rc, out, _ = run_git(
        ["show", f"{commit_hash}", "--", filepath],
        repo_path,
    )
    if rc == 0 and out.strip():
        return out
    return f"(no diff available for {filepath} @ {commit_hash[:8]})"


def get_file_diff(repo_path, filepath):
    """Return unified diff for a single working-tree file."""
    # try unstaged diff first
    rc, out, _ = run_git(["diff", "--", filepath], repo_path)
    if rc == 0 and out.strip():
        return out

    # try staged diff
    rc, out, _ = run_git(["diff", "--cached", "--", filepath], repo_path)
    if rc == 0 and out.strip():
        return out

    # untracked / new file: show full content as all-added
    full_path = os.path.join(repo_path, filepath)
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        header = f"--- /dev/null\n+++ b/{filepath}\n@@ -0,0 +1,{len(lines)} @@\n"
        return header + "".join("+" + l for l in lines)
    except Exception:
        return f"(no diff available for {filepath})"


# ──────────────────────────────────────────────
#  Colours / fonts
# ──────────────────────────────────────────────

THEMES = {
    "default": {
        "BG": "#1e1f2e",
        "BG2": "#252638",
        "BG3": "#2d2f45",
        "BG_DIFF": "#12131e",
        "BG_GUT": "#161726",
        "ACCENT": "#7c6af7",
        "ACCENT2": "#5b54d4",
        "GREEN": "#4ade80",
        "YELLOW": "#fbbf24",
        "RED": "#f87171",
        "BLUE": "#60a5fa",
        "FG": "#e2e4f0",
        "FG2": "#9496b0",
        "BORDER": "#3a3c55",
        "DIFF_ADD_BG": "#0d2b0d",
        "DIFF_ADD_FG": "#4ade80",
        "DIFF_DEL_BG": "#2b0d0d",
        "DIFF_DEL_FG": "#f87171",
        "DIFF_HDR_BG": "#0d1530",
        "DIFF_HDR_FG": "#60a5fa",
        "DIFF_META_FG": "#6a6c88",
        "DIFF_LNO_FG": "#44465e",
        "DANGER_BG": "#4b1a1a",
        "DANGER_ACTIVE": "#6b2020",
    },
    "white": {
        "BG": "#f4f4f4",
        "BG2": "#ffffff",
        "BG3": "#e8e8e8",
        "BG_DIFF": "#ffffff",
        "BG_GUT": "#f0f0f0",
        "ACCENT": "#0078d7",
        "ACCENT2": "#005a9e",
        "GREEN": "#107c10",
        "YELLOW": "#d78315",
        "RED": "#d13438",
        "BLUE": "#0078d7",
        "FG": "#333333",
        "FG2": "#666666",
        "BORDER": "#cccccc",
        "DIFF_ADD_BG": "#e6ffed",
        "DIFF_ADD_FG": "#22863a",
        "DIFF_DEL_BG": "#ffeef0",
        "DIFF_DEL_FG": "#cb2431",
        "DIFF_HDR_BG": "#f1f8ff",
        "DIFF_HDR_FG": "#0366d6",
        "DIFF_META_FG": "#6a737d",
        "DIFF_LNO_FG": "#babbc0",
        "DANGER_BG": "#f8d7da",
        "DANGER_ACTIVE": "#f5c2c7",
    },
    "dark": {
        "BG": "#1e1e1e",
        "BG2": "#252526",
        "BG3": "#2d2d30",
        "BG_DIFF": "#1e1e1e",
        "BG_GUT": "#1e1e1e",
        "ACCENT": "#007acc",
        "ACCENT2": "#005f9e",
        "GREEN": "#89d185",
        "YELLOW": "#cca700",
        "RED": "#f14c4c",
        "BLUE": "#3794ff",
        "FG": "#cccccc",
        "FG2": "#999999",
        "BORDER": "#3e3e42",
        "DIFF_ADD_BG": "#203820",
        "DIFF_ADD_FG": "#89d185",
        "DIFF_DEL_BG": "#3e2020",
        "DIFF_DEL_FG": "#f14c4c",
        "DIFF_HDR_BG": "#000000",
        "DIFF_HDR_FG": "#569cd6",
        "DIFF_META_FG": "#858585",
        "DIFF_LNO_FG": "#858585",
        "DANGER_BG": "#4b1a1a",
        "DANGER_ACTIVE": "#6b2020",
    }
}

_theme_name = "default"
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            _config_data = json.load(f)
            _theme_name = _config_data.get("theme", "default")
    except Exception:
        pass

if _theme_name not in THEMES:
    _theme_name = "default"

_theme = THEMES[_theme_name]

BG       = _theme["BG"]
BG2      = _theme["BG2"]
BG3      = _theme["BG3"]
BG_DIFF  = _theme["BG_DIFF"]
BG_GUT   = _theme["BG_GUT"]
ACCENT   = _theme["ACCENT"]
ACCENT2  = _theme["ACCENT2"]
GREEN    = _theme["GREEN"]
YELLOW   = _theme["YELLOW"]
RED      = _theme["RED"]
BLUE     = _theme["BLUE"]
FG       = _theme["FG"]
FG2      = _theme["FG2"]
BORDER   = _theme["BORDER"]

DIFF_ADD_BG  = _theme["DIFF_ADD_BG"]
DIFF_ADD_FG  = _theme["DIFF_ADD_FG"]
DIFF_DEL_BG  = _theme["DIFF_DEL_BG"]
DIFF_DEL_FG  = _theme["DIFF_DEL_FG"]
DIFF_HDR_BG  = _theme["DIFF_HDR_BG"]
DIFF_HDR_FG  = _theme["DIFF_HDR_FG"]
DIFF_META_FG = _theme["DIFF_META_FG"]
DIFF_LNO_FG  = _theme["DIFF_LNO_FG"]

DANGER_BG     = _theme["DANGER_BG"]
DANGER_ACTIVE = _theme["DANGER_ACTIVE"]

FONT      = ("Consolas", 10)
FONT_BOLD = ("Consolas", 10, "bold")
FONT_SM   = ("Consolas", 9)
FONT_LG   = ("Consolas", 13, "bold")
FONT_DIFF = ("Consolas", 10)

STATUS_COLORS = {
    "clean":    GREEN,
    "modified": YELLOW,
    "behind":   BLUE,
    "ahead":    ACCENT,
    "diverged": RED,
    "unknown":  FG2,
    "fetching": FG2,
}

STATUS_ICONS = {
    "clean":    "✓",
    "modified": "●",
    "behind":   "↓",
    "ahead":    "↑",
    "diverged": "↕",
    "unknown":  "?",
    "fetching": "⟳",
}


# ──────────────────────────────────────────────
#  App
# ──────────────────────────────────────────────

class GitManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git Manager")
        self.geometry("1340x860")
        self.minsize(900, 640)
        self.configure(bg=BG)

        self.repos: list[dict] = []
        self.selected_repo: dict | None = None
        self._op_queue: queue.Queue = queue.Queue()
        self._diff_job = None
        self.current_theme = _theme_name

        self._setup_styles()
        self._build_ui()
        self._load_config()
        self._start_queue_processor()
        self.after(200, self._refresh_all_status)

    # ── Styles ────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".", background=BG, foreground=FG, font=FONT,
                    fieldbackground=BG2, bordercolor=BORDER,
                    troughcolor=BG2, selectbackground=ACCENT, selectforeground=FG)

        s.configure("Treeview", background=BG2, foreground=FG,
                    fieldbackground=BG2, rowheight=26, borderwidth=0, relief="flat")
        s.map("Treeview",
              background=[("selected", ACCENT2)],
              foreground=[("selected", FG)])

        s.configure("Treeview.Heading", background=BG3, foreground=FG2,
                    font=FONT_SM, relief="flat", borderwidth=0)
        s.map("Treeview.Heading", background=[("active", BG3)])

        s.configure("TScrollbar", background=BG3, troughcolor=BG,
                    borderwidth=0, arrowsize=12)
        s.configure("TLabel",         background=BG,  foreground=FG)
        s.configure("TFrame",         background=BG)
        s.configure("Sidebar.TFrame", background=BG3)
        s.configure("TPanedwindow",   background=BORDER)

        s.configure("TButton", background=BG3, foreground=FG,
                    font=FONT_SM, relief="flat", borderwidth=0, padding=(8, 4))
        s.map("TButton",
              background=[("active", ACCENT2), ("pressed", ACCENT)],
              foreground=[("active", FG)])

        s.configure("Accent.TButton", background=ACCENT, foreground=FG,
                    font=FONT_BOLD, padding=(10, 5))
        s.map("Accent.TButton",
              background=[("active", ACCENT2), ("pressed", ACCENT2)])

        s.configure("Danger.TButton", background=DANGER_BG, foreground=RED,
                    font=FONT_SM, relief="flat", borderwidth=0, padding=(8, 4))
        s.map("Danger.TButton", background=[("active", DANGER_ACTIVE)])

    # ── Layout ────────────────────────────────

    def _build_ui(self):
        # ── toolbar
        toolbar = tk.Frame(self, bg=BG3, height=48)
        toolbar.pack(fill="x", side="top")
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text="  ⎇  Git Manager", bg=BG3, fg=ACCENT,
                 font=("Consolas", 14, "bold")).pack(side="left", padx=8)
        tk.Frame(toolbar, bg=BORDER, width=1).pack(side="left", fill="y", padx=8, pady=6)

        for label, cmd, style_ in [
            ("⟳  Fetch All",  self._fetch_all,  "TButton"),
            ("↓  Pull All",   self._pull_all,   "Accent.TButton"),
            ("↑  Push All",   self._push_all,   "TButton"),
            ("＋  Add Repo",  self._add_repo,   "TButton"),
        ]:
            ttk.Button(toolbar, text=label, command=cmd,
                       style=style_).pack(side="left", padx=3, pady=8)

        # theme selector
        theme_frame = tk.Frame(toolbar, bg=BG3)
        theme_frame.pack(side="right", padx=10, pady=10)
        
        ttk.Button(theme_frame, text="☾", width=3, command=lambda: self._set_theme("dark")).pack(side="right", padx=1)
        ttk.Button(theme_frame, text="☀", width=3, command=lambda: self._set_theme("white")).pack(side="right", padx=1)
        ttk.Button(theme_frame, text="☁", width=3, command=lambda: self._set_theme("default")).pack(side="right", padx=1)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(toolbar, textvariable=self.status_var, bg=BG3, fg=FG2,
                 font=FONT_SM).pack(side="right", padx=12)
        self.progress = ttk.Progressbar(toolbar, mode="indeterminate", length=120)

        # ── horizontal split: sidebar | detail
        h_pane = ttk.PanedWindow(self, orient="horizontal")
        h_pane.pack(fill="both", expand=True)

        left = ttk.Frame(h_pane, style="Sidebar.TFrame", width=310)
        h_pane.add(left, weight=0)
        self._build_sidebar(left)

        right = ttk.Frame(h_pane)
        h_pane.add(right, weight=1)
        self._build_detail(right)

        # ── bottom status bar
        log_frame = tk.Frame(self, bg=BG3, height=24)
        log_frame.pack(fill="x", side="bottom")
        log_frame.pack_propagate(False)
        self.log_var = tk.StringVar(value="")
        tk.Label(log_frame, textvariable=self.log_var, bg=BG3, fg=FG2,
                 font=FONT_SM, anchor="w").pack(fill="x", padx=8)

    def _build_sidebar(self, parent):
        v_pane = ttk.PanedWindow(parent, orient="vertical")
        v_pane.pack(fill="both", expand=True)

        repo_frame = ttk.Frame(v_pane, style="Sidebar.TFrame")
        v_pane.add(repo_frame, weight=3)

        hdr = tk.Frame(repo_frame, bg=BG3)
        hdr.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(hdr, text="REPOSITORIES", bg=BG3, fg=FG2,
                 font=("Consolas", 9, "bold")).pack(side="left")
        ttk.Button(hdr, text="＋", width=3, command=self._add_repo,
                   style="TButton").pack(side="right")

        sf = tk.Frame(repo_frame, bg=BG3)
        sf.pack(fill="x", padx=6, pady=2)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_repos()
                                  if hasattr(self, "repo_tree") else None)
        entry = tk.Entry(sf, textvariable=self.search_var, bg=BG2, fg=FG,
                         insertbackground=FG, relief="flat", font=FONT_SM, bd=4)
        entry.pack(fill="x")
        entry.insert(0, "Search…")
        entry.bind("<FocusIn>", lambda e: entry.delete(0, "end")
                   if entry.get() == "Search…" else None)

        repo_body = tk.Frame(repo_frame, bg=BG3)
        repo_body.pack(fill="both", expand=True, padx=6, pady=4)

        self.repo_tree = ttk.Treeview(repo_body, columns=("name",),
                                      show="tree", selectmode="browse")
        self.repo_tree.column("#0",   width=26,  minwidth=26,  stretch=False)
        self.repo_tree.column("name", width=260, stretch=True)
        self.repo_tree.tag_configure("group", foreground=FG2,
                                     font=("Consolas", 9, "bold"))

        sc = ttk.Scrollbar(repo_body, orient="vertical", command=self.repo_tree.yview)
        self.repo_tree.configure(yscrollcommand=sc.set)
        self.repo_tree.pack(side="left", fill="both", expand=True)
        sc.pack(side="left", fill="y")

        self.repo_tree.bind("<<TreeviewSelect>>", self._on_repo_select)
        self.repo_tree.bind("<Button-3>",          self._on_repo_right_click)

        branch_frame = ttk.Frame(v_pane, style="Sidebar.TFrame")
        v_pane.add(branch_frame, weight=2)

        bhdr = tk.Frame(branch_frame, bg=BG3)
        bhdr.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(bhdr, text="BRANCHES", bg=BG3, fg=FG2,
                 font=("Consolas", 9, "bold")).pack(side="left")
        ttk.Button(bhdr, text="＋ Branch", command=self._create_branch,
                   style="TButton").pack(side="right")

        branch_body = tk.Frame(branch_frame, bg=BG3)
        branch_body.pack(fill="both", expand=True, padx=6, pady=4)

        self.left_branch_tree = ttk.Treeview(branch_body, columns=("name",),
                                             show="tree", selectmode="browse")
        self.left_branch_tree.column("#0", width=26, minwidth=26, stretch=False)
        self.left_branch_tree.column("name", width=260, stretch=True)
        self.left_branch_tree.tag_configure("local", foreground=FG)
        self.left_branch_tree.tag_configure("remote", foreground=FG2)
        self.left_branch_tree.tag_configure("current", foreground=ACCENT, font=FONT_BOLD)
        self.left_branch_tree.tag_configure("group", foreground=FG2, font=("Consolas", 9, "bold"))

        bsc = ttk.Scrollbar(branch_body, orient="vertical", command=self.left_branch_tree.yview)
        self.left_branch_tree.configure(yscrollcommand=bsc.set)
        self.left_branch_tree.pack(side="left", fill="both", expand=True)
        bsc.pack(side="left", fill="y")
        
        self.left_branch_tree.bind("<Button-3>", self._on_left_branch_right_click)
        self.left_branch_tree.bind("<Double-1>", self._on_left_branch_double_click)

    def _build_detail(self, parent):
        # header card
        card = tk.Frame(parent, bg=BG2)
        card.pack(fill="x")

        self.detail_name   = tk.Label(card, text="← Select a repository",
                                      bg=BG2, fg=FG, font=FONT_LG, anchor="w")
        self.detail_name.pack(side="left", padx=14, pady=10)
        self.detail_branch = tk.Label(card, text="", bg=BG2, fg=ACCENT, font=FONT_BOLD)
        self.detail_branch.pack(side="left", padx=4)
        self.detail_status = tk.Label(card, text="", bg=BG2, fg=GREEN, font=FONT_BOLD)
        self.detail_status.pack(side="left", padx=4)
        self.detail_url    = tk.Label(card, text="", bg=BG2, fg=FG2, font=FONT_SM)
        self.detail_url.pack(side="left", padx=8)

        btn_frame = tk.Frame(card, bg=BG2)
        btn_frame.pack(side="right", padx=10, pady=8)
        for label, cmd in [
            ("⟳ Fetch",     lambda: self._repo_op("fetch")),
            ("↓ Pull",      lambda: self._repo_op("pull")),
            ("↑ Push",      lambda: self._repo_op("push")),
            ("Open Folder", self._open_folder),
            ("Terminal",    self._open_terminal),
        ]:
            ttk.Button(btn_frame, text=label, command=cmd,
                       style="TButton").pack(side="left", padx=2)
        ttk.Button(btn_frame, text="✕ Remove", command=self._remove_repo,
                   style="Danger.TButton").pack(side="left", padx=2)

        # notebook
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        log_tab     = ttk.Frame(nb)
        changes_tab = ttk.Frame(nb)
        branch_tab  = ttk.Frame(nb)
        console_tab = ttk.Frame(nb)

        nb.add(log_tab,     text="  Commit Log  ")
        nb.add(changes_tab, text="  Changes  ")
        nb.add(branch_tab,  text="  Branches  ")
        nb.add(console_tab, text="  Console  ")

        self._build_log_tab(log_tab)
        self._build_changes_tab(changes_tab)
        self._build_branch_tab(branch_tab)
        self._build_console_tab(console_tab)

    # ── Commit log tab ────────────────────────

    def _build_log_tab(self, parent):
        # ── horizontal split: commit list (left) | commit detail (right)
        h_pane = ttk.PanedWindow(parent, orient="horizontal")
        h_pane.pack(fill="both", expand=True)

        # ── LEFT: commit list ────────────────────────────────────────────
        left_frame = ttk.Frame(h_pane)
        h_pane.add(left_frame, weight=2)

        cols = ("hash", "date", "message", "author")
        self.log_tree = ttk.Treeview(left_frame, columns=cols, show="headings")
        self.log_tree.heading("hash",    text="Hash")
        self.log_tree.heading("date",    text="Date")
        self.log_tree.heading("message", text="Message")
        self.log_tree.heading("author",  text="Author")
        self.log_tree.column("hash",    width=80,  minwidth=60,  stretch=False)
        self.log_tree.column("date",    width=130, minwidth=100, stretch=False)
        self.log_tree.column("message", width=380, stretch=True)
        self.log_tree.column("author",  width=130, minwidth=100, stretch=False)

        self.log_tree.tag_configure("working_tree", foreground=YELLOW,
                                    font=("Consolas", 10, "bold"))

        ys = ttk.Scrollbar(left_frame, orient="vertical",   command=self.log_tree.yview)
        xs = ttk.Scrollbar(left_frame, orient="horizontal", command=self.log_tree.xview)
        self.log_tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.log_tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        self.log_tree.bind("<<TreeviewSelect>>", self._on_commit_select)

        # ── RIGHT: commit detail (file list + diff) ──────────────────────
        right_frame = ttk.Frame(h_pane)
        h_pane.add(right_frame, weight=3)

        # header bar showing the selected commit info
        self.commit_detail_bar = tk.Frame(right_frame, bg=BG3, height=30)
        self.commit_detail_bar.pack(fill="x")
        self.commit_detail_bar.pack_propagate(False)
        self.commit_detail_label = tk.Label(
            self.commit_detail_bar,
            text="  ← click a commit to see its changes",
            bg=BG3, fg=FG2, font=FONT_SM, anchor="w"
        )
        self.commit_detail_label.pack(fill="x", padx=6, pady=4)

        # staging panel (hidden by default)
        self._staging_panel = tk.Frame(right_frame, bg=BG2)

        _stg_hdr = tk.Frame(self._staging_panel, bg=BG3, height=28)
        _stg_hdr.pack(fill="x")
        _stg_hdr.pack_propagate(False)
        tk.Label(_stg_hdr, text="  Stage files for commit",
                 bg=BG3, fg=YELLOW, font=("Consolas", 10, "bold"),
                 anchor="w").pack(side="left", padx=6, pady=4)

        _stg_lo = tk.Frame(self._staging_panel, bg=BG2)
        _stg_lo.pack(fill="both", expand=True, padx=6, pady=4)
        _stg_cv = tk.Canvas(_stg_lo, bg=BG2, bd=0, highlightthickness=0)
        _stg_sb = ttk.Scrollbar(_stg_lo, orient="vertical", command=_stg_cv.yview)
        self._stg_inner = tk.Frame(_stg_cv, bg=BG2)
        self._stg_inner.bind("<Configure>",
            lambda e: _stg_cv.configure(scrollregion=_stg_cv.bbox("all")))
        _stg_cv.create_window((0, 0), window=self._stg_inner, anchor="nw")
        _stg_cv.configure(yscrollcommand=_stg_sb.set)
        _stg_cv.pack(side="left", fill="both", expand=True)
        _stg_sb.pack(side="right", fill="y")
        _stg_cv.bind("<MouseWheel>",
                     lambda e: _stg_cv.yview_scroll(-1*(e.delta//120), "units"))
        self._stg_canvas = _stg_cv

        _stg_br = tk.Frame(self._staging_panel, bg=BG2)
        _stg_br.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Button(_stg_br, text="Select All",
                   command=self._stage_select_all).pack(side="left", padx=2)
        ttk.Button(_stg_br, text="Select None",
                   command=self._stage_select_none).pack(side="left", padx=2)

        _stg_mf = tk.Frame(self._staging_panel, bg=BG2)
        _stg_mf.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(_stg_mf, text="Commit message:", bg=BG2, fg=FG2,
                 font=("Consolas", 9), anchor="w").pack(anchor="w")
        self._commit_msg_text = tk.Text(_stg_mf, bg=BG3, fg=FG,
                                        font=("Consolas", 9), relief="flat",
                                        height=3, insertbackground=FG, bd=4)
        self._commit_msg_text.pack(fill="x", pady=(2, 4))
        ttk.Button(_stg_mf, text="Commit", command=self._do_commit,
                   style="Accent.TButton").pack(anchor="e")

        self._stg_check_vars = []  # list of (BooleanVar, status, filepath)

        # vertical split inside right panel: file list (top) + diff (bottom)
        v_pane = ttk.PanedWindow(right_frame, orient="vertical")
        v_pane.pack(fill="both", expand=True)

        # ── top: files changed in the commit
        files_frame = ttk.Frame(v_pane)
        v_pane.add(files_frame, weight=1)

        cols2 = ("status", "file")
        self.commit_files_tree = ttk.Treeview(files_frame, columns=cols2,
                                              show="headings", selectmode="browse")
        self.commit_files_tree.heading("status", text="St")
        self.commit_files_tree.heading("file",   text="Changed File")
        self.commit_files_tree.column("status", width=35, minwidth=30, stretch=False)
        self.commit_files_tree.column("file",   stretch=True)

        self.commit_files_tree.tag_configure("M",  foreground=YELLOW)
        self.commit_files_tree.tag_configure("A",  foreground=GREEN)
        self.commit_files_tree.tag_configure("D",  foreground=RED)
        self.commit_files_tree.tag_configure("R",  foreground=BLUE)
        self.commit_files_tree.tag_configure("C",  foreground=BLUE)
        self.commit_files_tree.tag_configure("??", foreground=FG2)

        cfs_sc = ttk.Scrollbar(files_frame, orient="vertical",
                               command=self.commit_files_tree.yview)
        self.commit_files_tree.configure(yscrollcommand=cfs_sc.set)
        self.commit_files_tree.pack(side="left", fill="both", expand=True)
        cfs_sc.pack(side="right", fill="y")

        self.commit_files_tree.bind("<<TreeviewSelect>>", self._on_commit_file_select)

        # ── bottom: diff viewer (reuse same style as working-tree diff)
        diff_outer = ttk.Frame(v_pane)
        v_pane.add(diff_outer, weight=3)

        diff_bar2 = tk.Frame(diff_outer, bg=BG3, height=26)
        diff_bar2.pack(fill="x")
        diff_bar2.pack_propagate(False)
        self.commit_diff_file_label = tk.Label(
            diff_bar2, text="  Select a file above to see its diff",
            bg=BG3, fg=FG2, font=FONT_SM, anchor="w"
        )
        self.commit_diff_file_label.pack(side="left", fill="x", padx=6)
        self.commit_diff_stat_label = tk.Label(diff_bar2, text="", bg=BG3, fg=FG2, font=FONT_SM)
        self.commit_diff_stat_label.pack(side="right", padx=10)

        diff_body2 = tk.Frame(diff_outer, bg=BG_DIFF)
        diff_body2.pack(fill="both", expand=True)

        self.commit_diff_gutter = tk.Text(
            diff_body2, width=9, bg=BG_GUT, fg=DIFF_LNO_FG,
            font=FONT_DIFF, relief="flat", state="disabled",
            cursor="arrow", selectbackground=BG_GUT,
            wrap="none", bd=0, padx=4
        )
        self.commit_diff_gutter.pack(side="left", fill="y")
        tk.Frame(diff_body2, bg=BORDER, width=1).pack(side="left", fill="y")

        self.commit_diff_text = tk.Text(
            diff_body2, bg=BG_DIFF, fg=FG, font=FONT_DIFF,
            relief="flat", state="disabled", wrap="none",
            insertbackground=FG, selectbackground=ACCENT2,
            bd=0, padx=6
        )
        cdiff_ys = ttk.Scrollbar(diff_body2, orient="vertical",
                                 command=self._commit_diff_yscroll_cmd)
        cdiff_xs = ttk.Scrollbar(diff_outer, orient="horizontal",
                                 command=self.commit_diff_text.xview)
        self.commit_diff_text.configure(
            yscrollcommand=self._commit_diff_yset,
            xscrollcommand=cdiff_xs.set
        )
        self.commit_diff_text.pack(side="left", fill="both", expand=True)
        cdiff_ys.pack(side="right", fill="y")
        cdiff_xs.pack(fill="x")

        # colour tags
        for tw in (self.commit_diff_text,):
            tw.tag_configure("add",    background=DIFF_ADD_BG, foreground=DIFF_ADD_FG)
            tw.tag_configure("del",    background=DIFF_DEL_BG, foreground=DIFF_DEL_FG)
            tw.tag_configure("hunk",   background=DIFF_HDR_BG, foreground=DIFF_HDR_FG)
            tw.tag_configure("meta",   foreground=DIFF_META_FG)
            tw.tag_configure("normal", foreground=FG)
        for tw in (self.commit_diff_gutter,):
            tw.tag_configure("add",    background=DIFF_ADD_BG)
            tw.tag_configure("del",    background=DIFF_DEL_BG)
            tw.tag_configure("hunk",   background=DIFF_HDR_BG)
            tw.tag_configure("normal", background=BG_GUT)
            tw.tag_configure("meta",   background=BG_GUT)

        for widget in (self.commit_diff_text, self.commit_diff_gutter):
            widget.bind("<MouseWheel>", self._on_commit_diff_wheel)

        # keep track of current commit hash for file-diff lookup
        self._selected_commit_hash = None
        self._commit_diff_job = None

    # ── Changes tab: file list + diff pane ────

    def _build_changes_tab(self, parent):
        # vertical paned: file list (top) + diff (bottom)
        vpane = ttk.PanedWindow(parent, orient="vertical")
        vpane.pack(fill="both", expand=True)

        # ── top: changed files
        top_frame = ttk.Frame(vpane)
        vpane.add(top_frame, weight=1)

        cols = ("status", "file")
        self.changes_tree = ttk.Treeview(top_frame, columns=cols,
                                         show="headings", selectmode="browse")
        self.changes_tree.heading("status", text="St")
        self.changes_tree.heading("file",   text="File")
        self.changes_tree.column("status", width=35, minwidth=30, stretch=False)
        self.changes_tree.column("file",   stretch=True)

        sc = ttk.Scrollbar(top_frame, orient="vertical",
                           command=self.changes_tree.yview)
        self.changes_tree.configure(yscrollcommand=sc.set)
        self.changes_tree.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        self.changes_tree.bind("<<TreeviewSelect>>", self._on_file_select)
        self.changes_tree.tag_configure("M",  foreground=YELLOW)
        self.changes_tree.tag_configure("A",  foreground=GREEN)
        self.changes_tree.tag_configure("D",  foreground=RED)
        self.changes_tree.tag_configure("R",  foreground=BLUE)
        self.changes_tree.tag_configure("??", foreground=FG2)

        # ── bottom: diff viewer
        diff_outer = ttk.Frame(vpane)
        vpane.add(diff_outer, weight=2)

        # diff toolbar
        diff_bar = tk.Frame(diff_outer, bg=BG3, height=26)
        diff_bar.pack(fill="x")
        diff_bar.pack_propagate(False)
        self.diff_file_label = tk.Label(
            diff_bar, text="  Select a file above to see its diff",
            bg=BG3, fg=FG2, font=FONT_SM, anchor="w"
        )
        self.diff_file_label.pack(side="left", fill="x", padx=6)

        # stat summary (lines added / removed)
        self.diff_stat_label = tk.Label(diff_bar, text="", bg=BG3, fg=FG2, font=FONT_SM)
        self.diff_stat_label.pack(side="right", padx=10)

        # diff body: gutter | separator | content
        diff_body = tk.Frame(diff_outer, bg=BG_DIFF)
        diff_body.pack(fill="both", expand=True)

        # line-number gutter (read-only, synced)
        self.diff_gutter = tk.Text(
            diff_body, width=9, bg=BG_GUT, fg=DIFF_LNO_FG,
            font=FONT_DIFF, relief="flat", state="disabled",
            cursor="arrow", selectbackground=BG_GUT,
            wrap="none", bd=0, padx=4
        )
        self.diff_gutter.pack(side="left", fill="y")

        tk.Frame(diff_body, bg=BORDER, width=1).pack(side="left", fill="y")

        # main diff text
        self.diff_text = tk.Text(
            diff_body, bg=BG_DIFF, fg=FG, font=FONT_DIFF,
            relief="flat", state="disabled", wrap="none",
            insertbackground=FG, selectbackground=ACCENT2,
            bd=0, padx=6
        )

        diff_ys = ttk.Scrollbar(diff_body, orient="vertical",
                                command=self._diff_yscroll_cmd)
        diff_xs = ttk.Scrollbar(diff_outer, orient="horizontal",
                                command=self.diff_text.xview)

        self.diff_text.configure(
            yscrollcommand=self._diff_yset,
            xscrollcommand=diff_xs.set
        )
        self.diff_text.pack(side="left", fill="both", expand=True)
        diff_ys.pack(side="right", fill="y")
        diff_xs.pack(fill="x")

        # diff colour tags
        self.diff_text.tag_configure("add",    background=DIFF_ADD_BG, foreground=DIFF_ADD_FG)
        self.diff_text.tag_configure("del",    background=DIFF_DEL_BG, foreground=DIFF_DEL_FG)
        self.diff_text.tag_configure("hunk",   background=DIFF_HDR_BG, foreground=DIFF_HDR_FG)
        self.diff_text.tag_configure("meta",   foreground=DIFF_META_FG)
        self.diff_text.tag_configure("normal", foreground=FG)

        self.diff_gutter.tag_configure("add",    background=DIFF_ADD_BG)
        self.diff_gutter.tag_configure("del",    background=DIFF_DEL_BG)
        self.diff_gutter.tag_configure("hunk",   background=DIFF_HDR_BG)
        self.diff_gutter.tag_configure("normal", background=BG_GUT)
        self.diff_gutter.tag_configure("meta",   background=BG_GUT)

        # sync scroll via mouse wheel
        for widget in (self.diff_text, self.diff_gutter):
            widget.bind("<MouseWheel>", self._on_diff_wheel)

    # sync helpers (working-tree diff)
    def _diff_yscroll_cmd(self, *args):
        self.diff_text.yview(*args)
        self.diff_gutter.yview(*args)

    def _diff_yset(self, first, last):
        self.diff_text.yview_moveto(first)
        self.diff_gutter.yview_moveto(first)

    def _on_diff_wheel(self, event):
        delta = -1 * (event.delta // 120)
        self.diff_text.yview_scroll(delta, "units")
        self.diff_gutter.yview_scroll(delta, "units")
        return "break"

    # sync helpers (commit diff)
    def _commit_diff_yscroll_cmd(self, *args):
        self.commit_diff_text.yview(*args)
        self.commit_diff_gutter.yview(*args)

    def _commit_diff_yset(self, first, last):
        self.commit_diff_text.yview_moveto(first)
        self.commit_diff_gutter.yview_moveto(first)

    def _on_commit_diff_wheel(self, event):
        delta = -1 * (event.delta // 120)
        self.commit_diff_text.yview_scroll(delta, "units")
        self.commit_diff_gutter.yview_scroll(delta, "units")
        return "break"

    # ── Branches tab ──────────────────────────

    def _build_branch_tab(self, parent):
        cols = ("name", "type", "tracking")
        self.branch_tree = ttk.Treeview(parent, columns=cols, show="headings")
        self.branch_tree.heading("name",     text="Branch")
        self.branch_tree.heading("type",     text="Type")
        self.branch_tree.heading("tracking", text="Tracking")
        self.branch_tree.column("name",     stretch=True)
        self.branch_tree.column("type",     width=90,  stretch=False)
        self.branch_tree.column("tracking", width=200, stretch=False)

        sc = ttk.Scrollbar(parent, orient="vertical", command=self.branch_tree.yview)
        self.branch_tree.configure(yscrollcommand=sc.set)
        self.branch_tree.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

    # ── Console tab ───────────────────────────

    def _build_console_tab(self, parent):
        self.console_text = tk.Text(parent, bg=BG_DIFF, fg=GREEN,
                                    font=("Consolas", 9), relief="flat",
                                    state="disabled", wrap="word",
                                    insertbackground=GREEN)
        sc = ttk.Scrollbar(parent, orient="vertical",
                           command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=sc.set)
        self.console_text.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        self.console_text.tag_configure("error",   foreground=RED)
        self.console_text.tag_configure("success", foreground=GREEN)
        self.console_text.tag_configure("info",    foreground=BLUE)
        self.console_text.tag_configure("cmd",     foreground=YELLOW)

    def _set_theme(self, new_theme):
        if new_theme == getattr(self, "current_theme", "default"):
            return
        self.current_theme = new_theme
        self._save_config()
        messagebox.showinfo("Theme Changed", "Please restart Git Manager to fully apply the new theme.")

    # ── Config ────────────────────────────────

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.repos = data.get("repos", [])
                for r in self.repos:
                    r.setdefault("info", {})
            except Exception:
                self.repos = []
        self._rebuild_tree()

    def _save_config(self):
        data = {
            "theme": getattr(self, "current_theme", "default"),
            "repos": [{"name": r["name"], "path": r["path"],
                       "group": r.get("group", "")} for r in self.repos]
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"Config save error: {e}", "error")

    # ── Tree rebuild ──────────────────────────

    def _rebuild_tree(self, filter_text=""):
        for item in self.repo_tree.get_children():
            self.repo_tree.delete(item)

        groups: dict[str, list] = {}
        for repo in self.repos:
            if filter_text and filter_text.lower() not in repo["name"].lower():
                continue
            g = repo.get("group") or "ungrouped"
            groups.setdefault(g, []).append(repo)

        for group, repos in sorted(groups.items()):
            g_id = self.repo_tree.insert("", "end", text="▶",
                                         values=(f"  {group.upper()}",),
                                         tags=("group",), open=True)
            for repo in repos:
                info   = repo.get("info", {})
                status = info.get("status", "unknown")
                icon   = STATUS_ICONS.get(status, "?")
                color  = STATUS_COLORS.get(status, FG2)
                branch = info.get("branch", "")
                ahead  = info.get("ahead", 0)
                behind = info.get("behind", 0)

                extras = ""
                if ahead:  extras += f" ↑{ahead}"
                if behind: extras += f" ↓{behind}"

                label = f"  {icon}  {repo['name']}"
                if branch:
                    label += f"  [{branch}]{extras}"

                self.repo_tree.insert(g_id, "end", text="",
                                      values=(label,),
                                      tags=(status, repo["path"]))
                self.repo_tree.tag_configure(status,       foreground=color)
                self.repo_tree.tag_configure(repo["path"], foreground=color)

    def _filter_repos(self):
        txt = self.search_var.get()
        if txt == "Search…":
            txt = ""
        self._rebuild_tree(txt)

    # ── Repo selection ────────────────────────

    def _on_repo_select(self, event=None):
        sel = self.repo_tree.selection()
        if not sel:
            return
        item = sel[0]
        tags = self.repo_tree.item(item, "tags")
        if "group" in tags:
            return
        path = tags[-1] if tags else None
        repo = next((r for r in self.repos if r["path"] == path), None)
        if repo is None:
            return
        self.selected_repo = repo
        self._update_detail_header()
        self._load_detail_tabs()
        self._clear_diff()

    def _update_detail_header(self):
        r = self.selected_repo
        if not r:
            return
        info   = r.get("info", {})
        status = info.get("status", "unknown")
        color  = STATUS_COLORS.get(status, FG2)
        icon   = STATUS_ICONS.get(status, "?")
        url    = info.get("remote_url", "")

        self.detail_name.config(text=r["name"])
        self.detail_branch.config(text=f"  ⎇ {info.get('branch','?')}")
        self.detail_status.config(text=f"  {icon} {status}", fg=color)
        self.detail_url.config(text=url[:80] + "…" if len(url) > 80 else url)

    def _load_detail_tabs(self):
        if not self.selected_repo:
            return
        threading.Thread(
            target=self._bg_load_tabs,
            args=(self.selected_repo["path"],),
            daemon=True
        ).start()

    def _bg_load_tabs(self, path):
        commits = get_commit_log(path)

        rc, out, _ = run_git(["status", "--porcelain"], path)
        changes = []
        if rc == 0:
            for line in out.splitlines():
                line = line.lstrip('\ufeff')
                if len(line) > 2:
                    st = line[:2].strip() or "?"
                    fn = line[2:].lstrip()
                    if fn.startswith('"') and fn.endswith('"'):
                        fn = fn[1:-1]
                    changes.append((st, fn))

        rc2, out2, _ = run_git(["branch", "-vva"], path)
        branches = []
        if rc2 == 0:
            for line in out2.splitlines():
                current = line.startswith("*")
                line = line.lstrip("* ").strip()
                parts = line.split()
                if not parts:
                    continue
                bname    = parts[0]
                tracking = ""
                if "[" in line:
                    s = line.index("["); e = line.index("]")
                    tracking = line[s+1:e]
                btype = "local" if "remotes/" not in bname else "remote"
                branches.append((bname, btype, tracking, current))

        self.after(0, self._populate_tabs, commits, changes, branches)

    def _populate_tabs(self, commits, changes, branches):
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)

        _n = len(changes)
        _wt = ("Working Tree / Index  (" + str(_n) + " changed)"
               if _n else "Working Tree / Index  (clean)")
        self.log_tree.insert("", "end", iid="__working_tree__",
                             values=("●", "now", _wt, ""),
                             tags=("working_tree",) if _n else ())

        for c in commits:
            # store full hash as item iid so we can retrieve it on selection
            self.log_tree.insert("", "end", iid=c["hash"],
                                 values=(c["hash_short"], c["date"], c["msg"], c["author"]))

        for item in self.changes_tree.get_children():
            self.changes_tree.delete(item)
        for st, fn in changes:
            tag = st if st in ("M", "A", "D", "R", "??") else "M"
            self.changes_tree.insert("", "end", values=(st, fn), tags=(tag,))

        for item in self.branch_tree.get_children():
            self.branch_tree.delete(item)
        for bname, btype, tracking, current in branches:
            self.branch_tree.insert(
                "", "end",
                values=(("★ " if current else "  ") + bname, btype, tracking),
                tags=("current" if current else "",)
            )
        self.branch_tree.tag_configure("current", foreground=ACCENT)

        if hasattr(self, "left_branch_tree"):
            for item in self.left_branch_tree.get_children():
                self.left_branch_tree.delete(item)
            
            loc_id = self.left_branch_tree.insert("", "end", text="▼", values=("  Local Branches",), tags=("group",), open=True)
            rem_id = self.left_branch_tree.insert("", "end", text="▶", values=("  Remote Branches",), tags=("group",), open=False)
            
            for bname, btype, tracking, current in branches:
                parent_id = loc_id if btype == "local" else rem_id
                tag = "current" if current else btype
                icon = "★" if current else "⎇"
                self.left_branch_tree.insert(parent_id, "end", text="", values=(f"  {icon}  {bname}",), tags=(tag, bname, btype))

    # ── Commit selection & detail ─────────────

    def _on_commit_select(self, event=None):
        sel = self.log_tree.selection()
        if not sel or not self.selected_repo:
            return
        commit_hash = sel[0]

        if commit_hash == "__working_tree__":
            self._selected_commit_hash = None
            self.commit_detail_label.config(
                text="  ● Working Tree / Index — stage files and commit",
                fg=YELLOW
            )
            self._show_staging_panel()
            return

        self._staging_panel.pack_forget()
        self._selected_commit_hash = commit_hash
        short = commit_hash[:8]

        values = self.log_tree.item(commit_hash, "values")
        msg = values[2] if len(values) > 2 else ""
        self.commit_detail_label.config(
            text="  ⊙ " + short + "  —  " + msg[:80], fg=ACCENT
        )

        for item in self.commit_files_tree.get_children():
            self.commit_files_tree.delete(item)
        self._clear_commit_diff()

        threading.Thread(
            target=self._bg_load_commit_files,
            args=(self.selected_repo["path"], commit_hash),
            daemon=True
        ).start()

    # ── Staging panel helpers ─────────────────

    def _show_staging_panel(self):
        if not self.selected_repo:
            return
        path = self.selected_repo["path"]
        rc, out, _ = run_git(["status", "--porcelain"], path)
        changes = []
        if rc == 0:
            for line in out.splitlines():
                line = line.lstrip('\ufeff')
                if len(line) > 2:
                    st = line[:2].strip() or "?"
                    fn = line[2:].lstrip()
                    if fn.startswith('"') and fn.endswith('"'):
                        fn = fn[1:-1]
                    changes.append((st, fn))

        for w in self._stg_inner.winfo_children():
            w.destroy()
        self._stg_check_vars.clear()

        for st, fn in changes:
            var = tk.BooleanVar(value=True)
            color = {"M": YELLOW, "A": GREEN, "D": RED, "??": FG2}.get(st, FG)
            row = tk.Frame(self._stg_inner, bg=BG2)
            row.pack(fill="x", pady=1, padx=4)
            tk.Checkbutton(row, variable=var, bg=BG2, fg=FG,
                           activebackground=BG2, selectcolor=BG3,
                           relief="flat").pack(side="left")
            lbl_text = st + "  " + fn
            tk.Label(row, text=lbl_text, bg=BG2, fg=color,
                     font=FONT_SM, anchor="w").pack(side="left")
            self._stg_check_vars.append((var, st, fn))

        self._stg_canvas.update_idletasks()
        self._stg_canvas.configure(
            scrollregion=self._stg_canvas.bbox("all"))
        self._staging_panel.pack(fill="both", expand=False,
                                 before=self.commit_files_tree.master.master)
        for item in self.commit_files_tree.get_children():
            self.commit_files_tree.delete(item)
        for st, fn in changes:
            tag = st if st in ("M", "A", "D", "R", "??") else "M"
            self.commit_files_tree.insert("", "end", values=(st, fn), tags=(tag,))
        self._clear_commit_diff()

    def _stage_select_all(self):
        for var, _, _ in self._stg_check_vars:
            var.set(True)

    def _stage_select_none(self):
        for var, _, _ in self._stg_check_vars:
            var.set(False)

    def _do_commit(self):
        if not self.selected_repo:
            return
        msg = self._commit_msg_text.get("1.0", "end").strip()
        if not msg:
            messagebox.showwarning("Commit", "Please enter a commit message.")
            return
        selected = [(st, fn) for var, st, fn in self._stg_check_vars
                    if var.get()]
        if not selected:
            messagebox.showwarning("Commit", "No files selected for commit.")
            return
        path = self.selected_repo["path"]

        def _bg():
            errors = []
            for st, fn in selected:
                rc_a, o_a, e_a = run_git(
                    ["add", "--force", "--", fn], path)
                if rc_a != 0:
                    errors.append(
                        "git add '" + fn + "': " + (e_a or o_a))
            if errors:
                emsg = "\n".join(errors)
                self.after(0, self._log,
                           "git add failed: " + emsg, "error")
                self.after(0, messagebox.showerror,
                           "git add failed", emsg)
                return
            rc, out, err = run_git(["commit", "-m", msg], path)
            if rc == 0:
                self.after(0, self._log,
                           "Committed: " + msg[:60], "success")
                self.after(0, self._commit_msg_text.delete,
                           "1.0", "end")
                self.after(0, self._staging_panel.pack_forget)
                self.after(0, self._load_detail_tabs)
            else:
                full = err or out or "unknown error"
                self.after(0, self._log,
                           "Commit failed: " + full, "error")
                self.after(0, messagebox.showerror,
                           "Commit failed", full)

        threading.Thread(target=_bg, daemon=True).start()

    def _bg_load_commit_files(self, repo_path, commit_hash):
        files = get_commit_files(repo_path, commit_hash)
        self.after(0, self._populate_commit_files, files)

    def _populate_commit_files(self, files):
        for item in self.commit_files_tree.get_children():
            self.commit_files_tree.delete(item)
        for st, fp in files:
            tag = st[0] if st and st[0] in ("M", "A", "D", "R", "C") else "M"
            self.commit_files_tree.insert("", "end", values=(st, fp), tags=(tag,))

    def _on_commit_file_select(self, event=None):
        sel = self.commit_files_tree.selection()
        if not sel or not self.selected_repo:
            return
        values = self.commit_files_tree.item(sel[0], "values")
        if not values or len(values) < 2:
            return
        filepath = values[1]

        if self._commit_diff_job:
            self.after_cancel(self._commit_diff_job)
        self._commit_diff_job = self.after(
            80, self._load_commit_diff_async, filepath
        )

    def _load_commit_diff_async(self, filepath):
        self._commit_diff_job = None
        repo_path   = self.selected_repo["path"]
        commit_hash = self._selected_commit_hash
        self.commit_diff_file_label.config(text=f"  ⊟  {filepath}", fg=ACCENT)
        self.commit_diff_stat_label.config(text="loading…", fg=FG2)
        self._set_commit_diff_loading()
        threading.Thread(
            target=self._bg_load_commit_diff,
            args=(repo_path, commit_hash, filepath),
            daemon=True
        ).start()

    def _bg_load_commit_diff(self, repo_path, commit_hash, filepath):
        if commit_hash is None:
            diff = get_file_diff(repo_path, filepath)
        else:
            diff = get_commit_file_diff(repo_path, commit_hash, filepath)
        self.after(0, self._render_commit_diff, diff, filepath)

    def _set_commit_diff_loading(self):
        for widget, txt in ((self.commit_diff_text, "  Loading…"),
                            (self.commit_diff_gutter, "")):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            if txt:
                widget.insert("end", txt, "meta")
            widget.configure(state="disabled")

    def _clear_commit_diff(self):
        self.commit_diff_file_label.config(
            text="  Select a file above to see its diff", fg=FG2
        )
        self.commit_diff_stat_label.config(text="")
        for widget in (self.commit_diff_text, self.commit_diff_gutter):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.configure(state="disabled")

    def _render_commit_diff(self, diff_raw: str, filepath: str):
        """Render unified diff for a commit file into the commit diff panel."""
        self.commit_diff_text.configure(state="normal")
        self.commit_diff_gutter.configure(state="normal")
        self.commit_diff_text.delete("1.0", "end")
        self.commit_diff_gutter.delete("1.0", "end")

        added = removed = old_ln = new_ln = 0
        for raw in diff_raw.splitlines():
            if raw.startswith("@@"):
                try:
                    tok = raw.split(" ")
                    old_ln = abs(int(tok[1].split(",")[0]))
                    new_ln = abs(int(tok[2].split(",")[0]))
                except Exception:
                    old_ln = new_ln = 0
                gutter, tag = "   ···   \n", "hunk"
            elif raw.startswith("+") and not raw.startswith("+++"):
                gutter = f"     {new_ln:>4}\n"; new_ln += 1; added += 1; tag = "add"
            elif raw.startswith("-") and not raw.startswith("---"):
                gutter = f"{old_ln:>4}     \n"; old_ln += 1; removed += 1; tag = "del"
            elif (raw.startswith("---") or raw.startswith("+++")
                  or raw.startswith("diff ") or raw.startswith("index ")
                  or raw.startswith("new file") or raw.startswith("old mode")
                  or raw.startswith("new mode") or raw.startswith("deleted file")
                  or raw.startswith("similarity") or raw.startswith("rename")):
                gutter, tag = "          \n", "meta"
            else:
                gutter = f"{old_ln:>4}  {new_ln:>4}\n"; old_ln += 1; new_ln += 1; tag = "normal"
            self.commit_diff_gutter.insert("end", gutter, tag)
            self.commit_diff_text.insert("end", raw + "\n", tag)

        self.commit_diff_text.configure(state="disabled")
        self.commit_diff_gutter.configure(state="disabled")
        self.commit_diff_text.yview_moveto(0)
        self.commit_diff_gutter.yview_moveto(0)

        stat_parts = []
        if added:   stat_parts.append(f"+{added}")
        if removed: stat_parts.append(f"-{removed}")
        stat_str = "  ".join(stat_parts) if stat_parts else "no changes"
        self.commit_diff_stat_label.config(
            text=stat_str,
            fg=GREEN if not removed else (RED if not added else YELLOW)
        )

    # ── Diff loading (working-tree) ───────────

    def _on_file_select(self, event=None):
        sel = self.changes_tree.selection()
        if not sel or not self.selected_repo:
            return
        values = self.changes_tree.item(sel[0], "values")
        if not values or len(values) < 2:
            return
        filepath = values[1]

        if self._diff_job:
            self.after_cancel(self._diff_job)
        self._diff_job = self.after(80, self._load_diff_async, filepath)

    def _load_diff_async(self, filepath):
        self._diff_job = None
        repo_path = self.selected_repo["path"]
        self.diff_file_label.config(text=f"  ⊟  {filepath}", fg=ACCENT)
        self.diff_stat_label.config(text="loading…", fg=FG2)
        self._set_diff_loading()
        threading.Thread(
            target=self._bg_load_diff,
            args=(repo_path, filepath),
            daemon=True
        ).start()

    def _bg_load_diff(self, repo_path, filepath):
        diff = get_file_diff(repo_path, filepath)
        self.after(0, self._render_diff, diff, filepath)

    def _set_diff_loading(self):
        for widget, txt in ((self.diff_text, "  Loading…"), (self.diff_gutter, "")):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            if txt:
                widget.insert("end", txt, "meta")
            widget.configure(state="disabled")

    def _clear_diff(self):
        self.diff_file_label.config(
            text="  Select a file above to see its diff", fg=FG2
        )
        self.diff_stat_label.config(text="")
        for widget in (self.diff_text, self.diff_gutter):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.configure(state="disabled")

    def _render_diff(self, diff_raw: str, filepath: str):
        """Parse unified diff and render with colour + line numbers."""
        self.diff_text.configure(state="normal")
        self.diff_gutter.configure(state="normal")
        self.diff_text.delete("1.0", "end")
        self.diff_gutter.delete("1.0", "end")

        added   = 0
        removed = 0
        old_ln  = 0
        new_ln  = 0

        lines = diff_raw.splitlines()

        for raw in lines:
            # ── classify line ──────────────────
            if raw.startswith("@@"):
                # @@ -old_start[,count] +new_start[,count] @@
                try:
                    tok = raw.split(" ")
                    old_ln = abs(int(tok[1].split(",")[0]))
                    new_ln = abs(int(tok[2].split(",")[0]))
                except Exception:
                    old_ln = new_ln = 0
                gutter = "   ···   \n"
                tag    = "hunk"

            elif raw.startswith("+") and not raw.startswith("+++"):
                gutter = f"     {new_ln:>4}\n"
                new_ln += 1
                added  += 1
                tag    = "add"

            elif raw.startswith("-") and not raw.startswith("---"):
                gutter = f"{old_ln:>4}     \n"
                old_ln += 1
                removed += 1
                tag    = "del"

            elif raw.startswith("---") or raw.startswith("+++") \
                    or raw.startswith("diff ") or raw.startswith("index ") \
                    or raw.startswith("new file") or raw.startswith("old mode") \
                    or raw.startswith("new mode") or raw.startswith("deleted file") \
                    or raw.startswith("similarity") or raw.startswith("rename"):
                gutter = "          \n"
                tag    = "meta"

            else:
                # context line
                gutter = f"{old_ln:>4}  {new_ln:>4}\n"
                old_ln += 1
                new_ln += 1
                tag    = "normal"

            self.diff_gutter.insert("end", gutter, tag)
            self.diff_text.insert("end", raw + "\n", tag)

        self.diff_text.configure(state="disabled")
        self.diff_gutter.configure(state="disabled")
        self.diff_text.yview_moveto(0)
        self.diff_gutter.yview_moveto(0)

        # update stat label
        stat_parts = []
        if added:   stat_parts.append(f"+{added}")
        if removed: stat_parts.append(f"-{removed}")
        stat_str = "  ".join(stat_parts) if stat_parts else "no changes"
        self.diff_stat_label.config(
            text=stat_str,
            fg=GREEN if not removed else (RED if not added else YELLOW)
        )

    # ── Git operations ────────────────────────

    def _repo_op(self, op):
        if not self.selected_repo:
            messagebox.showinfo("No selection", "Select a repository first.")
            return
        self._queue_op(op, [self.selected_repo])

    def _fetch_all(self): self._queue_op("fetch", self.repos)

    def _pull_all(self):
        if messagebox.askyesno("Pull All", f"Pull {len(self.repos)} repositories?"):
            self._queue_op("pull", self.repos)

    def _push_all(self):
        if messagebox.askyesno("Push All", f"Push {len(self.repos)} repositories?"):
            self._queue_op("push", self.repos)

    def _queue_op(self, op, repos):
        self._op_queue.put((op, list(repos)))

    def _start_queue_processor(self):
        def worker():
            while True:
                op, repos = self._op_queue.get()
                self.after(0, self._show_progress, True, f"{op.title()}ing…")
                for repo in repos:
                    self._do_git_op(op, repo)
                self.after(0, self._show_progress, False, "Ready")
                self.after(0, self._refresh_all_status)
        threading.Thread(target=worker, daemon=True).start()

    def _show_progress(self, running, msg):
        self.status_var.set(msg)
        if running:
            self.progress.pack(side="right", padx=4, pady=8)
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def _do_git_op(self, op, repo):
        path = repo["path"]
        name = repo["name"]
        cmds = {
            "fetch": ["fetch", "--all", "--prune"],
            "pull":  ["pull", "--ff-only"],
            "push":  ["push"],
        }
        cmd = cmds.get(op)
        if not cmd:
            return
        self.after(0, self._log, f"$ git {' '.join(cmd)}  ({name})", "cmd")
        rc, out, err = run_git(cmd, path, timeout=120)
        if rc == 0:
            self.after(0, self._log, f"  ✓ {out or op + ' OK'}", "success")
        else:
            self.after(0, self._log, f"  ✗ {err or out or 'error'}", "error")

    # ── Status refresh ────────────────────────

    def _refresh_all_status(self):
        repos = list(self.repos)
        threading.Thread(target=self._bg_refresh, args=(repos,), daemon=True).start()

    def _bg_refresh(self, repos):
        for repo in repos:
            if not os.path.isdir(os.path.join(repo["path"], ".git")):
                repo["info"] = {"status": "unknown", "branch": "not a repo"}
                continue
            repo["info"] = get_repo_info(repo["path"])
        self.after(0, self._rebuild_tree)
        if self.selected_repo:
            self.after(0, self._update_detail_header)

    # ── Add / Remove ──────────────────────────

    def _add_repo(self):
        path = filedialog.askdirectory(title="Select Git Repository Folder")
        if not path:
            return
        path = os.path.normpath(path)
        if not os.path.isdir(os.path.join(path, ".git")):
            messagebox.showerror("Not a git repo",
                                 "The selected folder is not a git repository.")
            return
        if any(r["path"] == path for r in self.repos):
            messagebox.showinfo("Already added", "Repository already in list.")
            return
        name  = os.path.basename(path)
        group = simpledialog.askstring("Group", "Enter group name (optional):",
                                       parent=self) or ""
        self.repos.append({"name": name, "path": path, "group": group, "info": {}})
        self._save_config()
        self._rebuild_tree()
        self._refresh_all_status()
        self._log(f"Added: {name} ({path})", "info")

    def _remove_repo(self):
        if not self.selected_repo:
            return
        name = self.selected_repo["name"]
        if not messagebox.askyesno("Remove",
                                   f"Remove '{name}' from list?\n(Files won't be deleted)"):
            return
        self.repos = [r for r in self.repos
                      if r["path"] != self.selected_repo["path"]]
        self.selected_repo = None
        self._save_config()
        self._rebuild_tree()
        self.detail_name.config(text="← Select a repository")
        self.detail_branch.config(text="")
        self.detail_status.config(text="")
        self.detail_url.config(text="")
        if hasattr(self, "left_branch_tree"):
            for item in self.left_branch_tree.get_children():
                self.left_branch_tree.delete(item)
        self._clear_diff()

    # ── Left Branch Tree Methods ──────────────────

    def _create_branch(self):
        if not self.selected_repo:
            messagebox.showinfo("No selection", "Select a repository first.")
            return
        new_branch = simpledialog.askstring("Create Branch", "Enter new branch name:", parent=self)
        if not new_branch:
            return
        
        path = self.selected_repo["path"]
        rc, out, err = run_git(["checkout", "-b", new_branch], path)
        if rc == 0:
            self._log(f"Created and checked out branch '{new_branch}'", "success")
            self._load_detail_tabs()
            self._refresh_all_status()
        else:
            self._log(f"Failed to create branch '{new_branch}': {err or out}", "error")
            messagebox.showerror("Error", err or out)

    def _on_left_branch_right_click(self, event):
        item = self.left_branch_tree.identify_row(event.y)
        if not item:
            return
        self.left_branch_tree.selection_set(item)
        tags = self.left_branch_tree.item(item, "tags")
        if "group" in tags:
            return
            
        bname = tags[1]
        btype = tags[2]
        
        menu = tk.Menu(self, tearoff=0, bg=BG3, fg=FG,
                       activebackground=ACCENT, activeforeground=FG,
                       font=FONT_SM, bd=0, relief="flat")
        
        if btype == "local":
            menu.add_command(label="✓  Checkout", command=lambda: self._checkout_branch(bname))
            menu.add_separator()
            menu.add_command(label="✕  Delete", command=lambda: self._delete_branch(bname, False))
            menu.add_command(label="✕  Force Delete", command=lambda: self._delete_branch(bname, True))
        else:
            menu.add_command(label="✓  Checkout (Track)", command=lambda: self._checkout_remote_branch(bname))
            
        menu.post(event.x_root, event.y_root)

    def _on_left_branch_double_click(self, event):
        item = self.left_branch_tree.identify_row(event.y)
        if not item:
            return
        tags = self.left_branch_tree.item(item, "tags")
        if "group" in tags:
            return
            
        bname = tags[1]
        btype = tags[2]
        
        if btype == "local":
            self._checkout_branch(bname)
        else:
            self._checkout_remote_branch(bname)

    def _checkout_branch(self, bname):
        if not self.selected_repo: return
        path = self.selected_repo["path"]
        rc, out, err = run_git(["checkout", bname], path)
        if rc == 0:
            self._log(f"Checked out branch '{bname}'", "success")
            self._load_detail_tabs()
            self._refresh_all_status()
        else:
            self._log(f"Failed to checkout '{bname}': {err or out}", "error")
            messagebox.showerror("Error", err or out)

    def _checkout_remote_branch(self, bname):
        if not self.selected_repo: return
        path = self.selected_repo["path"]
        local_name = bname.split("/", 1)[-1] if "/" in bname else bname
        rc, out, err = run_git(["checkout", "-t", bname], path)
        if rc == 0:
            self._log(f"Checked out tracking branch '{local_name}'", "success")
            self._load_detail_tabs()
            self._refresh_all_status()
        else:
            self._log(f"Failed to checkout remote '{bname}': {err or out}", "error")
            messagebox.showerror("Error", err or out)

    def _delete_branch(self, bname, force=False):
        if not self.selected_repo: return
        if not messagebox.askyesno("Delete Branch", f"Are you sure you want to delete '{bname}'?"):
            return
        path = self.selected_repo["path"]
        flag = "-D" if force else "-d"
        rc, out, err = run_git(["branch", flag, bname], path)
        if rc == 0:
            self._log(f"Deleted branch '{bname}'", "success")
            self._load_detail_tabs()
        else:
            self._log(f"Failed to delete branch '{bname}': {err or out}", "error")
            messagebox.showerror("Error", err or out)

    # ── Context menu ──────────────────────────

    def _on_repo_right_click(self, event):
        item = self.repo_tree.identify_row(event.y)
        if not item:
            return
        self.repo_tree.selection_set(item)
        if "group" in self.repo_tree.item(item, "tags"):
            return
        menu = tk.Menu(self, tearoff=0, bg=BG3, fg=FG,
                       activebackground=ACCENT, activeforeground=FG,
                       font=FONT_SM, bd=0, relief="flat")
        menu.add_command(label="⟳  Fetch",        command=lambda: self._repo_op("fetch"))
        menu.add_command(label="↓  Pull",          command=lambda: self._repo_op("pull"))
        menu.add_command(label="↑  Push",          command=lambda: self._repo_op("push"))
        menu.add_separator()
        menu.add_command(label="📁  Open Folder",  command=self._open_folder)
        menu.add_command(label="⌨  Terminal",     command=self._open_terminal)
        menu.add_separator()
        menu.add_command(label="✕  Remove",        command=self._remove_repo)
        menu.post(event.x_root, event.y_root)

    # ── Misc helpers ──────────────────────────

    def _open_folder(self):
        if self.selected_repo:
            os.startfile(self.selected_repo["path"])

    def _open_terminal(self):
        if not self.selected_repo:
            return
        path = self.selected_repo["path"]
        try:
            subprocess.Popen(["cmd.exe", "/k", f"cd /d {path}"],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _log(self, msg, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console_text.configure(state="normal")
        self.console_text.insert("end", f"[{ts}] {msg}\n", tag)
        self.console_text.see("end")
        self.console_text.configure(state="disabled")
        self.log_var.set(msg[:120])


# ──────────────────────────────────────────────

if __name__ == "__main__":
    app = GitManager()
    app.mainloop()
