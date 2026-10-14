"""Authenticated access to the running local League client; never persists secrets."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from .core import LootError


def is_admin() -> bool:
    return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())


def restart_elevated() -> bool:
    if os.name != "nt":
        raise LootError("自动提权只支持Windows。")
    if getattr(sys, "frozen", False):
        executable, arguments = sys.executable, sys.argv[1:]
    else:
        executable = sys.executable
        entry = Path(__file__).resolve().parents[1] / "main.py"
        arguments = [str(entry), *sys.argv[1:]]
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, subprocess.list2cmdline(arguments), None, 1)
    return result > 32


class LeagueClient:
    def __init__(self, port: int, token: str):
        if not 1 <= port <= 65535 or not token:
            raise LootError("客户端连接参数无效。")
        self._base = f"https://127.0.0.1:{port}"
        self._authorization = "Basic " + base64.b64encode(("riot:" + token).encode()).decode()
        # The client uses a self-signed certificate. This opener can only reach loopback.
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))

    @classmethod
    def discover(cls, lockfile: str = ""):
        if lockfile:
            try:
                parts = Path(lockfile).read_text(encoding="utf-8").strip().split(":")
                if len(parts) != 5 or parts[4] != "https":
                    raise ValueError()
                return cls(int(parts[2]), parts[3])
            except (OSError, ValueError):
                raise LootError("lockfile为空、无法读取或格式无效。请尝试自动连接。") from None
        if os.name != "nt":
            raise LootError("自动连接目前仅支持Windows；其他系统可手动选择lockfile。")
        command = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
            "Get-CimInstance Win32_Process -Filter \"name='LeagueClientUx.exe'\" | "
            "Where-Object {$_.CommandLine} | Select-Object -ExpandProperty CommandLine | "
            "ConvertTo-Json -Compress"
        )
        try:
            process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                     capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            commands = json.loads(process.stdout.decode("utf-8-sig", errors="replace"))
            if isinstance(commands, str):
                commands = [commands]
            for command_line in commands or []:
                port = re.search(r'--app-port[= ]"?(\d+)', command_line)
                token = re.search(r'--remoting-auth-token[= ]"?([^\s"]+)', command_line)
                if port and token:
                    return cls(int(port.group(1)), token.group(1))
        except (OSError, ValueError, subprocess.SubprocessError, TypeError):
            pass
        raise LootError("无法读取客户端连接参数。请保持英雄联盟客户端开启，必要时点击“以管理员权限重启”。")

    def _request(self, route: str, payload=None):
        if not route.startswith("/") or ".." in route or "#" in route or "://" in route:
            raise LootError("无效的本地接口路径。")
        request = urllib.request.Request(
            self._base + route,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={"Authorization": self._authorization, "Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as error:
            # Never include request headers, credentials, or unfiltered response bodies.
            raise LootError(f"客户端接口返回HTTP {error.code}。操作已停止，请刷新库存核对。") from None
        except (OSError, ValueError, urllib.error.URLError):
            raise LootError("客户端连接中断或返回格式异常。请求不会自动重试；请刷新库存核对结果。") from None

    def inventory(self):
        items = self._request("/lol-loot/v1/player-loot")
        if not isinstance(items, list):
            raise LootError("客户端库存格式不受支持。")
        return items

    def account(self):
        result = self._request("/lol-summoner/v1/current-summoner")
        if not isinstance(result, dict) or not result.get("summonerId"):
            raise LootError("请先完成客户端登录。")
        key = str(result.get("puuid") or result["summonerId"])
        return {"id": result["summonerId"], "key": hashlib.sha256(key.encode()).hexdigest(),
                "name": result.get("gameName") or result.get("displayName") or "已登录玩家"}

    def preflight(self, account_key: str, require_all_owned: bool):
        account = self.account()
        if account["key"] != account_key:
            raise LootError("登录账号已变化，请重新连接并生成预览。")
        phase = self._request("/lol-gameflow/v1/gameflow-phase")
        if phase not in ("None", "Lobby"):
            raise LootError("请先退出排队、选人或对局，再处理战利品。")
        if require_all_owned:
            champions = self._request(f"/lol-champions/v1/inventories/{account['id']}/champions")
            if not isinstance(champions, list) or not champions or any(
                not isinstance(i.get("ownership"), dict) or i["ownership"].get("owned") is not True
                for i in champions
            ):
                raise LootError("当前账号未拥有全部英雄，或无法核实所有权。重随可能自动解锁新英雄；若接受，请勾选相应选项后重新预览。")

    def recipes(self, name: str):
        result = self._request("/lol-loot/v1/recipes/initial-item/" + urllib.parse.quote(name, safe=""))
        if not isinstance(result, list):
            raise LootError("客户端配方格式不受支持。")
        return result

    def craft(self, recipe: str, names: list[str]):
        from .core import REROLL, SHARD_DISENCHANT, PERMANENT_DISENCHANT
        if recipe not in (REROLL, SHARD_DISENCHANT, PERMANENT_DISENCHANT):
            raise LootError("不支持的配方。")
        return self._request(f"/lol-loot/v1/recipes/{recipe}/craft?repeat=1", names)
