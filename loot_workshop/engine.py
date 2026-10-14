"""Sequential execution with durable transaction records and inventory reconciliation."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import threading
import uuid

from .core import (BLUE, PERMANENT_DISENCHANT, REROLL, SHARD, SHARD_DISENCHANT,
                   LootError, Plan, counts, essence, fingerprint, inventory_map,
                   transaction_delta, validate_inputs)


def history_directory() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return root / "LoLLootWorkshop" / "history"


class ExecutionLock:
    """One execution per history directory, including separate app instances."""
    def __init__(self, path):
        self.path, self.stream = Path(path), None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        try:
            if stream.seek(0, 2) == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.stream = stream
        except OSError:
            stream.close()
            raise LootError("另一个工具窗口正在处理物品，请等待它完成。") from None

    def release(self):
        if self.stream:
            self.stream.close()
            self.stream = None


class Runner:
    def __init__(self, client, plan: Plan, account_key: str, stop: threading.Event,
                 emit=lambda *args: None, history: Path | None = None):
        self.client, self.plan, self.account_key = client, plan, account_key
        self.stop, self.emit = stop, emit
        self.history = history or history_directory()
        self.session = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        self.journal = self.history / (self.session + ".jsonl")
        self.report_path = self.history / (self.session + ".json")
        self.generated = Counter()
        self.state = plan.snapshot
        self.report = {"version": 1, "status": "starting", "session": self.session,
                       "accountFingerprint": account_key, "rules": plan.to_dict()["rules"],
                       "initialBlueEssence": essence(self.state), "rerolls": 0,
                       "directDisenchants": 0, "permanentDisenchants": 0,
                       "unlockedChampions": 0, "completedUnits": 0,
                       "totalUnits": plan.units, "pendingGenerated": {}}

    def record(self, kind, **data):
        self.history.mkdir(parents=True, exist_ok=True)
        with self.journal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": datetime.now().isoformat(), "kind": kind, **data}, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def save(self):
        self.report["pendingGenerated"] = dict(+self.generated)
        temp = self.report_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.report_path)

    def check_recipe(self, recipe, names):
        choices = self.client.recipes(names[0])
        match = next((r for r in choices if r.get("recipeName") == recipe), None)
        slots = match.get("slots", []) if match else []
        slots = sorted(slots, key=lambda s: s.get("slotNumber", -1))
        if len(slots) != len(names) or any(s.get("quantity") != 1 or n not in s.get("lootIds", []) for s, n in zip(slots, names)):
            raise LootError("当前客户端配方与预期不一致，尚未发送这次操作。")

    def craft(self, recipe, names):
        # Re-read immediately before every mutation. No automatic retries.
        fresh = self.client.inventory()
        if fingerprint(fresh) != fingerprint(self.state):
            raise LootError("库存被其他操作改变，已停止。请重新生成预览。")
        validate_inputs(fresh, recipe, names, self.plan.rules, self.generated)
        self.check_recipe(recipe, names)
        operation = uuid.uuid4().hex
        self.record("intent", operation=operation, recipe=recipe, inputs=names,
                    beforeCounts=dict(counts(fresh)))
        result = self.client.craft(recipe, names)
        # Persist the response before validation, so a crash never hides a sent mutation.
        self.record("response", operation=operation, result=result)
        expected, generated, unlocked = transaction_delta(fresh, recipe, names, result, self.plan.rules.allow_unlock)
        self.generated.update(generated)
        if recipe == PERMANENT_DISENCHANT:
            self.generated[names[0]] -= 1
        self.save()
        after = self.client.inventory()
        if counts(after) != expected:
            raise LootError("交易结果与实际库存不一致，已停止。请求不会重试，请查看处理记录。")
        self.state = after
        self.record("verified", operation=operation, afterCounts=dict(counts(after)))
        if recipe == REROLL:
            self.report["rerolls"] += 1
            self.report["unlockedChampions"] += unlocked
        elif recipe == SHARD_DISENCHANT:
            self.report["directDisenchants"] += 1
        else:
            self.report["permanentDisenchants"] += 1
        self.report["finalBlueEssence"] = essence(after)
        self.report["blueEssenceGained"] = essence(after) - self.report["initialBlueEssence"]
        self.save()
        return generated

    def run(self):
        lock = ExecutionLock(self.history / "execution.lock")
        try:
            lock.acquire()
            self.record("session", accountFingerprint=self.account_key, plan=self.plan.to_dict())
            self.save()
            self.client.preflight(self.account_key, bool(self.plan.groups) and not self.plan.rules.allow_unlock)
            if fingerprint(self.client.inventory()) != self.plan.snapshot_hash:
                raise LootError("库存已变化，请重新生成预览后执行。")
            self.report["status"] = "running"
            units = [(REROLL, names) for names in self.plan.groups] + [(SHARD_DISENCHANT, [name]) for name in self.plan.direct]
            for recipe, names in units:
                if self.stop.is_set():
                    self.report["status"] = "cancelled"
                    break
                produced = self.craft(recipe, names)
                # Cancellation takes effect after this group and its generated permanents.
                for name, n in produced.items():
                    for _ in range(n):
                        self.craft(PERMANENT_DISENCHANT, [name])
                self.report["completedUnits"] += 1
                self.save()
                self.emit("progress", dict(self.report))
                self.emit("log", f"{'重随并分解所得' if recipe == REROLL else '直接分解'}完成 · {self.report['completedUnits']}/{self.plan.units}")
            else:
                remaining = Counter({n: i["count"] for n, i in inventory_map(self.state).items() if i.get("type") == SHARD and i["count"]})
                if remaining != Counter(self.plan.leftovers) or +self.generated:
                    raise LootError("最终保留数量或重随产出未通过核对。")
                self.report["status"] = "complete"
            self.report["leftovers"] = [{"lootId": n, "count": q, "name": inventory_map(self.state)[n].get("itemDesc", n)}
                                         for n, q in counts(self.state).items() if n.startswith("CHAMPION_RENTAL_")]
        except Exception as error:
            self.report["status"] = "stopped"
            self.report["error"] = str(error) if isinstance(error, LootError) else "接口格式或本地记录出现异常，操作已停止。请检查客户端与记录文件。"
            self.record("stopped", error=self.report["error"])
        finally:
            try:
                self.report["reportPath"] = str(self.report_path)
                self.save()
            finally:
                lock.release()
        return self.report
