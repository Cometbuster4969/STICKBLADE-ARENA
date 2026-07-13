import tempfile
import unittest

from storage import LocalStorage


class StorageQueryTests(unittest.TestCase):
    def setUp(self):
        self.storage = LocalStorage(root=tempfile.mkdtemp())

    def test_record_vote_updates_expected_counters(self):
        a = "model-a"
        b = "model-b"
        mid = self.storage.create_match(a, b, ["tip"], blind=True, weapon="sword")
        self.storage.set_flip(mid, False)
        self.storage.finish_match(mid, "a", "kill", 10,
                                  {"meta": {}, "frames": [], "events": [], "thoughts": []})
        self.storage.record_vote(mid, "a")

        rows = self.storage.leaderboard("tip", "sword")
        by_model = {r["model"]: r for r in rows}
        self.assertEqual(by_model[a]["wins"], 1)
        self.assertEqual(by_model[a]["losses"], 0)
        self.assertEqual(by_model[b]["wins"], 0)
        self.assertEqual(by_model[b]["losses"], 1)

    def test_leaderboard_filters_by_sharp_and_weapon(self):
        with self.storage._conn() as c:
            c.execute("INSERT INTO elo (model, sharp, weapon, rating) VALUES (?,?,?,?)",
                      ("spear-tip", "tip", "spear", 1100))
            c.execute("INSERT INTO elo (model, sharp, weapon, rating) VALUES (?,?,?,?)",
                      ("sword-tip", "tip", "sword", 1200))
            c.execute("INSERT INTO elo (model, sharp, weapon, rating) VALUES (?,?,?,?)",
                      ("sword-pommel", "pommel", "sword", 1300))

        filtered = self.storage.leaderboard("tip", "sword")
        self.assertEqual([row["model"] for row in filtered], ["sword-tip"])


if __name__ == "__main__":
    unittest.main()
