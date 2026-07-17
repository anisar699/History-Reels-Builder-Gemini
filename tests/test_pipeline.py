import unittest
from history_reels import config
from history_reels.jobs import create_generation_job
from history_reels.script_generator import ScriptConfig

class TestHistoryReels(unittest.TestCase):
    def test_config_initialization(self):
        self.assertIsNotNone(config.TEMP_DIR)
        self.assertIsNotNone(config.OUTPUT_DIR)
        self.assertEqual(config.VOICE_ID, "ur-PK-AsadNeural")

    def test_pydantic_validation(self):
        data = {
            "title": "Titanic",
            "year": "1912",
            "bg_music_vibe": "sad",
            "captions": ["Test slide 1", "Test slide 2", "Test slide 3"],
            "narrations": ["Urdu speech 1", "Urdu speech 2", "Urdu speech 3"],
            "queries": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"],
            "seo_title": "Title hook",
            "seo_description": "Description",
            "seo_hashtags": "#Test",
            "seo_short_caption": "Short"
        }
        model = ScriptConfig(**data)
        self.assertEqual(model.title, "Titanic")
        self.assertEqual(model.bg_music_vibe, "sad")
        self.assertEqual(len(model.captions), 3)
        self.assertEqual(len(model.narrations), 3)
        self.assertEqual(len(model.queries), 8)

    def test_pydantic_invalid_vibe_falls_back_to_mystery(self):
        model = ScriptConfig(bg_music_vibe="invalid_vibe")
        self.assertEqual(model.bg_music_vibe, "mystery")

    def test_pydantic_short_queries_are_padded(self):
        model = ScriptConfig(queries=["q1", "q2", "q3", "q4", "q5", "q6", "q7"])
        self.assertEqual(len(model.queries), 8)
        self.assertEqual(model.queries[-1], "cinematic")

    def test_generation_jobs_use_unique_workspaces_and_snapshots(self):
        original_vibe = config.BG_MUSIC_VIBE
        try:
            config.BG_MUSIC_VIBE = "epic"
            first = create_generation_job(config)
            config.BG_MUSIC_VIBE = "sad"
            second = create_generation_job(config)

            self.assertNotEqual(first.job_id, second.job_id)
            self.assertNotEqual(first.TOPIC_TEMP_DIR, second.TOPIC_TEMP_DIR)
            self.assertIn("jobs", first.TOPIC_TEMP_DIR)
            self.assertEqual(first.BG_MUSIC_VIBE, "epic")
            self.assertEqual(second.BG_MUSIC_VIBE, "sad")

            first.DOWNLOADED_VIDEO_IDS.add("first-job-media")
            first.VIDEO_ATTRIBUTIONS.append("First job attribution")
            self.assertNotIn("first-job-media", second.DOWNLOADED_VIDEO_IDS)
            self.assertEqual(second.VIDEO_ATTRIBUTIONS, [])
        finally:
            config.BG_MUSIC_VIBE = original_vibe

if __name__ == "__main__":
    unittest.main()
