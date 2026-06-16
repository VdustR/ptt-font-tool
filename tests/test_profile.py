import unittest

from ptt_font_tool.profile import TermPttProfile


class TermPttProfileTest(unittest.TestCase):
    def test_maps_halfwidth_and_fullwidth_characters_to_ptt_cells(self):
        profile = TermPttProfile(half_advance=600)

        self.assertEqual(profile.cell_width("A"), 1)
        self.assertEqual(profile.target_advance("A"), 600)
        self.assertEqual(profile.cell_width("0"), 1)
        self.assertEqual(profile.target_advance("0"), 600)
        self.assertEqual(profile.cell_width("漢"), 2)
        self.assertEqual(profile.target_advance("漢"), 1200)
        self.assertEqual(profile.cell_width("│"), 2)
        self.assertEqual(profile.target_advance("│"), 1200)
        self.assertEqual(profile.cell_width("◢"), 2)
        self.assertEqual(profile.target_advance("◢"), 1200)

    def test_treats_ambiguous_characters_as_wide_for_term_ptt(self):
        profile = TermPttProfile(half_advance=600)

        self.assertEqual(profile.cell_width("ˇ"), 2)
        self.assertEqual(profile.target_advance("ˇ"), 1200)

    def test_rejects_non_single_character_inputs(self):
        profile = TermPttProfile(half_advance=600)

        with self.assertRaises(ValueError):
            profile.cell_width("")

        with self.assertRaises(ValueError):
            profile.cell_width("AA")


if __name__ == "__main__":
    unittest.main()
