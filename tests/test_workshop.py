import copy
from pathlib import Path
import tempfile
import threading
import unittest

from loot_workshop.core import (BLUE, REROLL, SHARD_DISENCHANT, PERMANENT_DISENCHANT,
                               LootError, Rules, counts, make_plan, transaction_delta,
                               validate_inputs)
from loot_workshop.demo import DemoClient, item
from loot_workshop.engine import Runner, ExecutionLock


class PlanningTests(unittest.TestCase):
    def test_threshold_is_inclusive_for_direct_disenchant(self):
        plan = make_plan([item("CHAMPION_RENTAL_a", "A", 2, 630)], Rules())
        self.assertEqual(len(plan.direct), 2)
        self.assertEqual(plan.groups, [])
        self.assertEqual(plan.guaranteed_essence, 1260)

    def test_groups_can_mix_heroes_and_keep_most_valuable_remainder(self):
        data = [item("CHAMPION_RENTAL_a", "A", 2, 90), item("CHAMPION_RENTAL_b", "B", 2, 270)]
        plan = make_plan(data, Rules())
        self.assertEqual(plan.groups, [["CHAMPION_RENTAL_a", "CHAMPION_RENTAL_a", "CHAMPION_RENTAL_b"]])
        self.assertEqual(plan.leftovers, ["CHAMPION_RENTAL_b"])
        data[0]["count"] = 10
        self.assertEqual(plan.snapshot[0]["count"], 2)

    def test_one_and_two_low_shards_are_left(self):
        for n in (1, 2):
            plan = make_plan([item("CHAMPION_RENTAL_a", "A", n, 90)], Rules())
            self.assertEqual(plan.units, 0)
            self.assertEqual(len(plan.leftovers), n)

    def test_disable_reroll_disenchants_all(self):
        plan = make_plan(DemoClient().inventory(), Rules(reroll_low=False))
        self.assertEqual(len(plan.direct), 20)
        self.assertEqual(plan.groups, [])

    def test_non_champion_loot_and_existing_permanents_excluded(self):
        data = DemoClient().inventory() + [item("CHAMPION_1", "A", 3, 225, "CHAMPION")]
        plan = make_plan(data, Rules())
        self.assertTrue(all(n.startswith("CHAMPION_RENTAL_") for n in plan.direct + [n for g in plan.groups for n in g]))

    def test_invalid_counts_or_values_are_rejected(self):
        for field, value in (("count", -1), ("count", True), ("disenchantValue", 0)):
            row = item("CHAMPION_RENTAL_a", "A", 1, 90)
            row[field] = value
            with self.assertRaises(LootError):
                make_plan([row], Rules())

    def test_duplicate_ids_and_unknown_recipes_are_rejected(self):
        row = item("CHAMPION_RENTAL_a", "A", 1, 90)
        with self.assertRaises(LootError):
            make_plan([row, row], Rules())
        row["disenchantRecipeName"] = "other"
        with self.assertRaises(LootError):
            make_plan([row], Rules())

    def test_rule_range(self):
        for n in (0, -1, 10001, True):
            with self.assertRaises(LootError):
                Rules(n)

    def test_zero_count_empty_placeholder_from_regional_client(self):
        client = DemoClient()
        data = client.inventory() + [{"lootId": "", "count": 0, "type": ""}]
        self.assertEqual(make_plan(data, Rules()).groups, make_plan(client.inventory(), Rules()).groups)
        data[-1]["count"] = 1
        with self.assertRaises(LootError):
            make_plan(data, Rules())


class TransactionTests(unittest.TestCase):
    def test_reroll_accepts_bonus_blue_essence_and_same_stack(self):
        client = DemoClient()
        client.rolls = 2
        before = client.inventory()
        names = ["CHAMPION_RENTAL_11"] * 3
        result = client.craft(REROLL, names)
        expected, generated, unlocked = transaction_delta(before, REROLL, names, result)
        self.assertEqual(expected, counts(client.inventory()))
        self.assertEqual(sum(generated.values()), 1)
        self.assertEqual(expected[BLUE], 10325)
        self.assertEqual(unlocked, 0)

    def test_wrong_consumption_or_non_champion_output_rejected(self):
        client = DemoClient()
        before = client.inventory()
        names = ["CHAMPION_RENTAL_11"] * 3
        result = client.craft(REROLL, names)
        wrong = copy.deepcopy(result)
        wrong["removed"][0]["deltaCount"] = 2
        with self.assertRaises(LootError):
            transaction_delta(before, REROLL, names, wrong)
        wrong = copy.deepcopy(result)
        wrong["added"][0]["playerLoot"]["type"] = "SKIN"
        with self.assertRaises(LootError):
            transaction_delta(before, REROLL, names, wrong)

    def test_disenchant_must_return_exact_preview_value(self):
        client = DemoClient()
        before = client.inventory()
        names = ["CHAMPION_RENTAL_147"]
        result = client.craft(SHARD_DISENCHANT, names)
        result["added"][0]["deltaCount"] = 1
        with self.assertRaises(LootError):
            transaction_delta(before, SHARD_DISENCHANT, names, result)

    def test_existing_permanent_cannot_be_disenchanted(self):
        data = [item("CHAMPION_1", "A", 5, 225, "CHAMPION")]
        from collections import Counter
        with self.assertRaises(LootError):
            validate_inputs(data, PERMANENT_DISENCHANT, ["CHAMPION_1"], Rules(), Counter())

    def test_reroll_cannot_consume_threshold_or_missing_shards(self):
        from collections import Counter
        data = [item("CHAMPION_RENTAL_a", "A", 3, 630)]
        with self.assertRaises(LootError):
            validate_inputs(data, REROLL, ["CHAMPION_RENTAL_a"] * 3, Rules(), Counter())
        data[0]["disenchantValue"] = 90
        data[0]["count"] = 2
        with self.assertRaises(LootError):
            validate_inputs(data, REROLL, ["CHAMPION_RENTAL_a"] * 3, Rules(), Counter())

    def test_unlock_requires_explicit_opt_in(self):
        client = DemoClient()
        before = client.inventory()
        names = ["CHAMPION_RENTAL_11"] * 3
        result = client.craft(REROLL, names)
        result["redeemed"] = result["added"]
        result["added"] = []
        with self.assertRaises(LootError):
            transaction_delta(before, REROLL, names, result)
        _, generated, unlocked = transaction_delta(before, REROLL, names, result, True)
        self.assertEqual(unlocked, 1)
        self.assertEqual(sum(generated.values()), 0)


