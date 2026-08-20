import argparse
import json
import subprocess
import unittest
from unittest.mock import patch

import feishu_views
import pipeline
import web_app


class CreatorViewTests(unittest.TestCase):
    def test_profile_video_filter_excludes_image_notes(self):
        notes = [
            {"note_id": "video-1", "type": "video"},
            {"note_id": "image-1", "type": "normal"},
            {"note_id": "video-2", "type": "video"},
        ]

        kept = pipeline.profile_video_notes(notes)

        self.assertEqual([item["note_id"] for item in kept], ["video-1", "video-2"])

    def test_creator_view_filter_is_limited_to_one_creators_profile_videos(self):
        self.assertEqual(
            feishu_views.creator_view_filter("Archie在摸鱼"),
            {
                "logic": "and",
                "conditions": [
                    ["达人昵称", "==", "Archie在摸鱼"],
                    ["来源类型", "==", ["达人主页"]],
                    ["笔记类型", "==", ["视频"]],
                ],
            },
        )

    def test_existing_view_with_matching_creator_filter_is_reused_even_if_name_is_shorter(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            action = command[2]
            if action == "+view-list":
                payload = {
                    "ok": True,
                    "data": {
                        "items": [
                            {
                                "view_id": "vew_tech",
                                "view_name": "科技米线",
                                "view_type": "grid",
                            }
                        ]
                    },
                }
            elif action == "+view-get-filter":
                payload = {
                    "ok": True,
                    "data": {
                        "filter": {
                            "logic": "and",
                            "conditions": [
                                ["达人昵称", "==", "科技米线(Ai 版）"],
                                ["来源类型", "==", ["达人主页"]],
                                ["笔记类型", "==", ["视频"]],
                            ],
                        }
                    },
                }
            else:
                self.fail(f"不应执行写操作: {action}")
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        result = feishu_views.ensure_creator_view(
            "base_demo",
            "tbl_demo",
            "科技米线(Ai 版）",
            runner=runner,
        )

        self.assertEqual(result, {"view_id": "vew_tech", "name": "科技米线", "created": False})
        self.assertEqual([command[2] for command in calls], ["+view-list", "+view-get-filter"])

    def test_missing_creator_view_is_created_and_filtered(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            action = command[2]
            if action == "+view-list":
                payload = {"ok": True, "data": {"items": []}}
            elif action == "+view-create":
                payload = {
                    "ok": True,
                    "data": {"items": [{"view_id": "vew_archie", "view_name": "Archie在摸鱼"}]},
                }
            elif action == "+view-set-filter":
                payload = {"ok": True, "data": {}}
            else:
                self.fail(f"未知操作: {action}")
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

        result = feishu_views.ensure_creator_view(
            "base_demo",
            "tbl_demo",
            "Archie在摸鱼",
            runner=runner,
        )

        self.assertEqual(result, {"view_id": "vew_archie", "name": "Archie在摸鱼", "created": True})
        self.assertEqual(
            [command[2] for command in calls],
            ["+view-list", "+view-create", "+view-set-filter"],
        )
        filter_command = calls[-1]
        sent_filter = json.loads(filter_command[filter_command.index("--json") + 1])
        self.assertEqual(sent_filter, feishu_views.creator_view_filter("Archie在摸鱼"))

    def test_web_profile_flow_prepares_creator_view_and_processes_only_videos(self):
        fetched = {
            "profile": {"nickname": "Archie在摸鱼"},
            "notes": [
                {"note_id": "video-note", "title": "视频", "type": "video"},
                {"note_id": "image-note", "title": "图文", "type": "normal"},
            ],
        }
        args = argparse.Namespace(since=None, no_transcribe=True, cleanup=False)
        ok_result = {"url": "", "ok": True, "steps": ["模拟"]}

        with (
            patch("web_app.fetch_profile.fetch_profile", return_value=fetched),
            patch("web_app.pipeline.ensure_profile_view") as ensure_view,
            patch("web_app.pipeline.process_note", return_value=ok_result) as process_note,
            patch("web_app.time.sleep"),
        ):
            web_app.process_profile_web("https://example.test/profile", args)

        ensure_view.assert_called_once_with("Archie在摸鱼")
        process_note.assert_called_once()
        self.assertIn("video-note", process_note.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
