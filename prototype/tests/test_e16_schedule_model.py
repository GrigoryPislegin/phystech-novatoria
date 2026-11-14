"""E16: the schedule model behind the speed-up proposal. Arithmetic only; it measures nothing."""
import unittest

from evaluation.schedule_model import summary, wall_time


class ScheduleModelTests(unittest.TestCase):
    def test_reported_baseline_is_reproduced_within_a_tenth(self):
        median, _ = summary(3, False)  # the live run: 680 s for 29 of 30 with three workers
        self.assertTrue(612 <= median <= 748, median)

    def test_overlap_never_loses_and_more_slots_never_hurt(self):
        for seed in range(50):
            for workers in (3, 6, 10, 16):
                now, overlap = wall_time(workers, False, seed=seed), wall_time(workers, True, seed=seed)
                self.assertLessEqual(overlap, now + 1e-9)
            times = [wall_time(w, True, seed=seed) for w in (3, 6, 10, 16, 31)]
            self.assertEqual(times, sorted(times, reverse=True))

    def test_the_chain_facts_then_evaluation_is_the_floor(self):
        # With a slot for every call the run still lasts privacy + facts + the longest evaluation.
        floor = wall_time(31, True, facts=49, low=30, high=30, privacy=5)
        self.assertAlmostEqual(floor, 5 + 49 + 30)
        self.assertGreater(summary(31, True)[0], 60)  # a minute is out of reach without a shorter output
        self.assertLess(summary(16, True, scale=0.6, facts_scale=0.6)[0], 120)


if __name__ == '__main__':
    unittest.main()
