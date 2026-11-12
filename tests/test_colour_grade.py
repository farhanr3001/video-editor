import unittest

import numpy as np
from PySide6.QtGui import QImage

from kinetic_cut.attributes import apply
from kinetic_cut.colour_grade import PRESETS, PRESETS_KEY, apply_image, apply_rgb, clean, saved_presets
from kinetic_cut.model import Project, TimelineItem


class ColourGradeTests(unittest.TestCase):
    def test_saved_presets_reject_bad_records_and_preserve_a_detached_grade(self):
        values = {"lift": [.3, .4, .1], "saturation": 130}
        settings = {PRESETS_KEY: [None, {"id": "bad", "name": "Warm Film", "values": {}},
                                {"id": "mine", "name": " Daylight ", "values": values},
                                {"id": "duplicate", "name": "DAYLIGHT", "values": {}},
                                {"id": "mine", "name": "Evening", "values": {}},
                                {"id": "other", "name": "Bad values", "values": "invalid"}]}
        records = saved_presets(settings)
        self.assertEqual(records, [{"id": "mine", "name": "Daylight", "values": values}])
        records[0]["values"]["lift"][0] = 0
        self.assertEqual(values["lift"][0], .3)

    def test_saved_grade_and_paste_are_independent_of_source(self):
        a = TimelineItem("a", "", "video_1", 0, 1, colour_grade={"gamma": (.25, .3, .1)})
        b = TimelineItem("b", "", "video_1", 1, 1, colour_grade={"exposure": 1})
        project = Project(timeline=[a, b])
        saved = Project.from_dict(project.to_dict())
        self.assertEqual(saved.timeline[0].colour_grade, a.colour_grade)
        source = saved.to_dict()["timeline"][0]
        apply(project, source, [b], "video", ["scale_x"])
        self.assertEqual(b.colour_grade, {"exposure": 1})
        apply(project, source, [b], "video", ["grade"])
        self.assertEqual(b.colour_grade, a.colour_grade)
        b.colour_grade["gamma"][0] = -.5
        self.assertEqual(a.colour_grade["gamma"][0], .25)
        apply(project, {}, [b], "video", ["grade"])
        self.assertEqual(b.colour_grade, {})

    def test_malformed_grade_remains_bounded_and_idempotent(self):
        raw = {"lift": [1, -1, 8], "offset": "invalid", "gamma": [0, 0, 0],
               "pivot": float("nan"), "saturation": -7, "temperature": float("inf")}
        value = clean(raw)
        self.assertEqual(value, clean(value))
        self.assertLessEqual(np.hypot(*value["lift"][:2]), 1.00001)
        self.assertEqual(value["lift"][2], 1)
        self.assertEqual(set(value), {"lift", "saturation"})

    def test_identity_alpha_and_separate_tonal_responses(self):
        colors = np.array([[[12, 12, 12, 64], [115, 115, 115, 128], [245, 245, 245, 255]]], dtype=np.uint8)
        rgb = colors[..., :3]/255
        np.testing.assert_allclose(apply_rgb(rgb, {}), rgb, atol=1e-7)
        for key, first, last in (("lift", 0, 2), ("gamma", 1, 2), ("gain", 2, 0)):
            changed = apply_rgb(rgb, {key: [0, 0, .15]}) - rgb
            self.assertGreater(changed[0, first, 0], changed[0, last, 0])
        image = QImage(colors.data, 3, 1, 12, QImage.Format_RGBA8888)
        for _, preset in PRESETS:
            raw = clean(preset)
            result = apply_image(image, raw)
            actual = np.frombuffer(result.constBits(), dtype=np.uint8).reshape(1, 3, 4)
            np.testing.assert_array_equal(actual[..., 3], colors[..., 3])
            np.testing.assert_array_equal(actual[..., :3], np.rint(apply_rgb(rgb, raw)*255))


if __name__ == "__main__":
    unittest.main()