class RunnerTests(unittest.TestCase):
    def test_another_window_cannot_execute_at_same_time(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory)
            lock = ExecutionLock(history / "execution.lock")
            lock.acquire()
            try:
                client = DemoClient()
                runner = Runner(client, make_plan(client.inventory(), Rules()), "offline-demo", threading.Event(), history=history)
                report = runner.run()
                self.assertEqual(report['status'], 'stopped')
                self.assertEqual(client.rolls, 0)
            finally:
                lock.release()
            lock.acquire()
            lock.release()

    def run_client(self, client, plan=None, stop=None, emit=lambda *args: None):
        with tempfile.TemporaryDirectory() as directory:
            runner = Runner(client, plan or make_plan(client.inventory(), Rules()), "offline-demo",
                            stop or threading.Event(), emit, Path(directory))
            report = runner.run()
            lines = runner.journal.read_text(encoding="utf-8")
            return report, lines

    def test_full_run_preserves_other_loot_and_existing_permanents(self):
        client = DemoClient()
        client.items["CHAMPION_DEMO_1"] = item("CHAMPION_DEMO_1", "Existing", 2, 1575, "CHAMPION")
        # Ensure a reroll output stacking on an existing permanent preserves its original quantity.
        original = client.craft
        def stacked(recipe, names):
            old_count = client.items.get("CHAMPION_DEMO_1", {}).get("count", 0)
            result = original(recipe, names)
            if recipe == REROLL and client.rolls == 1:
                client.items["CHAMPION_DEMO_1"]["count"] = old_count + 1
                result["added"][0]["playerLoot"]["count"] = old_count + 1
            return result
        client.craft = stacked
        report, journal = self.run_client(client)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["rerolls"], 4)
        self.assertEqual(report["directDisenchants"], 7)
        self.assertEqual(report["permanentDisenchants"], 4)
        self.assertEqual(report["blueEssenceGained"], 12955)
        self.assertEqual(client.items["SKIN_RENTAL_DEMO"]["count"], 5)
        self.assertEqual(client.items["CHAMPION_DEMO_1"]["count"], 2)
        self.assertNotIn("Authorization", journal)

    def test_stale_plan_sends_no_mutation(self):
        client = DemoClient()
        plan = make_plan(client.inventory(), Rules())
        client.items["CHAMPION_RENTAL_1"]["count"] += 1
        report, journal = self.run_client(client, plan)
        self.assertEqual(report["status"], "stopped")
        self.assertNotIn('"kind": "intent"', journal)

    def test_cancellation_finishes_current_group_and_generated_item(self):
        client = DemoClient()
        stop = threading.Event()
        original = client.craft
        def craft(recipe, names):
            result = original(recipe, names)
            if recipe == REROLL:
                stop.set()
            return result
        client.craft = craft
        report, _ = self.run_client(client, stop=stop)
        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(report["rerolls"], 1)
        self.assertEqual(report["permanentDisenchants"], 1)
        self.assertEqual(report["pendingGenerated"], {})

    def test_mutation_timeout_never_retries(self):
        client = DemoClient()
        calls = []
        def craft(recipe, names):
            calls.append((recipe, names))
            raise LootError("网络中断")
        client.craft = craft
        report, journal = self.run_client(client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["status"], "stopped")
        self.assertIn('"kind": "intent"', journal)
        self.assertNotIn('"kind": "response"', journal)

    def test_recipe_mismatch_stops_before_mutation(self):
        client = DemoClient()
        client.recipes = lambda _: []
        report, journal = self.run_client(client)
        self.assertEqual(report["status"], "stopped")
        self.assertNotIn('"kind": "intent"', journal)

    def test_unrelated_inventory_change_after_transaction_stops(self):
        client = DemoClient()
        original = client.craft
        def craft(recipe, names):
            result = original(recipe, names)
            client.items["SKIN_RENTAL_DEMO"]["count"] -= 1
            return result
        client.craft = craft
        report, _ = self.run_client(client)
        self.assertEqual(report["status"], "stopped")
        self.assertEqual(sum(report["pendingGenerated"].values()), 1)


if __name__ == "__main__":
    unittest.main()
