import unittest

from PIL import Image

from automation_hub.proyek import photo_prep as P


class CropBoxTest(unittest.TestCase):
    def ratio(self, box):
        return (box[2] - box[0]) / (box[3] - box[1])

    def test_landscape_wide_trims_sides(self):
        box = P.crop_box(1600, 900)
        self.assertAlmostEqual(self.ratio(box), 4 / 3, places=2)
        self.assertEqual(box[1], 0)
        self.assertEqual(box[3], 900)

    def test_portrait_trims_height_centered(self):
        box = P.crop_box(900, 1600)
        self.assertAlmostEqual(self.ratio(box), 4 / 3, places=2)
        self.assertEqual((box[0], box[2]), (0, 900))
        self.assertLessEqual(abs(box[1] - (1600 - box[3])), 1)

    def test_already_4x3_unchanged(self):
        self.assertEqual(P.crop_box(1200, 900), (0, 0, 1200, 900))

    def test_prepare_without_text_gives_4x3_and_no_stamp(self):
        img, stamp = P.prepare(Image.new("RGB", (1000, 1000), "white"))
        self.assertFalse(stamp)
        self.assertAlmostEqual(img.width / img.height, 4 / 3, places=2)


if __name__ == "__main__":
    unittest.main()
