"""Modal confirmations that share the main window's metal-and-glass theme."""
import tkinter as tk
from tkinter import ttk

from .theme import BG, GOLD, TEXT, BLUE, ClientChrome, Divider, dark_titlebar


def _show(title, message, parent, confirm=False, error=False):
    window = tk.Toplevel(parent)
    window.withdraw()
    window.title(title)
    window.configure(bg=BG)
    window.transient(parent)
    window.resizable(False, False)
    chrome = ClientChrome(window)
    chrome.pack(fill="both", expand=True)
    body = chrome.content
    ttk.Label(body, text=title, foreground="#d89b72" if error else GOLD,
              font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", pady=(4, 8))
    Divider(body).pack(fill="x", pady=(0, 12))
    label = ttk.Label(body, text=message, foreground=TEXT, wraplength=480, justify="left")
    label.pack(fill="x", pady=(0, 20))
    actions = ttk.Frame(body)
    actions.pack(fill="x", side="bottom")
    result = [False]

    def finish(value=False):
        result[0] = value
        window.grab_release()
        window.destroy()

    if confirm:
        ttk.Button(actions, text="取消", command=finish).pack(side="left")
    primary = ttk.Button(actions, text="确认执行" if confirm else "知道了", style="Accent.TButton",
                         command=lambda: finish(True))
    primary.pack(side="right")
    window.update_idletasks()
    height = max(230, body.winfo_reqheight() + 62)
    width = 560
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.protocol("WM_DELETE_WINDOW", finish)
    window.bind("<Escape>", lambda _: finish())
    if not confirm:
        window.bind("<Return>", lambda _: finish(True))
    window.deiconify()
    dark_titlebar(window)
    window.grab_set()
    # An irreversible confirmation receives no default Enter shortcut.
    window.focus_set() if confirm else primary.focus_set()
    parent.wait_window(window)
    if parent.winfo_exists():
        parent.focus_set()
    return result[0]


def askyesno(title, message, *, parent, **_):
    return _show(title, message, parent, confirm=True)


def showinfo(title, message, *, parent, **_):
    return _show(title, message, parent)


def showerror(title, message, *, parent, **_):
    return _show(title, message, parent, error=True)
