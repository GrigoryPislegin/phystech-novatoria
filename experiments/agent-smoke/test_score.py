import unittest
from score import percentage


class ScoreContractTests(unittest.TestCase):
    def test_percentage_scale(self):
        self.assertEqual(percentage(25, 50), 50.0)

    def test_boundaries(self):
        self.assertEqual(percentage(0, 50), 0.0)
        self.assertEqual(percentage(50, 50), 100.0)

    def test_invalid_maximum(self):
        for maximum in (0, -50):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                percentage(0, maximum)

    def test_out_of_range(self):
        for points in (-1, 51):
            with self.subTest(points=points), self.assertRaises(ValueError):
                percentage(points, 50)


if __name__ == '__main__':
    unittest.main()
