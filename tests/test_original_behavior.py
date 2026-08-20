import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_note
import pipeline


class OriginalBehaviorTests(unittest.TestCase):
    def test_mixed_note_and_profile_links_keep_original_classification(self):
        values = pipeline.expand_links(
            [
                "https://www.xiaohongshu.com/explore/note_demo?xsec_token=private",
                "https://www.xiaohongshu.com/user/profile/user_demo?source=web",
            ]
        )

        self.assertEqual(
            values,
            [
                (
                    "https://www.xiaohongshu.com/explore/note_demo",
                    "note",
                    "单条笔记",
                ),
                (
                    "https://www.xiaohongshu.com/user/profile/user_demo",
                    "profile",
                    "达人主页",
                ),
            ],
        )

    def test_time_filter_keeps_newer_and_unknown_timestamp_notes(self):
        notes = [
            {"note_id": "old", "time": 100},
            {"note_id": "new", "time": 300},
            {"note_id": "unknown", "time": None},
        ]
        kept = pipeline.filter_by_time(notes, 200)
        self.assertEqual([item["note_id"] for item in kept], ["new", "unknown"])

    def test_note_initial_state_parser_can_decode_json(self):
        html = '<script>window.__INITIAL_STATE__={"note":{"noteDetailMap":{}}}</script>'
        self.assertEqual(
            fetch_note.extract_initial_state(html),
            {"note": {"noteDetailMap": {}}},
        )

    def test_cover_upload_uses_cover_directory_as_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cover = Path(tmp) / "demo_cover.jpg"
            cover.write_bytes(b"fake-image")
            completed = type(
                "Completed",
                (),
                {"stdout": json.dumps({"ok": True}), "returncode": 0},
            )()
            with patch("pipeline.subprocess.run", return_value=completed) as run:
                self.assertTrue(pipeline.upload_cover("rec_demo", str(cover)))

            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--file") + 1], cover.name)
            self.assertEqual(run.call_args.kwargs["cwd"], str(cover.resolve().parent))


if __name__ == "__main__":
    unittest.main()
