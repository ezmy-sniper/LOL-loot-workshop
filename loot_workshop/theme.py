"""Original procedural Hextech-style surfaces; no proprietary game assets."""
import ctypes
import os
import math
import tkinter as tk
from tkinter import ttk

BG = "#010a13"
PANEL = "#06141e"
TEXT = "#cdbe91"
MUTED = "#8e9287"
GOLD = "#c8aa6e"
BLUE = "#0ac8b9"
EDGE = "#785a28"


def icon_pixels(size):
    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            u, v = (x + .5) / size * 2 - 1, (y + .5) / size * 2 - 1
            radius = math.hypot(u, v)
            color, alpha = BG, 255
            if radius > .98:
                alpha = 0
            elif .83 < radius < .94:
                color = blend(GOLD, EDGE, (v + 1) / 2)
            elif .73 < radius < .77:
                color = GOLD
            elif abs(u) / .44 + abs(v) / .66 < 1:
                color = "#86e8d7" if u < 0 else "#08788c"
                if abs(u) < .035:
                    color = "#d3f6dd"
            elif abs(u) / .50 + abs(v) / .73 < 1:
                color = BLUE
            row.append((*tuple(int(color[n:n+2], 16) for n in (1, 3, 5)), alpha))
        pixels.append(row)
    return pixels


def window_icon(root):
    pixels = icon_pixels(48)
    image = tk.PhotoImage(master=root, width=48, height=48)
    for y, row in enumerate(pixels):
        for x, (r, g, b, alpha) in enumerate(row):
            if alpha:
                image.put(f"#{r:02x}{g:02x}{b:02x}", to=(x, y))
    root.iconphoto(True, image)
    root._app_icon = image


def blend(a, b, amount):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(f"{round(int(a[n:n+2],16)*(1-amount)+int(b[n:n+2],16)*amount):02x}" for n in (0, 2, 4))


def surface(root, width, height, accent=GOLD, active=False, pressed=False, disabled=False):
    """Small nine-slice texture with bevelled metal edges and a dark glass face."""
    image = tk.PhotoImage(master=root, width=width, height=height)
    top, bottom = ("#102d38", "#041019") if active else ("#0a1e29", "#030b12")
    if pressed:
        top, bottom = "#020a10", "#0b1d25"
    if disabled:
        top, bottom, accent = "#0a1016", "#050b11", "#34403e"
    for y in range(height):
        color = blend(top, bottom, y / (height - 1))
        if y == 0:
            color = blend(accent, "#f0e4bd", .24) if not disabled else accent
        elif y == height - 1:
            color = blend(accent, "#010a13", .46)
        elif y in (1, height - 2):
            color = blend(accent, bottom, .72)
        row = [color] * width
        if 1 < y < height - 2:
            row[0] = blend(accent, BG, .2)
            row[-1] = blend(accent, BG, .42)
            row[1] = row[-2] = blend(accent, bottom, .8)
        if y in (0, height - 1):
            row[0] = row[-1] = BG
        image.put("{" + " ".join(row) + "}", to=(0, y))
    return image


def checkbox(root, selected=False, disabled=False):
    image = tk.PhotoImage(master=root, width=20, height=20)
    image.put(BG, to=(0, 0, 20, 20))
    edge = "#39413c" if disabled else EDGE
    image.put(edge, to=(2, 2, 18, 18))
    image.put("#071923", to=(3, 3, 17, 17))
    image.put("#243d40" if selected else "#0a202b", to=(4, 4, 16, 16))
    if selected:
        color = "#68766b" if disabled else BLUE
        for x, y in ((5, 10), (6, 11), (7, 12), (8, 11), (9, 10), (10, 9), (11, 8), (12, 7), (13, 6)):
            image.put(color, to=(x, y, x + 2, y + 2))
    return image


