
import unittest
from bb84 import simulate_bb84


class TestBB84(unittest.TestCase):

    def test_no_eavesdropper(self):
        result = simulate_bb84(
            n_bits=2000,
            eve_present=False,
            seed=42,
        )
        self.assertEqual(result["qber"], 0.0)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["candidate_bits_match"])

    def test_eavesdropper_introduces_errors(self):
        result = simulate_bb84(
            n_bits=10000,
            eve_present=True,
            seed=42,
        )
        # Intercept-and-resend should create errors
        # with a sufficiently large sample.
        self.assertGreater(result["qber"], 0.0)
        self.assertFalse(result["accepted"])

    def test_final_key_is_not_claimed(self):
        result = simulate_bb84(n_bits=1000, seed=7)
        self.assertFalse(result["final_secure_key_generated"])

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            simulate_bb84(n_bits=5)

    def test_reproducibility(self):
        first = simulate_bb84(n_bits=1000, seed=123)
        second = simulate_bb84(n_bits=1000, seed=123)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()