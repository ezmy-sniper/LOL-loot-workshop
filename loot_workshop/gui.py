"""Native Tk interface. All client I/O runs outside the UI thread."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from . import __version__
from . import dialogs as messagebox
from .client import LeagueClient, is_admin, restart_elevated
from .core import SHARD, LootError, Rules, essence, inventory_map, make_plan
from .demo import DemoClient
from .engine import Runner, history_directory
from .theme import BG, PANEL, TEXT, MUTED, GOLD, BLUE, ClientChrome, Crest, Divider, install, dark_titlebar, window_icon


class App:
    def __init__(self, root: tk.Tk, demo=False):
        self.root, self.demo = root, demo
        self.client, self.account, self.plan = None, None, None
        self.inventory, self.report = [], None
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy, self.closing = None, False
        self.controls = []
        self.threshold = tk.StringVar(value="630")
        self.reroll = tk.BooleanVar(value=True)
        self.allow_unlock = tk.BooleanVar(value=False)
        self.search = tk.StringVar()
        self.status = tk.StringVar(value="未连接 · 请先打开英雄联盟客户端")
        self.subtitle = tk.StringVar(value="先查看清单，再处理碎片。")
        self.connection = tk.StringVar(value="未连接")
        self.root.title(f"LoL Loot Workshop · 英雄碎片工坊 {__version__}")
        self.root.geometry("1180x860")
        self.root.minsize(940, 720)
        self.root.configure(bg=BG)
        window_icon(self.root)
        self._style()
        self._build()
        dark_titlebar(self.root)
        for variable in (self.threshold, self.reroll, self.allow_unlock):
            variable.trace_add("write", self._invalidate)
        self.search.trace_add("write", lambda *_: self.render_rows())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.poll)
        if demo:
            self.root.after(150, self.load_demo)

    def _style(self):
        self.style = install(self.root)

    def button(self, parent, title, command, **kwargs):
        button = ttk.Button(parent, text=title, command=command, **kwargs)
        self.controls.append(button)
        return button

    def _build(self):
        self.chrome = ClientChrome(self.root)
        self.chrome.pack(fill="both", expand=True)
        outer = self.chrome.content
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(6, weight=1)
        heading = ttk.Frame(outer)
        heading.grid(row=0, column=0, sticky="ew")
        Crest(heading).pack(side="left", padx=(0, 14))
        titles = ttk.Frame(heading)
        titles.pack(side="left")
        ttk.Label(titles, text="战利品  /  合成", style="Muted.TLabel", font=("Microsoft YaHei UI", 9)).pack(anchor="w")
        ttk.Label(titles, text="英雄碎片工坊", style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, textvariable=self.connection, foreground=BLUE).pack(side="right")
        intro = ttk.Frame(outer)
        intro.grid(row=1, column=0, sticky="ew", pady=(2, 6))
        ttk.Label(intro, textvariable=self.subtitle, style="Muted.TLabel").pack(anchor="w")
        Divider(intro).pack(fill="x")

        toolbar = ttk.Frame(outer)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        self.button(toolbar, "连接客户端", self.connect).pack(side="left", padx=(0, 8))
        self.button(toolbar, "刷新库存 / 生成预览", self.refresh).pack(side="left", padx=(0, 8))
        self.button(toolbar, "选择 lockfile", self.choose_lockfile).pack(side="left")
        self.button(toolbar, "体验演示", self.load_demo).pack(side="right", padx=(8, 0))
        self.button(toolbar, "以管理员权限重启", self.elevate).pack(side="right")

        rules = ttk.Frame(outer)
        rules.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(rules, text="分解价值阈值").pack(side="left")
        spin = ttk.Spinbox(rules, from_=1, to=10000, textvariable=self.threshold, width=7)
        spin.pack(side="left", padx=(10, 14))
        self.controls.append(spin)
        check = ttk.Checkbutton(rules, text="低于阈值：每三个重随，分解所得，余数保留", variable=self.reroll)
        check.pack(side="left")
        self.controls.append(check)
        extra = ttk.Frame(outer)
        extra.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        unlock = ttk.Checkbutton(extra, text="接受重随可能自动解锁未拥有的英雄（这部分无法分解）", variable=self.allow_unlock)
        unlock.pack(side="left")
        self.controls.append(unlock)
        ttk.Label(extra, text="取消重随后，全部英雄碎片直接分解", style="Muted.TLabel").pack(side="right")

        cards = ttk.Frame(outer)
        cards.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        self.metrics = {}
        for index, (key, title) in enumerate((("reroll", "重随次数"), ("direct", "直接分解碎片"), ("keep", "保留碎片"), ("gain", "直接分解预计精萃"))):
            cards.columnconfigure(index, weight=1, uniform="cards")
            card = ttk.Frame(cards, style="Card.TFrame", padding=(18, 12))
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 6, 0 if index == 3 else 6))
            ttk.Label(card, text=title, style="Card.TLabel").pack(anchor="w")
            var = tk.StringVar(value="—")
            self.metrics[key] = var
            ttk.Label(card, textvariable=var, style="Value.TLabel").pack(anchor="w", pady=(5, 0))

        notebook = ttk.Notebook(outer)
        notebook.grid(row=6, column=0, sticky="nsew")
        inventory_tab = ttk.Frame(notebook, padding=(0, 12, 0, 0))
        log_tab = ttk.Frame(notebook, padding=(0, 12, 0, 0))
        notebook.add(inventory_tab, text="碎片清单")
        notebook.add(log_tab, text="执行记录")
        filter_bar = ttk.Frame(inventory_tab)
        filter_bar.pack(fill="x", pady=(0, 10))
        ttk.Label(filter_bar, text="搜索英雄").pack(side="left", padx=(0, 10))
        ttk.Entry(filter_bar, textvariable=self.search, width=23).pack(side="left")
        self.balance_label = ttk.Label(filter_bar, text="蓝色精萃 —", style="Muted.TLabel")
        self.balance_label.pack(side="right")
        table_frame = ttk.Frame(inventory_tab, style="Panel.TFrame", padding=1)
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "quantity", "value", "action", "detail")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse", height=5)
        for key, title, width in zip(columns, ("英雄", "数量", "单个分解价值", "处理方式", "计划详情"), (210, 70, 130, 110, 330)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=60, anchor="w" if key in ("name", "detail") else "center", stretch=key in ("name", "detail"))
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.tag_configure("reroll", foreground=BLUE)
        self.tree.tag_configure("direct", foreground=GOLD)
        self.tree.tag_configure("keep", foreground=MUTED)
        self.tree.tag_configure("even", background="#06141e")
        self.tree.tag_configure("odd", background="#081b25")
        self.log = tk.Text(log_tab, height=5, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                           font=("Microsoft YaHei UI", 10), relief="flat", padx=14, pady=12, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        bottom = ttk.Frame(outer)
        bottom.grid(row=7, column=0, sticky="ew", pady=(16, 0))
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(bottom)
        row.pack(fill="x")
        ttk.Label(row, textvariable=self.status, style="Muted.TLabel", wraplength=650).pack(side="left", fill="x", expand=True)
        self.stop_button = ttk.Button(row, text="完成当前组后停止", command=self.cancel, state="disabled")
        self.stop_button.pack(side="right", padx=(8, 0))
        self.execute_button = ttk.Button(row, text="执行预览计划", command=self.execute, style="Accent.TButton", state="disabled")
        self.execute_button.pack(side="right")
        links = ttk.Frame(outer)
        links.grid(row=8, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(links, text=f"v{__version__} · 本地连接 · { '管理员权限' if is_admin() else '标准权限' }", style="Muted.TLabel").pack(side="left")
        ttk.Button(links, text="导出本次结果", command=self.export_report, style="Utility.TButton").pack(side="right")
        ttk.Button(links, text="打开处理记录", command=self.open_history, style="Utility.TButton").pack(side="right", padx=8)

    def _invalidate(self, *_):
        if self.busy == "execute":
            return
        self.plan = None
        self.execute_button.configure(state="disabled")
        for var in self.metrics.values():
            var.set("—")
        self.status.set("规则已变化，请点击“刷新库存 / 生成预览”。")
        self.render_rows()

    def rules(self):
        try:
            return Rules(int(self.threshold.get()), self.reroll.get(), self.allow_unlock.get())
        except ValueError:
            raise LootError("阈值请输入整数。") from None

    def set_busy(self, mode):
        self.busy = mode
        for control in self.controls:
            control.configure(state="disabled" if mode else "normal")
        self.execute_button.configure(state="normal" if not mode and self.plan and self.plan.units else "disabled")
        self.stop_button.configure(state="normal" if mode == "execute" else "disabled")

    def background(self, function, mode):
        self.set_busy(mode)
        def work():
            try:
                value = function()
                self.events.put(("finished", value))
            except Exception as error:
                text = str(error) if isinstance(error, LootError) else "操作或记录保存失败，请核对客户端中的库存与本地文件权限。"
                self.events.put(("error", text))
        threading.Thread(target=work, daemon=False).start()

    def connect(self, lockfile=""):
        if self.busy:
            return
        try:
            rules = self.rules()
        except LootError as error:
            messagebox.showerror("规则无效", str(error), parent=self.root)
            return
        self.plan = None
        self.demo = False
        self.client, self.account = None, None
        self.connection.set("连接中…")
        self.status.set("正在读取本地客户端…")
        def work():
            client = LeagueClient.discover(lockfile)
            account, items = client.account(), client.inventory()
            return ("inventory", client, account, items, make_plan(items, rules), False)
        self.background(work, "connect")

    def choose_lockfile(self):
        path = filedialog.askopenfilename(title="选择客户端目录中的lockfile", filetypes=[("客户端连接文件", "lockfile"), ("全部文件", "*")])
        if path:
            self.connect(path)

    def refresh(self):
        if self.busy:
            return
        if self.client is None:
            self.connect()
            return
        try:
            rules = self.rules()
        except LootError as error:
            messagebox.showerror("规则无效", str(error), parent=self.root)
            return
        self.plan = None
        self.status.set("正在刷新库存…")
        client, demo = self.client, self.demo
        def work():
            account, items = client.account(), client.inventory()
            return ("inventory", client, account, items, make_plan(items, rules), demo)
        self.background(work, "connect")

    def load_demo(self):
        if self.busy:
            return
        try:
            client = DemoClient()
            items = client.inventory()
            self.show_inventory(client, client.account(), items, make_plan(items, self.rules()), True)
            self.append_log("演示模式已载入：使用内置合成数据，操作不会连接游戏客户端。")
        except LootError as error:
            messagebox.showerror("规则无效", str(error), parent=self.root)

    def show_inventory(self, client, account, items, plan, demo):
        self.client, self.account, self.inventory, self.plan, self.demo = client, account, items, plan, demo
        self.connection.set("离线演示" if demo else "客户端已连接")
        self.subtitle.set(account["name"] + (" · 离线演示，所有操作仅影响合成数据" if demo else " · 当前库存已读取"))
        for key, value in (("reroll", len(plan.groups)), ("direct", len(plan.direct)), ("keep", len(plan.leftovers)), ("gain", f"{plan.guaranteed_essence:,}")):
            self.metrics[key].set(str(value))
        self.balance_label.configure(text=f"蓝色精萃 {essence(items):,}")
        self.status.set("预览已生成 · 重随收益为随机结果，未计入预计精萃" if plan.units else "没有符合当前规则的待处理碎片")
        self.progress["value"] = 0
        self.execute_button.configure(text="模拟执行计划" if demo else "执行预览计划")
        self.set_busy(None)
        self.render_rows()

    def render_rows(self):
        self.tree.delete(*self.tree.get_children())
        rerolls = Counter(n for group in self.plan.groups for n in group) if self.plan else Counter()
        direct = Counter(self.plan.direct) if self.plan else Counter()
        keep = Counter(self.plan.leftovers) if self.plan else Counter()
        term = self.search.get().strip().casefold()
        visible_index = 0
        for item in sorted(self.inventory, key=lambda i: (i.get("disenchantValue", 0), i.get("itemDesc", ""))):
            if item.get("type") != SHARD or not item["count"]:
                continue
            name, loot_id = item.get("itemDesc") or item["lootId"], item["lootId"]
            if term and term not in name.casefold() and term not in loot_id.casefold():
                continue
            if not self.plan:
                action, detail, tag = "待预览", "刷新库存后生成计划", "keep"
            elif direct[loot_id]:
                action, detail, tag = "直接分解", f"分解 {direct[loot_id]} 个 → {direct[loot_id] * item['disenchantValue']:,} 精萃", "direct"
            elif rerolls[loot_id]:
                action, detail, tag = "参与重随", f"消耗 {rerolls[loot_id]} 个" + (f" · 保留 {keep[loot_id]} 个" if keep[loot_id] else ""), "reroll"
            else:
                action, detail, tag = "保留", f"剩余 {keep[loot_id]} 个，不足三个", "keep"
            self.tree.insert("", "end", values=(name, item["count"], item["disenchantValue"], action, detail), tags=(tag, "odd" if visible_index % 2 else "even"))
            visible_index += 1

    def execute(self):
        if self.busy or not self.plan or not self.plan.units:
            return
        plan, client, account = self.plan, self.client, self.account
        prefix = "这是离线模拟。\n\n" if self.demo else "此操作会消耗客户端中的英雄碎片，无法撤销。\n\n"
        text = prefix + f"重随 {len(plan.groups)} 次，并分解所得\n直接分解 {len(plan.direct)} 个碎片\n保留 {len(plan.leftovers)} 个碎片\n直接分解预计获得 {plan.guaranteed_essence:,} 蓝色精萃"
        if plan.groups and plan.rules.allow_unlock:
            text += "\n\n未拥有的英雄可能自动解锁，这部分无法分解。"
        if not messagebox.askyesno("确认执行这份计划", text, icon="warning", parent=self.root):
            return
        self.stop.clear()
        self.report = None
        self.status.set("正在执行 · 请保持客户端登录，避免同时操作战利品")
        self.append_log("开始" + ("离线模拟" if self.demo else "处理预览计划"))
        runner = Runner(client, plan, account["key"], self.stop,
                        lambda kind, value: self.events.put((kind, value)),
                        history=history_directory() / "demo" if self.demo else None)
        self.background(lambda: ("report", runner.run()), "execute")

    def cancel(self):
        self.stop.set()
        self.stop_button.configure(state="disabled")
        self.status.set("正在停止：完成当前组及所得分解后停止。")

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.append_log(value)
                elif kind == "progress":
                    self.progress["value"] = value["completedUnits"] / max(value["totalUnits"], 1) * 100
                    self.status.set(f"已完成 {value['completedUnits']}/{value['totalUnits']} · 增加 {value.get('blueEssenceGained', 0):,} 蓝色精萃")
                elif kind == "error":
                    self.plan = None
                    self.set_busy(None)
                    self.connection.set("连接需检查")
                    self.status.set(value)
                    self.append_log(value)
                    messagebox.showerror("操作未完成", value, parent=self.root)
                elif kind == "finished":
                    if value[0] == "inventory":
                        self.show_inventory(*value[1:])
                    else:
                        self.report = value[1]
                        self.plan = None
                        self.set_busy(None)
                        self.show_report()
                        if self.closing:
                            self.root.destroy()
                            return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def show_report(self):
        report = self.report
        if report["status"] in ("complete", "cancelled"):
            remaining = {i["lootId"]: i["count"] for i in report.get("leftovers", [])}
            for item in self.inventory:
                if item.get("type") == SHARD:
                    item["count"] = remaining.get(item["lootId"], 0)
            self.metrics["reroll"].set(str(report["rerolls"]))
            self.metrics["direct"].set(str(report["directDisenchants"]))
            self.metrics["keep"].set(str(sum(remaining.values())))
        self.render_rows()
        title = {"complete": "处理完成", "cancelled": "已按要求停止", "stopped": "异常停止"}.get(report["status"], "处理结束")
        text = f"{title} · 重随 {report['rerolls']} 次 · 直接分解 {report['directDisenchants']} 个 · 增加 {report.get('blueEssenceGained', 0):,} 精萃"
        self.status.set(text)
        self.append_log(text)
        self.append_log("记录文件：" + report["reportPath"])
        if report.get("error"):
            self.append_log(report["error"])
            messagebox.showerror("操作已停止", report["error"] + "\n\n已发送的操作不会自动重试。请检查客户端和处理记录；未分解的重随所得需要核对后手动处理。", parent=self.root)
        else:
            messagebox.showinfo(title, text + "\n\n点击“刷新库存 / 生成预览”查看剩余物品。", parent=self.root)
        if report.get("finalBlueEssence") is not None:
            self.balance_label.configure(text=f"蓝色精萃 {report['finalBlueEssence']:,}")

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def export_report(self):
        if not self.report:
            messagebox.showinfo("暂无结果", "执行后可以导出本次处理结果。", parent=self.root)
            return
        path = filedialog.asksaveasfilename(title="导出处理结果", defaultextension=".json", initialfile="loot-result.json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                shutil.copyfile(self.report["reportPath"], path)
            except OSError:
                messagebox.showerror("导出失败", "请检查目标目录权限。", parent=self.root)

    def open_history(self):
        directory = history_directory()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(directory)
            else:
                messagebox.showinfo("处理记录目录", str(directory), parent=self.root)
        except OSError:
            messagebox.showerror("无法打开记录", "请检查本地文件权限。", parent=self.root)

    def elevate(self):
        if is_admin():
            messagebox.showinfo("管理员权限", "当前已经以管理员权限运行。", parent=self.root)
            return
        if restart_elevated():
            self.root.destroy()
        else:
            self.status.set("管理员重启已取消，当前窗口继续运行。")

    def close(self):
        if self.busy == "execute":
            if messagebox.askyesno("停止后退出", "将完成当前组及所得分解后退出，是否继续？", parent=self.root):
                self.closing = True
                self.cancel()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root, demo="--demo" in sys.argv)
    root.mainloop()
