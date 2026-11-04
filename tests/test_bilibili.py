import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tempfile
import unittest

from review_sprint.bilibili import (
    BiliClient, BiliError, locate_segment, mixin_key, sign_params,
)
from review_sprint.topics import build_queries, detect_domain


class BilibiliTest(unittest.TestCase):
    def test_mixin_and_sign(self):
        key = mixin_key(
            "7cd084941338484aae1ad9425b84077c",
            "4932caff0ff746eab6f01bf08b70ac45",
        )
        self.assertEqual(key, "ea1db124af3c7062474693fa704f4ff8")
        signed = sign_params(
            {"bar": 514, "foo": 114, "zab": 1919810}, key, now=1702204169,
        )
        self.assertEqual(signed["w_rid"], "8f6f2b5b3d485fe1886cec6a0be8c5d4")

    def test_domain_and_queries(self):
        self.assertEqual(detect_domain("补码 溢出 IEEE754 x86-64"), "cs_systems")
        queries = build_queries(["补码", "整数"], "cs_systems", "计算机系统基础")
        self.assertTrue(any("计算机系统" in q for q in queries))

    def test_locate_segment(self):
        cues = [
            {"from": 0, "to": 5, "content": "开场"},
            {"from": 10, "to": 15, "content": "补码的符号位参与运算"},
            {"from": 190, "to": 200, "content": "溢出就是结果超出范围"},
        ]
        segment = locate_segment(cues, ["补码", "溢出"], window=120)
        self.assertIsNotNone(segment)
        self.assertEqual(segment["start"], 10)

    def test_score_rejects_off_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = BiliClient(Path(tmp), transport=lambda url, params: {"code": 0})
            kp = {"id": "K1", "title": "补码与溢出", "anchors": ["补码", "溢出"]}
            video = {
                "bvid": "BV1xx411c7mD",
                "title": "中职英语 阅读理解 速成",
                "description": "英语",
                "pages": [],
                "play": 10000,
            }
            scored = client.score_video(kp, video, [], domain="cs_systems")
            self.assertEqual(scored["score"], 0)
            self.assertEqual(scored.get("rejected"), "negative")

    def test_recommend_fixture(self):
        nav = {
            "code": 0,
            "data": {"wbi_img": {
                "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
            }},
        }
        search = {
            "code": 0,
            "data": {"result": [
                {
                    "bvid": "BV1xx411c7mD",
                    "title": "<em>补码</em>与溢出：计算机系统基础",
                    "author": "CS老师", "play": 120000, "description": "补码 溢出",
                    "tag": "计算机系统", "duration": "12:30", "pubdate": 1700000000,
                    "typename": "校园学习",
                },
                {
                    "bvid": "BV1yy411c7mE",
                    "title": "中职英语 阅读理解 速成",
                    "author": "英语老师", "play": 900000, "description": "中职英语",
                    "tag": "英语", "duration": "20:00", "pubdate": 1700000000,
                    "typename": "外语",
                },
            ]},
        }
        view = {
            "code": 0,
            "data": {
                "bvid": "BV1xx411c7mD", "title": "补码与溢出：计算机系统基础",
                "owner": {"name": "CS老师"}, "desc": "补码 溢出 讲解",
                "duration": 750, "stat": {"view": 120000, "like": 5000},
                "pages": [{"cid": 111, "page": 1, "part": "补码与溢出", "duration": 750}],
            },
        }
        player = {"code": 0, "data": {"subtitle": {"subtitles": [
            {"lan": "zh-CN", "subtitle_url": "//example.com/sub.json"}
        ]}}}
        subtitle = {"body": [
            {"from": 10, "to": 15, "content": "补码的符号位参与运算"},
            {"from": 190, "to": 200, "content": "溢出就是结果超出范围"},
        ]}

        def transport(url, params):
            if url.endswith("/x/web-interface/nav"):
                return nav
            if "search/type" in url:
                return search
            if "/x/web-interface/view" in url:
                return view
            if "player/wbi/v2" in url:
                return player
            if url.endswith("/sub.json"):
                return subtitle
            return {"code": -404, "message": "no fixture"}

        with tempfile.TemporaryDirectory() as tmp:
            client = BiliClient(Path(tmp), transport=transport, rate_seconds=0)
            kp = {"id": "K1", "title": "补码与溢出", "anchors": ["补码", "溢出"]}
            result = client.recommend(kp, domain="cs_systems", course="计算机系统基础", limit=2)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(result["items"]), 1)
            item = result["items"][0]
            self.assertEqual(item["bvid"], "BV1xx411c7mD")
            self.assertIn("BV1xx411c7mD", item["link"])
            self.assertNotIn("BV1yy411c7mE", item["link"])
            self.assertGreaterEqual(item["score"], 0.5)

    def test_insecure_rejects_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BiliError):
                BiliClient(Path(tmp), cookie="SESSDATA=secret", insecure=True)

    def test_subtitle_only_adds_score(self):
        kp = {"id": "K1", "title": "补码与溢出", "anchors": ["补码", "溢出"]}
        video = {
            "bvid": "BV1xx411c7mD", "title": "补码与溢出", "description": "",
            "pages": [{"page": 1, "part": "补码与溢出"}], "play": 10000,
        }
        cues = [{"from": 1, "to": 2, "content": "补码的符号位参与运算"}]
        with tempfile.TemporaryDirectory() as tmp:
            client = BiliClient(Path(tmp))
            base = client.score_video(kp, video, [], domain="cs_systems")
            with_cues = client.score_video(kp, video, cues, domain="cs_systems")
            self.assertGreaterEqual(with_cues["score"], base["score"])

    def test_cached_bvids(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = BiliClient(Path(tmp))
            client.cache_put("search:x", [{"bvid": "BV1xx411c7mD"}])
            self.assertIn("BV1xx411c7mD", client.cached_bvids())


if __name__ == "__main__":
    unittest.main()
