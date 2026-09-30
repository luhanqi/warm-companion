from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from backend.app import db
from backend.app.agents import MemorySteward
from backend.app.blackboard import Blackboard
from backend.app.cognition import analyze_transcript, build_series, build_trend
from backend.app.cognition_eval import evaluate_cases
from backend.app.embeddings import cosine, embedding_is_local, hashed_vector, reranker_is_local
from backend.app.media import subtitle_timeline, to_webvtt
from backend.app.model_services import service_status


class InnovationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "test.db"
        self.board = Blackboard()
        db.init_db(self.board.conn)

    def tearDown(self) -> None:
        self.board.conn.close()
        db.DB_PATH = self.old_path
        self.temp_dir.cleanup()

    def test_accounts_have_isolated_memory(self) -> None:
        first = self.board.bind_user("elder-one")
        self.board.ensure_user("elder-one", "甲")
        self.board.add_fact("工作", "1958年进厂", "test")
        self.board.reset_user(first)

        second = self.board.bind_user("elder-two")
        self.board.ensure_user("elder-two", "乙")
        self.assertEqual([], self.board.list_facts())
        self.board.reset_user(second)

    def test_query_retrieval_prefers_relevant_memory(self) -> None:
        token = self.board.bind_user("elder-rag")
        self.board.ensure_user("elder-rag", "王阿姨")
        self.board.add_fact("工作", "1958年进入纺织厂工作", "test")
        self.board.add_fact("爱好", "喜欢在早晨打太极", "test")
        result = MemorySteward().retrieve(self.board, "进厂那一年发生了什么")
        self.assertIn("纺织厂", result["retrieved"][0]["text"])
        indexed = self.board.conn.execute(
            "SELECT COUNT(*) AS total FROM memory_embeddings WHERE user_id=?",
            ("elder-rag",),
        ).fetchone()
        self.assertGreater(indexed["total"], 0)
        self.board.reset_user(token)

    def test_language_trend_needs_enough_personal_samples(self) -> None:
        feature = analyze_transcript("那时候我在厂里工作，后来认识了很多老朋友。")
        self.assertGreater(feature["quality"], 0.5)
        rows = [feature for _ in range(4)]
        self.assertEqual("collecting", build_trend(rows)["level"])
        rows.extend(feature for _ in range(8))
        self.assertIn(build_trend(rows)["level"], ("stable", "watch", "attention"))

    def test_language_samples_are_aggregated_by_day(self) -> None:
        token = self.board.bind_user("elder-daily")
        self.board.ensure_user("elder-daily", "老人")
        features = analyze_transcript("后来我在厂里认识了许多朋友，我们每天一起上班。")
        self.board.add_language_sample("第一段有效讲述", features, "talk")
        self.board.add_language_sample("第二段有效讲述", features, "talk")
        rows = self.board.list_cognitive_daily_metrics()
        self.assertEqual(1, len(rows))
        self.assertEqual(2, rows[0]["sample_count"])
        trend = build_trend(rows)
        self.assertEqual(1, trend["day_count"])
        self.assertEqual(2, trend["sample_count"])
        self.board.reset_user(token)

    def test_memoir_persists_and_can_be_rewritten(self) -> None:
        token = self.board.bind_user("elder-book")
        self.board.ensure_user("elder-book", "老人")
        self.board.append_chapter("youth", "我年轻时在厂里工作。", "口述")
        chapter = next(item for item in self.board.list_chapters() if item["chapter_key"] == "youth")
        self.assertIn("厂里工作", chapter["body"])
        self.board.clear_chapter("youth")
        chapter = next(item for item in self.board.list_chapters() if item["chapter_key"] == "youth")
        self.assertEqual("", chapter["body"])
        self.board.reset_user(token)

    def test_photo_story_music_form_personal_storyboard(self) -> None:
        token = self.board.bind_user("elder-video")
        self.board.ensure_user("elder-video", "老人")
        photo = self.board.add_photo("old-photo.jpg", "年轻时的合影")
        project = self.board.add_memory_project(photo["id"], "molihua", "那一年我们刚进厂。", "进厂那年")
        self.assertEqual("storyboard", project["status"])
        voice = self.board.add_voice_session(
            "voice.webm", "那一年我们刚进厂。", 5000, "audio/webm", 0.2, 2, 0.08, 0.5
        )
        self.assertEqual(voice["id"], self.board.list_memory_projects()[0]["voice_session_id"])
        self.assertEqual("ready", self.board.list_memory_projects()[0]["status"])
        self.assertEqual(2, self.board.voice_summary()["average_pause_count"])
        self.assertEqual("molihua", self.board.list_memory_projects()[0]["song_id"])
        self.board.reset_user(token)

    def test_long_memoir_is_split_into_retrieval_chunks(self) -> None:
        token = self.board.bind_user("elder-chunks")
        self.board.ensure_user("elder-chunks", "老人")
        self.board.append_chapter("youth", "年轻时的故事。" * 100)
        chunks = [item for item in self.board.list_memory_documents() if item["kind"] == "chapter"]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(item["text"]) <= 320 for item in chunks))
        self.board.reset_user(token)

    def test_cloud_processing_requires_explicit_consent(self) -> None:
        token = self.board.bind_user("elder-consent")
        self.board.ensure_user("elder-consent", "老人")
        scopes = self.board.consent_scopes()
        self.assertFalse(scopes["cloud_conversation"])
        self.assertFalse(scopes["cloud_image_processing"])
        self.assertFalse(scopes["cloud_video_processing"])
        self.assertFalse(scopes["research_cognition_model"])
        self.board.set_consent_scope("cloud_conversation", True)
        self.assertTrue(self.board.consent_scopes()["cloud_conversation"])
        self.board.reset_user(token)

    def test_model_status_never_exposes_api_keys(self) -> None:
        with patch.dict(
            "os.environ",
            {"VISION_API_KEY": "secret-key", "VISION_BASE_URL": "https://example.invalid/v1", "VISION_MODEL": "qwen-test"},
            clear=False,
        ):
            status = service_status()
        self.assertTrue(status["vision"]["enabled"])
        self.assertEqual("qwen-test", status["vision"]["model"])
        self.assertNotIn("secret-key", str(status))

    def test_model_metadata_is_saved_with_personal_media(self) -> None:
        token = self.board.bind_user("elder-model-media")
        self.board.ensure_user("elder-model-media", "老人")
        photo = self.board.add_photo("old.jpg", "老照片")
        photo = self.board.set_photo_analysis(photo["id"], "照片中有一张木桌。", "qwen")
        self.assertEqual("qwen", photo["ai_provider"])
        voice = self.board.add_voice_session(
            "voice.webm", "今天很好", 3000, "audio/webm", asr_provider="SenseVoice", analysis={"emotion": "NEUTRAL"}
        )
        self.assertEqual("SenseVoice", voice["asr_provider"])
        project = self.board.add_memory_project(photo["id"], "", "今天很好", "旧时光")
        project = self.board.set_memory_project_video(
            project["id"], {"job_id": "task-1", "status": "succeeded", "provider": "Wan", "video_url": "/api/memory-videos/test.mp4"}
        )
        self.assertEqual("task-1", project["video_job_id"])
        self.assertTrue(self.board.owns_memory_video("/api/memory-videos/test.mp4"))
        self.board.reset_user(token)

    def test_personal_text_style_is_learned_without_impersonation_data(self) -> None:
        token = self.board.bind_user("elder-style")
        self.board.ensure_user("elder-style", "老人")
        for text in ("嗯，今天挺好的呀", "我想听听老歌呀", "然后我们去公园呀", "这个故事很好呀", "晚上早点休息呀"):
            self.board.add_message("user", text)
        style = self.board.speech_style_profile()
        self.assertEqual("available", style["status"])
        self.assertEqual(5, style["sample_count"])
        self.assertEqual("呀", style["preferred_ending"])
        memory = MemorySteward().retrieve(self.board, "今天聊什么")
        self.assertEqual("available", memory["speech_style"]["status"])
        self.board.reset_user(token)

    def test_memory_can_be_corrected_and_removed(self) -> None:
        token = self.board.bind_user("elder-correction")
        self.board.ensure_user("elder-correction", "老人")
        fact = self.board.add_fact("年代", "1959年进厂", "test")
        saved = self.board.update_fact(fact["id"], "年代", "1958年进厂")
        self.assertEqual("1958年进厂", saved["value"])
        self.board.delete_fact(fact["id"])
        self.assertEqual([], self.board.list_facts())
        self.board.reset_user(token)

    def test_family_series_contains_no_transcript(self) -> None:
        rows = []
        for index in range(3):
            item = analyze_transcript("后来我在厂里认识了许多朋友，我们常常一起回家。")
            item["created_at"] = "2026-09-%02d 10:00:00" % (20 + index)
            rows.append(item)
        series = build_series(rows)
        self.assertEqual(3, len(series))
        self.assertNotIn("transcript", series[0])

    def test_local_vectors_are_stable_and_rank_related_text(self) -> None:
        query = hashed_vector("年轻时进厂工作")
        related = cosine(query, hashed_vector("我年轻时进入纺织厂上班"))
        unrelated = cosine(query, hashed_vector("每天早晨喜欢在公园打太极"))
        self.assertGreater(related, unrelated)

    def test_loopback_model_services_do_not_require_cloud_consent(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "EMBEDDING_BASE_URL": "http://127.0.0.1:8004/v1",
                "RERANK_BASE_URL": "http://localhost:8004/v1",
            },
        ):
            self.assertTrue(embedding_is_local())
            self.assertTrue(reranker_is_local())
        with patch.dict("os.environ", {"EMBEDDING_BASE_URL": "https://example.com/v1"}):
            self.assertFalse(embedding_is_local())

    def test_subtitles_follow_recording_duration(self) -> None:
        cues = subtitle_timeline("那一年我进了工厂。后来认识了很多朋友。", 6000)
        self.assertEqual(0, cues[0]["start_ms"])
        self.assertEqual(6000, cues[-1]["end_ms"])
        vtt = to_webvtt(cues)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("进了工厂", vtt)

    def test_evaluation_harness_reports_program_metrics(self) -> None:
        report = evaluate_cases([{"name": "insufficient data", "expected_attention": False, "samples": []}])
        self.assertEqual(1, report["true_negative"])
        self.assertIn("临床", report["warning"])


if __name__ == "__main__":
    unittest.main()