def install(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    images = []
    for name, accent in (("Hex.Button", GOLD), ("Hex.Primary", BLUE), ("Hex.Card", EDGE), ("Hex.Tab", EDGE)):
        states = [surface(root, 48, 64 if "Card" in name else 24, accent, **kw)
                  for kw in ({}, {"active": True}, {"pressed": True}, {"disabled": True})]
        images.extend(states)
        element = name + ".surface"
        style.element_create(element, "image", states[0],
                             ("disabled", states[3]), ("pressed", states[2]),
                             ("active", states[1]), ("selected", states[1]), border=3, sticky="nsew")
        if "Card" in name:
            style.layout("Card.TFrame", [(element, {"sticky": "nsew"})])
        elif "Tab" in name:
            style.layout("TNotebook.Tab", [(element, {"sticky": "nsew", "children": [
                ("Notebook.padding", {"sticky": "nsew", "children": [("Notebook.label", {"sticky": "nsew"})]})]})])
        else:
            target = "Accent.TButton" if "Primary" in name else "TButton"
            style.layout(target, [(element, {"sticky": "nsew", "children": [
                ("Button.focus", {"sticky": "nsew", "children": [
                    ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})]})])
    checks = [checkbox(root), checkbox(root, True), checkbox(root, False, True), checkbox(root, True, True)]
    images.extend(checks)
    style.element_create("Hex.Check.indicator", "image", checks[0],
                         ("disabled", "selected", checks[3]), ("disabled", checks[2]),
                         ("selected", checks[1]), width=22, sticky="w")
    style.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nsew", "children": [
        ("Hex.Check.indicator", {"side": "left", "sticky": "w"}),
        ("Checkbutton.label", {"side": "left", "sticky": "w"})]})])
    style.configure(".", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 10),
                    bordercolor=EDGE, lightcolor="#3c3728", darkcolor="#030b12", focuscolor=GOLD)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL, borderwidth=1, relief="solid")
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Card.TLabel", background="#081822", foreground=TEXT)
    style.configure("Value.TLabel", background="#06131c", foreground=GOLD, font=("Georgia", 25, "bold"))
    style.configure("Title.TLabel", foreground=GOLD, font=("Microsoft YaHei UI", 20, "bold"))
    style.configure("TButton", padding=(14, 9), foreground=TEXT, borderwidth=0)
    style.map("TButton", foreground=[("disabled", "#59605b"), ("active", "#f0e6cf")])
    style.configure("Utility.TButton", padding=(12, 4), font=("Microsoft YaHei UI", 9))
    style.configure("Accent.TButton", padding=(20, 9), foreground="#d5f3ef", font=("Microsoft YaHei UI", 10, "bold"))
    style.map("Accent.TButton", foreground=[("disabled", "#53645e"), ("active", "#effffc")])
    style.configure("TEntry", fieldbackground="#020e18", foreground=TEXT, padding=7, insertcolor=GOLD, borderwidth=1)
    style.configure("TSpinbox", fieldbackground="#020e18", foreground=TEXT, padding=5, arrowcolor=GOLD, background=PANEL)
    style.map("TEntry", bordercolor=[("focus", GOLD)])
    style.configure("TCheckbutton", background=BG, foreground=TEXT, padding=3)
    style.map("TCheckbutton", background=[("active", BG)], foreground=[("disabled", "#62675f"), ("active", GOLD)])
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34,
                    borderwidth=0, lightcolor=PANEL, darkcolor=PANEL)
    style.configure("Treeview.Heading", background="#0e1b23", foreground=GOLD, padding=8,
                    bordercolor="#463b25", lightcolor="#52442a", darkcolor="#0b1720", relief="flat")
    style.map("Treeview", background=[("selected", "#123440")], foreground=[("selected", "#f0e6d2")])
    style.map("Treeview.Heading", background=[("active", "#172b32")])
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", padding=(22, 8), foreground=MUTED)
    style.map("TNotebook.Tab", foreground=[("selected", GOLD), ("active", TEXT)])
    style.configure("Horizontal.TProgressbar", troughcolor="#07131b", background="#039eaa", bordercolor=EDGE,
                    lightcolor="#22d9ca", darkcolor="#005a70", borderwidth=1, thickness=8)
    style.configure("Vertical.TScrollbar", background="#4b412c", troughcolor="#030d15", arrowcolor=GOLD,
                    bordercolor=BG, lightcolor="#785a28", darkcolor="#30291e", width=12)
    style.map("Vertical.TScrollbar", background=[("active", EDGE)])
    root._hextech_images = images  # Tk image elements require live Python references.
    return style


def dark_titlebar(root):
    if os.name == "nt":
        try:
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except (AttributeError, OSError):
            pass


class ClientChrome(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, bg=BG, highlightthickness=0)
        self.content = ttk.Frame(self, padding=(22, 10))
        self.window = self.create_window(14, 16, anchor="nw", window=self.content)
        self.bind("<Configure>", self.draw)

    def draw(self, event):
        w, h = event.width, event.height
        self.delete("chrome")
        # Dark blue edge material and original, understated etched geometry.
        for y in range(0, h, 3):
            self.create_line(0, y, w, y, fill=blend("#0b2430", BG, min(1, y / max(1, h) * 1.7)), tags="chrome")
        for offset in range(20, max(w, h), 96):
            self.create_line(0, offset, offset, 0, fill="#10232a", tags="chrome")
            self.create_line(w-offset, h, w, h-offset, fill="#0b1c24", tags="chrome")
        self.create_rectangle(1, 1, w-2, h-2, outline=EDGE, tags="chrome")
        self.create_rectangle(4, 4, w-5, h-5, outline="#23312f", tags="chrome")
        self.create_line(1, 1, w-2, 1, fill=GOLD, tags="chrome")
        center = w / 2
        self.create_polygon(center-15, 1, center, 15, center+15, 1, fill=BG, outline=EDGE, width=2, tags="chrome")
        self.create_line(center-7, 2, center, 8, center+7, 2, fill=GOLD, width=2, tags="chrome")
        for x, y, dx, dy in ((8, 8, 1, 1), (w-9, 8, -1, 1), (8, h-9, 1, -1), (w-9, h-9, -1, -1)):
            self.create_line(x, y+21*dy, x, y, x+21*dx, y, fill=GOLD, tags="chrome")
        self.itemconfigure(self.window, width=max(1, w-28), height=max(1, h-30))
        self.tag_lower("chrome")


class Crest(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, width=55, height=55, bg=BG, highlightthickness=0)
        self.create_oval(3, 3, 51, 51, outline=EDGE, width=2)
        self.create_oval(7, 7, 47, 47, outline=GOLD)
        self.create_polygon(27, 11, 39, 27, 27, 43, 15, 27, outline=BLUE, fill="#073844", width=2)
        self.create_polygon(27, 17, 32, 27, 27, 37, 22, 27, fill="#74e3d4", outline="")
        self.create_line(27, 12, 27, 42, fill="#d7f3df")


class Divider(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=BG, height=12, highlightthickness=0)
        self.bind("<Configure>", self.draw)

    def draw(self, event):
        self.delete("all")
        self.create_line(0, 5, event.width, 5, fill="#453b29")
        self.create_line(0, 5, min(event.width*.4, 220), 5, fill=EDGE)
        self.create_polygon(0, 5, 4, 1, 8, 5, 4, 9, fill=GOLD, outline="")
