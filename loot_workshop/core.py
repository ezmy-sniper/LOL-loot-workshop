"""Pure planning and transaction validation. No network or UI dependencies."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json

BLUE = "CURRENCY_champion"
SHARD = "CHAMPION_RENTAL"
PERMANENT = "CHAMPION"
REROLL = "CHAMPION_reroll"
SHARD_DISENCHANT = "CHAMPION_RENTAL_disenchant"
PERMANENT_DISENCHANT = "CHAMPION_disenchant"


class LootError(RuntimeError):
    pass


def quantity(item: dict) -> int:
    n = item.get("count")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise LootError("库存包含无效数量，已停止。")
    return n


def inventory_map(items: list[dict]) -> dict[str, dict]:
    result = {}
    for item in items:
        name = item.get("lootId")
        if name == "" and item.get("type") == "" and quantity(item) == 0:
            # Some regional clients include an empty, zero-count placeholder row.
            continue
        if not isinstance(name, str) or not name or name in result:
            raise LootError("库存物品标识无效或重复，已停止。")
        quantity(item)
        result[name] = item
    return result


def counts(items: list[dict]) -> Counter:
    return Counter({n: quantity(i) for n, i in inventory_map(items).items() if quantity(i)})


def fingerprint(items: list[dict]) -> str:
    # Include prices and recipe names: unchanged quantities alone are insufficient.
    rows = sorted((n, quantity(i), i.get("type"), i.get("disenchantValue"),
                   i.get("disenchantRecipeName")) for n, i in inventory_map(items).items() if quantity(i))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=True).encode()).hexdigest()


def essence(items: list[dict]) -> int:
    return counts(items).get(BLUE, 0)


@dataclass(frozen=True)
class Rules:
    threshold: int = 630
    reroll_low: bool = True
    allow_unlock: bool = False

    def __post_init__(self):
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, int) or not 1 <= self.threshold <= 10000:
            raise LootError("阈值必须是1～10000之间的整数。")


@dataclass
class Plan:
    rules: Rules
    snapshot: list[dict]
    groups: list[list[str]]
    direct: list[str]
    leftovers: list[str]
    guaranteed_essence: int
    snapshot_hash: str

    @property
    def units(self):
        return len(self.groups) + len(self.direct)

    def to_dict(self):
        return asdict(self)


def make_plan(items: list[dict], rules: Rules) -> Plan:
    inventory_map(items)
    low, direct = [], []
    guaranteed = 0
    shards = sorted((i for i in items if i.get("type") == SHARD and quantity(i)),
                    key=lambda i: (i.get("disenchantValue", -1), i["lootId"]))
    for item in shards:
        value = item.get("disenchantValue")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise LootError("英雄碎片分解价值无效，请刷新库存。")
        if item.get("disenchantRecipeName") != SHARD_DISENCHANT or item.get("disenchantLootName") != BLUE:
            raise LootError("英雄碎片的分解配方不受支持。")
        names = [item["lootId"]] * quantity(item)
        if value < rules.threshold and rules.reroll_low:
            low.extend(names)
        else:
            direct.extend(names)
            guaranteed += value * quantity(item)
    size = len(low) // 3 * 3
    # Consume cheaper shards first, keeping the most valuable remainder.
    groups = [low[n:n + 3] for n in range(0, size, 3)]
    snapshot = json.loads(json.dumps(items))
    return Plan(rules, snapshot, groups, direct, low[size:], guaranteed, fingerprint(items))


def validate_inputs(items: list[dict], recipe: str, names: list[str], rules: Rules,
                    generated: Counter) -> None:
    data = inventory_map(items)
    for name, n in Counter(names).items():
        if name not in data or quantity(data[name]) < n:
            raise LootError("计划中的碎片已变化，请刷新预览。")
    if recipe == REROLL:
        if len(names) != 3 or not rules.reroll_low:
            raise LootError("重随必须使用三个低价值英雄碎片。")
        if any(data[n].get("type") != SHARD or not 0 < data[n].get("disenchantValue", 0) < rules.threshold for n in names):
            raise LootError("重随输入超出规则范围。")
    elif recipe in (SHARD_DISENCHANT, PERMANENT_DISENCHANT):
        if len(names) != 1:
            raise LootError("每次只分解一个英雄物品。")
        item = data[names[0]]
        if item.get("disenchantRecipeName") != recipe or item.get("disenchantLootName") != BLUE:
            raise LootError("分解配方与库存不符。")
        if recipe == SHARD_DISENCHANT:
            if item.get("type") != SHARD or (rules.reroll_low and item["disenchantValue"] < rules.threshold):
                raise LootError("不能直接分解应当保留或重随的碎片。")
        elif item.get("type") != PERMANENT or generated[names[0]] < 1:
            raise LootError("只能分解本次重随新产生的永久英雄。")
    else:
        raise LootError("不支持的配方。")


def transaction_delta(before: list[dict], recipe: str, names: list[str], result: dict,
                      allow_unlock: bool = False) -> tuple[Counter, Counter, int]:
    """Check returned outputs before trusting a transaction, including bonus BE."""
    if not isinstance(result, dict) or any(not isinstance(result.get(k), list) for k in ("added", "removed", "redeemed")):
        raise LootError("客户端返回了不支持的交易格式，已停止。")
    expected = counts(before)
    removed, generated = Counter(), Counter()
    unlocked = 0
    for entry in result["removed"]:
        name = entry["playerLoot"]["lootId"]
        q = entry["deltaCount"]
        if type(q) is not int or q <= 0:
            raise LootError("交易消耗数量异常。")
        removed[name] += q
        expected[name] -= q
    if removed != Counter(names) or any(n < 0 for n in expected.values()):
        raise LootError("交易实际消耗与计划不符，已停止。")
    for entry in result["added"]:
        item, q = entry["playerLoot"], entry["deltaCount"]
        name = item["lootId"]
        if type(q) is not int or q <= 0:
            raise LootError("交易产出数量异常。")
        if name == BLUE:
            expected[name] += q
        elif recipe == REROLL and item.get("type") == PERMANENT and item.get("disenchantRecipeName") == PERMANENT_DISENCHANT and item.get("disenchantLootName") == BLUE:
            expected[name] += q
            generated[name] += q
        else:
            raise LootError("交易产生了预期外的物品，已停止。")
    for entry in result["redeemed"]:
        item, q = entry["playerLoot"], entry["deltaCount"]
        if not allow_unlock or recipe != REROLL or item.get("type") != PERMANENT or type(q) is not int or q <= 0:
            raise LootError("重随发生了预期外的解锁，已停止，请查看客户端。")
        unlocked += q
    if recipe == REROLL and sum(generated.values()) + unlocked != 1:
        raise LootError("重随没有恰好产出一个永久英雄，已停止。")
    if recipe != REROLL:
        item = inventory_map(before)[names[0]]
        gain = sum(e["deltaCount"] for e in result["added"] if e["playerLoot"]["lootId"] == BLUE)
        if gain != item["disenchantValue"]:
            raise LootError("实际分解收益与预览价值不符，已停止。")
    return +expected, generated, unlocked
