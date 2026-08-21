import unittest
from unittest.mock import patch

import fetch_profile


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSigner:
    def sign_headers_get(self, **kwargs):
        return {"X-Test-Signature": "signed"}


class FetchProfileTests(unittest.TestCase):
    def test_api_fetch_reads_flat_fields_and_all_pages_without_duplicates(self):
        pages = [
            FakeResponse(
                {
                    "success": True,
                    "code": 0,
                    "data": {
                        "notes": [
                            {
                                "note_id": "note-first",
                                "display_title": "第一页",
                                "type": "video",
                                "time": 100,
                                "cover": {"url": "cover-first"},
                                "xsec_token": "token-first",
                                "interact_info": {"liked_count": "10"},
                            },
                            {
                                "note_id": "note-pinned",
                                "display_title": "置顶作品",
                                "type": "video",
                                "time": 90,
                                "cover": {},
                                "xsec_token": "token-pinned",
                                "interact_info": {"liked_count": "9"},
                            },
                        ],
                        "cursor": "page-two",
                        "has_more": True,
                    },
                }
            ),
            FakeResponse(
                {
                    "success": True,
                    "code": 0,
                    "data": {
                        "notes": [
                            {
                                "note_id": "note-pinned",
                                "display_title": "置顶作品",
                                "type": "video",
                                "time": 90,
                                "cover": {},
                                "xsec_token": "token-pinned",
                                "interact_info": {"liked_count": "9"},
                            },
                            {
                                "note_id": "note-second",
                                "display_title": "第二页",
                                "type": "video",
                                "time": 80,
                                "cover": {"url": "cover-second"},
                                "xsec_token": "token-second",
                                "interact_info": {"liked_count": "8"},
                            },
                        ],
                        "cursor": "done",
                        "has_more": False,
                    },
                }
            ),
        ]

        with (
            patch("fetch_profile._xhshow_client", return_value=FakeSigner()),
            patch("fetch_profile.requests.get", side_effect=pages),
        ):
            notes = fetch_profile._fetch_notes_via_api("user-demo")

        self.assertEqual(
            [note["note_id"] for note in notes],
            ["note-first", "note-pinned", "note-second"],
        )
        self.assertEqual(notes[0]["title"], "第一页")
        self.assertEqual(notes[0]["type"], "video")
        self.assertEqual(notes[0]["liked_text"], "10")

    def test_api_fetch_rejects_video_cards_without_note_ids(self):
        response = FakeResponse(
            {
                "success": True,
                "code": 0,
                "data": {
                    "notes": [
                        {
                            "display_title": "缺少ID的视频",
                            "type": "video",
                            "time": 100,
                            "cover": {},
                            "interact_info": {},
                        }
                    ],
                    "cursor": "",
                    "has_more": False,
                },
            }
        )

        with (
            patch("fetch_profile._xhshow_client", return_value=FakeSigner()),
            patch("fetch_profile.requests.get", return_value=response),
        ):
            with self.assertRaisesRegex(RuntimeError, "更新Cookie|接口数据异常"):
                fetch_profile._fetch_notes_via_api("user-demo")


if __name__ == "__main__":
    unittest.main()
