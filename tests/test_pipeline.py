import unittest
from history_reels import config
from history_reels.script_generator import ScriptConfig

class TestHistoryReels(unittest.TestCase):
    def test_config_initialization(self):
        self.assertIsNotNone(config.TEMP_DIR)
        self.assertIsNotNone(config.OUTPUT_DIR)
        self.assertEqual(config.VOICE_ID, "ur-PK-AsadNeural")

    def test_pydantic_validation(self):
        # Valid test data
        data = {
            "title": "Titanic",
            "year": "1912",
            "bg_music_vibe": "sad",
            "caption_text_1": "Test slide 1",
            "caption_text_2": "Test slide 2",
            "caption_text_3": "Test slide 3",
            "caption_text_4": "Test slide 4",
            "narration_text_1": "Urdu speech 1",
            "narration_text_2": "Urdu speech 2",
            "narration_text_3": "Urdu speech 3",
            "narration_text_4": "Urdu speech 4",
            "queries": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"],
            "seo_title": "Title hook",
            "seo_description": "Description",
            "seo_hashtags": "#Test",
            "seo_short_caption": "Short"
        }
        model = ScriptConfig(**data)
        self.assertEqual(model.title, "Titanic")
        self.assertEqual(model.bg_music_vibe, "sad")
        self.assertEqual(len(model.queries), 8)

    def test_pydantic_invalid_vibe(self):
        # Invalid music vibe test data
        data = {
            "title": "Titanic",
            "year": "1912",
            "bg_music_vibe": "invalid_vibe",  # Must be mystery, epic, sad, ancient
            "caption_text_1": "Test slide 1",
            "caption_text_2": "Test slide 2",
            "caption_text_3": "Test slide 3",
            "caption_text_4": "Test slide 4",
            "narration_text_1": "Urdu speech 1",
            "narration_text_2": "Urdu speech 2",
            "narration_text_3": "Urdu speech 3",
            "narration_text_4": "Urdu speech 4",
            "queries": ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"],
            "seo_title": "Title hook",
            "seo_description": "Description",
            "seo_hashtags": "#Test",
            "seo_short_caption": "Short"
        }
        with self.assertRaises(Exception):
            ScriptConfig(**data)

    def test_pydantic_invalid_queries_count(self):
        # Invalid queries count (7 instead of 8)
        data = {
            "title": "Titanic",
            "year": "1912",
            "bg_music_vibe": "sad",
            "caption_text_1": "Test slide 1",
            "caption_text_2": "Test slide 2",
            "caption_text_3": "Test slide 3",
            "caption_text_4": "Test slide 4",
            "narration_text_1": "Urdu speech 1",
            "narration_text_2": "Urdu speech 2",
            "narration_text_3": "Urdu speech 3",
            "narration_text_4": "Urdu speech 4",
            "queries": ["q1", "q2", "q3", "q4", "q5", "q6", "q7"],  # 7 items
            "seo_title": "Title hook",
            "seo_description": "Description",
            "seo_hashtags": "#Test",
            "seo_short_caption": "Short"
        }
        with self.assertRaises(Exception):
            ScriptConfig(**data)

if __name__ == "__main__":
    unittest.main()
