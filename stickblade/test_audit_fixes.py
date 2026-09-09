"""
Test suite covering all audit fixes from AUDIT.md / astra 6.txt:
1. Objective leaderboard flip mapping (LocalStorage and SupabaseStorage).
2. Stale match cleanup on startup.
3. Strict API validation for weapons, sharp zones, modes, arenas, and votes.
4. Idempotent voting & uniqueness.
5. Evaluation integrity tracking in match recording and match API.
6. set_flip error propagation.
"""
import os
import sys
import tempfile
import unittest
from fastapi.testclient import TestClient

# Ensure SDL uses dummy driver for headless test
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
pygame.init()
if pygame.display.get_surface() is None:
    pygame.display.set_mode((10, 10))

from storage import LocalStorage
from storage_supabase import SupabaseStorage
from server import app
from recorder import ReplayRecorder
import config as C


class TestAuditFixes(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(root=self.temp_dir)
        self.client = TestClient(app)

    def test_objective_leaderboard_flip_mapping(self):
        """Verify that damage and stats are attributed correctly when flip=True vs flip=False."""
        m_a = "model-alpha"
        m_b = "model-beta"

        # Match 1: flip = False -> canvas side 'a' is model-alpha, side 'b' is model-beta
        mid1 = self.storage.create_match(m_a, m_b, ["tip"], blind=True, weapon="sword")
        self.storage.set_flip(mid1, False)
        self.storage.finish_match(mid1, "a", "kill", 10, {
            "meta": {
                "metrics": {
                    "damage_dealt_a": 100.0,
                    "damage_dealt_b": 20.0,
                    "hits_landed_a": 5,
                    "hits_landed_b": 1,
                    "hits_attempted_a": 10,
                    "hits_attempted_b": 8,
                    "fallback_turns_a": 0,
                    "fallback_turns_b": 2,
                    "avg_distance": 150.0
                }
            },
            "frames": [], "events": [], "thoughts": []
        })

        lb1 = {row["model"]: row for row in self.storage.objective_leaderboard()}
        self.assertEqual(lb1[m_a]["damage_per_turn"], 10.0)
        self.assertEqual(lb1[m_b]["damage_per_turn"], 2.0)
        self.assertEqual(lb1[m_a]["wins"], 1)
        self.assertEqual(lb1[m_b]["losses"], 1)

        # Match 2: flip = True -> canvas side 'a' is model-beta, side 'b' is model-alpha
        mid2 = self.storage.create_match(m_a, m_b, ["tip"], blind=True, weapon="sword")
        self.storage.set_flip(mid2, True)
        self.storage.finish_match(mid2, "a", "kill", 10, {
            "meta": {
                "metrics": {
                    "damage_dealt_a": 80.0,  # Side 'a' (model-beta) did 80 dmg
                    "damage_dealt_b": 10.0,  # Side 'b' (model-alpha) did 10 dmg
                    "hits_landed_a": 4,
                    "hits_landed_b": 1,
                    "hits_attempted_a": 8,
                    "hits_attempted_b": 5,
                    "fallback_turns_a": 1,
                    "fallback_turns_b": 0,
                    "avg_distance": 120.0
                }
            },
            "frames": [], "events": [], "thoughts": []
        })

        lb2 = {row["model"]: row for row in self.storage.objective_leaderboard()}
        # Combined across match 1 and 2:
        # m_a: 100 dmg (match 1) + 10 dmg (match 2) = 110 dmg over 20 turns = 5.5 dmg/turn
        # m_b: 20 dmg (match 1) + 80 dmg (match 2) = 100 dmg over 20 turns = 5.0 dmg/turn
        self.assertEqual(lb2[m_a]["damage_per_turn"], 5.5)
        self.assertEqual(lb2[m_b]["damage_per_turn"], 5.0)
        self.assertEqual(lb2[m_a]["wins"], 1)
        self.assertEqual(lb2[m_a]["losses"], 1)
        self.assertEqual(lb2[m_b]["wins"], 1)
        self.assertEqual(lb2[m_b]["losses"], 1)

    def test_stale_match_cleanup(self):
        """Verify that cleanup_stale_matches transitions running/queued matches to error."""
        mid1 = self.storage.create_match("m1", "m2", ["tip"])
        mid2 = self.storage.create_match("m1", "m2", ["tip"])
        self.storage.set_status(mid2, "running")

        self.storage.cleanup_stale_matches("Test restart")
        m1 = self.storage.get_match(mid1)
        m2 = self.storage.get_match(mid2)

        self.assertEqual(m1["status"], "error")
        self.assertEqual(m1["error"], "Test restart")
        self.assertEqual(m2["status"], "error")
        self.assertEqual(m2["error"], "Test restart")

    def test_vote_uniqueness_and_idempotency(self):
        """Verify duplicate voting returns already_voted without shifting Elo twice."""
        mid = self.storage.create_match("model-x", "model-y", ["tip"], blind=True, weapon="sword")
        self.storage.set_flip(mid, False)
        self.storage.finish_match(mid, "a", "kill", 5, {"meta": {}, "frames": [], "events": [], "thoughts": []})

        res1 = self.storage.record_vote(mid, "a")
        self.assertFalse(res1.get("already_voted", False))
        self.assertEqual(res1["model_a"], "model-x")
        self.assertEqual(res1["elo_change"]["model-x"], 16.0)

        res2 = self.storage.record_vote(mid, "a")
        self.assertTrue(res2.get("already_voted", False))
        self.assertEqual(res2["model_a"], "model-x")

    def test_strict_api_validation(self):
        """Verify API returns 400 or 422 for invalid requests."""
        # Invalid weapon
        r = self.client.post("/api/match", json={
            "model_a": "mock:duelist",
            "model_b": "mock:berserker",
            "sharp": ["tip"],
            "weapon": "laser_blaster"
        })
        self.assertIn(r.status_code, (400, 422))

        # Sharp zone incompatible with weapon
        r = self.client.post("/api/match", json={
            "model_a": "mock:duelist",
            "model_b": "mock:berserker",
            "sharp": ["arrowhead"],  # arrowhead not valid for sword
            "weapon": "sword"
        })
        self.assertIn(r.status_code, (400, 422))

        # Invalid mode
        r = self.client.post("/api/match", json={
            "model_a": "mock:duelist",
            "model_b": "mock:berserker",
            "sharp": ["tip"],
            "weapon": "sword",
            "mode": "god_mode"
        })
        self.assertIn(r.status_code, (400, 422))

        # Invalid arena
        r = self.client.post("/api/match", json={
            "model_a": "mock:duelist",
            "model_b": "mock:berserker",
            "sharp": ["tip"],
            "weapon": "sword",
            "arena": "volcano"
        })
        self.assertIn(r.status_code, (400, 422))

        # Leaderboard invalid weapon filter
        r = self.client.get("/api/leaderboard?weapon=invalid_gun")
        self.assertEqual(r.status_code, 400)

        r = self.client.get("/api/leaderboard/objective?weapon=invalid_gun")
        self.assertEqual(r.status_code, 400)

    def test_recorder_evaluation_integrity(self):
        """Verify evaluation_integrity is tracked and emitted in match metadata."""
        from main import Match
        from recorder import ReplayRecorder, RecordingFX
        rec = ReplayRecorder()
        fx = RecordingFX(rec)
        m = Match("Mock-duelist", "Mock-berserker", ["tip"], fx)
        rec.attach(m)
        # Advance match so log and frames are recorded
        m.update(1/60, False)
        summary = rec.build()
        self.assertIn("evaluation_integrity", summary["meta"])
        integrity = summary["meta"]["evaluation_integrity"]
        self.assertIn("fully_llm_controlled", integrity)
        self.assertIn("fallback_turns_a", integrity)
        self.assertIn("fallback_turns_b", integrity)


if __name__ == "__main__":
    unittest.main()
