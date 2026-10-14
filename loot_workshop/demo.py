"""Synthetic, offline inventory for trying the UI and testing the runner."""
from copy import deepcopy
from .core import BLUE, PERMANENT, PERMANENT_DISENCHANT, REROLL, SHARD, SHARD_DISENCHANT


def item(name, title, count, value, kind=SHARD):
    return {"lootId": name, "lootName": name, "itemDesc": title, "count": count,
            "type": kind, "disenchantValue": value, "disenchantLootName": BLUE,
            "disenchantRecipeName": SHARD_DISENCHANT if kind == SHARD else PERMANENT_DISENCHANT}


class DemoClient:
    def __init__(self):
        self.items = {
            i["lootId"]: i for i in [
                item("CHAMPION_RENTAL_1", "黑暗之女", 2, 90),
                item("CHAMPION_RENTAL_11", "无极剑圣", 4, 90),
                item("CHAMPION_RENTAL_9", "远古恐惧", 3, 270),
                item("CHAMPION_RENTAL_875", "腕豪", 4, 270),
                item("CHAMPION_RENTAL_147", "星籁歌姬", 3, 630),
                item("CHAMPION_RENTAL_57", "扭曲树精", 2, 960),
                item("CHAMPION_RENTAL_902", "明烛", 2, 1260),
                {"lootId": BLUE, "count": 10000, "type": "CURRENCY"},
                {"lootId": "SKIN_RENTAL_DEMO", "count": 5, "type": "SKIN_RENTAL"},
            ]
        }
        self.rolls = 0

    def account(self):
        return {"id": 1, "key": "offline-demo", "name": "演示账号 · 合成数据"}

    def inventory(self):
        return deepcopy(list(self.items.values()))

    def preflight(self, *args):
        pass

    def recipes(self, name):
        if name.startswith("CHAMPION_RENTAL_"):
            ids = [i["lootId"] for i in self.items.values() if i["type"] == SHARD and i["count"]]
            return [{"recipeName": REROLL, "slots": [{"slotNumber": n, "quantity": 1, "lootIds": ids} for n in range(3)]},
                    {"recipeName": SHARD_DISENCHANT, "slots": [{"slotNumber": 0, "quantity": 1, "lootIds": [name]}]}]
        return [{"recipeName": PERMANENT_DISENCHANT, "slots": [{"slotNumber": 0, "quantity": 1, "lootIds": [name]}]}]

    def craft(self, recipe, names):
        from collections import Counter
        result = {"added": [], "removed": [], "redeemed": []}
        for name, n in Counter(names).items():
            self.items[name]["count"] -= n
            result["removed"].append({"deltaCount": n, "playerLoot": deepcopy(self.items[name])})
        if recipe == REROLL:
            self.rolls += 1
            name = "CHAMPION_DEMO_" + str(self.rolls)
            self.items[name] = item(name, "演示永久英雄", 1, 1575, PERMANENT)
            result["added"].append({"deltaCount": 1, "playerLoot": deepcopy(self.items[name])})
            bonus = 325 if self.rolls % 3 == 0 else 0
        else:
            bonus = self.items[names[0]]["disenchantValue"]
        if bonus:
            self.items[BLUE]["count"] += bonus
            result["added"].append({"deltaCount": bonus, "playerLoot": deepcopy(self.items[BLUE])})
        return result
