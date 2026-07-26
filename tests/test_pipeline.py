import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import requests

from history_reels import config
from history_reels.acceptance import classify_acceptance_failure, validate_video_artifact
from history_reels.cli import check_inputs, copy_deliverables, download_visuals, generate_video_for_topic, main as cli_main
from history_reels.font_manager import get_font_preset, prepare_caption_font
from history_reels.music_library import MUSIC_TRACK_DURATION_SECONDS, local_track_command, resolve_music_vibe
from history_reels.job_manager import JobManager
from history_reels.job_store import JobStore, categorize_error, snapshot_safe_settings, get_dashboard_metrics
from history_reels.input_validation import validate_external_url, validate_uploaded_file
from history_reels.jobs import create_generation_job
from history_reels.news_scraper import fetch_public_response
from history_reels.renderer import build_video_frames, crop_window, run_ffmpeg
from history_reels.security import dashboard_auth_required, hash_password, save_local_env_values, session_key_override_allowed, verify_password
from history_reels.script_generator import ScriptConfig, build_api_request_error, fetch_ai_script
from history_reels.stock_media import (
    accept_downloaded_image,
    acceptable_media_metadata,
    diversify_media_queries,
    download_clip_for_query,
    effective_min_media_dimension,
    media_candidate_score,
    media_text_relevance_score,
    media_quality_score,
    is_safe_media_metadata,
    _safe_error_message,
)
from history_reels.ffmpeg_runner import RenderError, kill_job_processes, run_command
from history_reels.subtitles import (
    _font_for_text,
    _load_mixed_script_fallback,
    render_caption_overlays,
    write_ass_subtitles,
)
from history_reels.verification import run_verification_matrix, verify_deliverable
from history_reels.voiceover import filter_voices_for_language, generate_voiceover
from history_reels.visual_quality import _timeline_failures, hash_distance, inspect_image
from history_reels.worker import run_job

class TestHistoryReels(unittest.TestCase):
    def test_local_api_key_save_updates_only_requested_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("EXISTING_VALUE=keep\nGROQ_API_KEY=old-value\n", encoding="utf-8")
            saved = save_local_env_values(env_path, {
                "GROQ_API_KEY": "new-value",
                "OPENAI_API_KEY": "",
            })
            content = env_path.read_text(encoding="utf-8")
            self.assertEqual(saved, ["GROQ_API_KEY"])
            self.assertIn("EXISTING_VALUE=keep", content)
            self.assertIn("GROQ_API_KEY='new-value'", content)
            self.assertNotIn("OPENAI_API_KEY", content)

    def test_pinterest_is_blocked_for_new_and_retried_media_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                ALLOWED_SOURCES=["pinterest"],
                MEDIA_PREFERENCE="images",
                DOWNLOADED_VIDEO_IDS=set(),
                VIDEO_ATTRIBUTIONS=[],
            )
            with patch("history_reels.stock_media.search_pinterest_images") as pinterest_search:
                self.assertFalse(download_clip_for_query("printing press", 1, job))
            pinterest_search.assert_not_called()

    def test_openai_429_errors_are_safe_and_actionable(self):
        response = requests.Response()
        response.status_code = 429
        response.headers["x-request-id"] = "req_test-123"
        response._content = b'{"error":{"type":"insufficient_quota","code":"insufficient_quota","message":"sensitive provider detail"}}'
        error = build_api_request_error("OpenAI", response, requests.HTTPError(response=response))

        self.assertIn("insufficient_quota", str(error))
        self.assertIn("billing", str(error))
        self.assertNotIn("sensitive provider detail", str(error))
        self.assertEqual(classify_acceptance_failure(error), "blocked_quota")

        settings = SimpleNamespace(OPENAI_API_KEY="not-a-real-key", TARGET_DURATION=30)
        with (
            patch("history_reels.script_generator.requests.post", return_value=response),
            self.assertRaisesRegex(RuntimeError, "insufficient_quota"),
        ):
            fetch_ai_script("Printing press", provider="openai", settings=settings)

        response._content = b'{"error":{"type":"rate_limit_exceeded"}}'
        error = build_api_request_error("OpenAI", response, requests.HTTPError(response=response))
        self.assertIn("rate limit", str(error))
        self.assertEqual(classify_acceptance_failure(error), "blocked_rate_limit")

    def test_staging_artifact_validation_requires_audio_video_and_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, "acceptance.mp4")
            seo_path = os.path.join(temp_dir, "acceptance.txt")
            with open(video_path, "wb") as video:
                video.write(b"video")
            with open(seo_path, "w", encoding="utf-8") as seo:
                seo.write("SEO package")
            probe = SimpleNamespace(stdout='{"streams":[{"codec_type":"video","codec_name":"h264","pix_fmt":"yuv420p"},{"codec_type":"audio","codec_name":"aac","sample_rate":"48000","channels":2}],"format":{"duration":"30.0"}}')
            with patch("history_reels.acceptance.subprocess.run", return_value=probe):
                result = validate_video_artifact(Path(video_path), Path(seo_path), 30)
            self.assertEqual(result["stream_types"], ["audio", "video"])
            self.assertEqual(result["actual_duration_seconds"], 30.0)
            self.assertEqual(result["audio_sample_rate"], 48_000)

    def test_verification_matrix_covers_all_supported_languages(self):
        report = run_verification_matrix()
        self.assertTrue(report["passed"])
        self.assertEqual({case["language"] for case in report["cases"]}, {"Urdu", "English", "Hindi", "Arabic", "Roman Urdu"})

    def test_post_render_verification_checks_streams_dimensions_and_writes_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir, "reel.mp4")
            seo_path = Path(temp_dir, "reel.txt")
            video_path.write_bytes(b"v" * 2048)
            seo_path.write_text("SEO", encoding="utf-8")
            probe = SimpleNamespace(stdout='{"streams":[{"codec_type":"video","width":720,"height":1280,"codec_name":"h264","pix_fmt":"yuv420p"},{"codec_type":"audio","codec_name":"aac","sample_rate":"48000","channels":2}],"format":{"duration":"18.5","size":"2048"}}')
            job = SimpleNamespace(
                video_path=str(video_path), seo_path=str(seo_path), VIDEO_WIDTH=720, VIDEO_HEIGHT=1280,
                OUTPUT_DIR=temp_dir, OUTPUT_NAME="reel",
            )
            with (
                patch("history_reels.verification.subprocess.run", return_value=probe),
                patch(
                    "history_reels.verification.inspect_rendered_video",
                    return_value={"passed": True, "sample_count": 3, "failed_samples": 0},
                ),
            ):
                report = verify_deliverable(job)
            self.assertTrue(report["passed"])
            self.assertEqual(report["audio_sample_rate"], 48_000)
            self.assertTrue(report["visual_qa"]["passed"])
            self.assertTrue(Path(job.VERIFICATION_REPORT_PATH).is_file())

    def test_rejects_private_urls_and_invalid_upload_signatures(self):
        with patch("history_reels.input_validation.socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
            self.assertFalse(validate_external_url("http://localhost:8080")[0])
        with patch("history_reels.input_validation.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
            self.assertTrue(validate_external_url("https://example.com/article")[0])

        invalid_png = SimpleNamespace(size=8, getbuffer=lambda: memoryview(b"not-a-png"))
        valid_png = SimpleNamespace(size=8, getbuffer=lambda: memoryview(b"\x89PNG\r\n\x1a\n"))
        self.assertFalse(validate_uploaded_file(invalid_png, "png")[0])
        self.assertTrue(validate_uploaded_file(valid_png, "png")[0])
        invalid_xlsx = SimpleNamespace(size=4, getbuffer=lambda: memoryview(b"PK\x03\x04"))
        self.assertFalse(validate_uploaded_file(invalid_xlsx, "xlsx")[0])

    def test_news_fetch_revalidates_redirect_targets(self):
        response = requests.Response()
        response.status_code = 302
        response.headers["Location"] = "http://127.0.0.1/private"
        response.close = lambda: None

        def resolve(host, _port):
            address = "127.0.0.1" if host == "127.0.0.1" else "93.184.216.34"
            return [(None, None, None, None, (address, 0))]

        with (
            patch("history_reels.input_validation.socket.getaddrinfo", side_effect=resolve),
            patch("history_reels.news_scraper.requests.get", return_value=response),
        ):
            with self.assertRaises(ValueError):
                fetch_public_response("https://example.com/article", headers={})

    def test_dashboard_security_flags_and_password_verification(self):
        password_hash = hashlib.sha256(b"correct horse battery staple").hexdigest()
        with patch.dict(os.environ, {
            "DASHBOARD_REQUIRE_AUTH": "true",
            "DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE": "false",
        }, clear=False):
            self.assertTrue(dashboard_auth_required())
            self.assertFalse(session_key_override_allowed())
            self.assertTrue(verify_password("correct horse battery staple", password_hash))
            self.assertFalse(verify_password("wrong password", password_hash))

        stronger_hash = hash_password("correct horse battery staple", salt=b"0123456789abcdef", iterations=100_000)
        self.assertTrue(verify_password("correct horse battery staple", stronger_hash))
        self.assertFalse(verify_password("wrong password", stronger_hash))

        # Public auth on + override unset => browser key entry blocked.
        cleaned = {
            key: value for key, value in os.environ.items()
            if key not in {"DASHBOARD_REQUIRE_AUTH", "DASHBOARD_ALLOW_SESSION_KEY_OVERRIDE"}
        }
        with patch.dict(os.environ, {**cleaned, "DASHBOARD_REQUIRE_AUTH": "true"}, clear=True):
            self.assertTrue(dashboard_auth_required())
            self.assertFalse(session_key_override_allowed())
        # Local desktop (auth off) + override unset => key save allowed.
        with patch.dict(os.environ, cleaned, clear=True):
            self.assertFalse(dashboard_auth_required())
            self.assertTrue(session_key_override_allowed())

    def test_renderer_always_uses_fixed_fade_transition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for index in range(1, 5):
                open(os.path.join(temp_dir, f"raw_clip{index}.jpg"), "wb").close()
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                QUERIES=["one", "two", "three", "four"],
                CROSSFADE_DUR=0.5,
                CLIP_DURATION_TARGET=5.0,
                VIDEO_WIDTH=720,
                VIDEO_HEIGHT=1280,
                FPS=25,
                VIDEO_TRANSITION="slideleft",
            )
            with patch("history_reels.renderer.run_command") as run:
                build_video_frames(job, voice_dur=20.0)
            final_command = run.call_args_list[-1].args[0]
            filter_graph = final_command[final_command.index("-filter_complex") + 1]
            self.assertIn("transition=fade", filter_graph)
            self.assertNotIn("transition=slideleft", filter_graph)

    def test_renderer_reuses_valid_media_when_some_downloads_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "raw_clip1.mp4")
            open(source_path, "wb").close()
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                QUERIES=["one"],
                CROSSFADE_DUR=0.5,
                CLIP_DURATION_TARGET=5.0,
                VIDEO_WIDTH=720,
                VIDEO_HEIGHT=1280,
                FPS=25,
            )
            with (
                patch("history_reels.renderer.get_video_dimensions", return_value=(720, 1280)),
                patch("history_reels.renderer.run_command") as run,
            ):
                build_video_frames(job, voice_dur=20.0)

            clip_commands = [call.args[0] for call in run.call_args_list[:4]]
            self.assertEqual(job.NUM_CLIPS, 4)
            self.assertTrue(all(source_path in command for command in clip_commands))

    def test_renderer_uses_slide_level_durations_and_matching_fade_offsets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for index in range(1, 4):
                Path(temp_dir, f"raw_clip{index}.mp4").write_bytes(b"video")
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                QUERIES=["one", "two", "three"],
                SLIDE_TIMINGS=[3.0, 8.0, 12.0],
                MEDIA_QA_BY_INDEX={},
                CROSSFADE_DUR=0.5,
                CLIP_DURATION_TARGET=5.0,
                VIDEO_WIDTH=720,
                VIDEO_HEIGHT=1280,
                FPS=25,
            )
            with (
                patch("history_reels.renderer.get_video_dimensions", return_value=(1280, 720)),
                patch("history_reels.renderer.run_command") as run,
            ):
                build_video_frames(job, voice_dur=12.0)

            clip_commands = [call.args[0] for call in run.call_args_list[:3]]
            durations = [
                float(command[command.index("-t") + 1])
                for command in clip_commands
            ]
            self.assertEqual(durations, [3.5, 5.5, 4.0])
            fade_command = run.call_args_list[-1].args[0]
            fade_graph = fade_command[fade_command.index("-filter_complex") + 1]
            self.assertIn("offset=3.000", fade_graph)
            self.assertIn("offset=8.000", fade_graph)

    def test_download_visuals_reports_when_no_usable_media_is_available(self):
        job = SimpleNamespace(QUERIES=["one", "two"], CLIP_DURATION_TARGET=5.0)
        with patch("history_reels.cli.download_clip_for_query", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "No usable media"):
                download_visuals(job, voice_dur=10.0)

    def test_copy_deliverables_copies_video_and_seo_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "workspace")
            output_dir = os.path.join(temp_dir, "output")
            os.makedirs(source_dir)
            os.makedirs(output_dir)
            Path(source_dir, "output.mp4").write_bytes(b"video")
            Path(source_dir, "output.txt").write_text("SEO package", encoding="utf-8")
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=source_dir,
                OUTPUT_DIR=output_dir,
                video_path=os.path.join(output_dir, "reel.mp4"),
                seo_path=os.path.join(output_dir, "reel.txt"),
                INTRO_BUMPER=None,
                OUTRO_BUMPER=None,
            )
            self.assertTrue(copy_deliverables(job))
            self.assertEqual(Path(job.video_path).read_bytes(), b"video")
            self.assertEqual(Path(job.seo_path).read_text(encoding="utf-8"), "SEO package")

    def test_renderer_mixes_music_and_burns_captions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            font_path = os.path.join(temp_dir, "font.ttf")
            open(font_path, "wb").close()
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                MUSIC_DIR=temp_dir,
                BG_MUSIC_VIBE="mystery",
                BG_MUSIC_TRACK_INDEX=1,
                COLOR_FILTER=None,
                SHOW_PROGRESS_BAR=False,
                SHOW_WATERMARK=False,
                OUTPUT_DIR=temp_dir,
                FONT_PATH=font_path,
            )
            with (
                patch("history_reels.renderer.run_command") as run,
                patch("history_reels.renderer.write_ass_subtitles") as subtitles,
                patch("history_reels.renderer.setup_fontconfig", return_value=os.path.join(temp_dir, "fonts.conf")) as fontconfig,
            ):
                run_ffmpeg(job, voice_dur=12.0)

            audio_command = run.call_args_list[0].args[0]
            audio_filter = audio_command[audio_command.index("-filter_complex") + 1]
            merge_command = run.call_args_list[-1].args[0]
            merge_filter = merge_command[merge_command.index("-filter_complex") + 1]
            self.assertEqual(audio_command[:4], ["ffmpeg", "-y", "-stream_loop", "-1"])
            self.assertIn("sidechaincompress=", audio_filter)
            self.assertIn("acompressor=", audio_filter)
            self.assertIn("loudnorm=I=-16.0:TP=-1.5:LRA=11.0", audio_filter)
            self.assertIn("subtitles=", merge_filter)
            self.assertEqual(merge_command[merge_command.index("-t") + 1], "12.000")
            subtitles.assert_called_once()
            fontconfig.assert_called_once_with(job)
            # FONTCONFIG_FILE is injected only into the merge subprocess env.
            merge_kwargs = run.call_args_list[-1].kwargs
            self.assertIn("env", merge_kwargs)
            self.assertIn("FONTCONFIG_FILE", merge_kwargs["env"])

    def test_config_initialization(self):
        self.assertIsNotNone(config.TEMP_DIR)
        self.assertIsNotNone(config.OUTPUT_DIR)
        self.assertEqual(config.VOICE_ID, "ur-PK-AsadNeural")

    def test_removed_pipeline_options_are_dropped_from_job_snapshots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(
                TEMP_DIR=temp_dir,
                OUTPUT_DIR=temp_dir,
                AMBIENT_SOUND="rain",
                CAMERA_SHAKE=True,
                CINEMATIC_GRAIN=True,
                TRANSITION_SFX=True,
                VOICE_PITCH="+15Hz",
                TARGET_PLATFORM="TikTok",
                WATERMARK_TEXT="@legacy",
                PROGRESS_BAR_COLOR="red",
                PROGRESS_BAR_HEIGHT=20,
                CONTENT_NICHE="Technology & AI",
                VISUAL_STYLE="Cyberpunk",
                BG_MUSIC_VIBE="random",
                VIDEO_TRANSITION="pixelize",
                COLOR_FILTER="cyberpunk",
            )
            job = create_generation_job(runtime)
            for removed_name in (
                "AMBIENT_SOUND",
                "CAMERA_SHAKE",
                "CINEMATIC_GRAIN",
                "TRANSITION_SFX",
                "VOICE_PITCH",
                "TARGET_PLATFORM",
                "WATERMARK_TEXT",
                "PROGRESS_BAR_COLOR",
                "PROGRESS_BAR_HEIGHT",
                "AUDIO_DUCKING",
                "VOICE_MASTERING",
                "CONTENT_NICHE",
                "VISUAL_STYLE",
                "VIDEO_TRANSITION",
            ):
                self.assertNotIn(removed_name, job.values)
            self.assertEqual(job.BG_MUSIC_VIBE, "mystery")
            self.assertIsNone(job.COLOR_FILTER)

    def test_default_demo_copy_is_not_history_specific(self):
        self.assertNotIn("baghdad", config.TOPIC_TITLE.lower())
        self.assertNotIn("#history", config.SEO_HASHTAGS.lower())
        self.assertEqual(JobManager._label(None, None), "Universal creator demo")

    def test_custom_caption_font_is_not_overwritten_by_default_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = os.path.join(temp_dir, "brand-font.ttf")
            with open(custom_path, "wb") as font:
                font.write(b"0" * 2048)
            job = SimpleNamespace(
                ASSETS_DIR=temp_dir,
                CUSTOM_FONT_PATH=custom_path,
                CUSTOM_FONT_FAMILY="Brand Font",
                CAPTION_FONT_PRESET="Noto Sans Arabic",
            )
            result = prepare_caption_font(job, lambda _url, _path: self.fail("custom font should not download"))
            self.assertEqual(result, custom_path)
            self.assertEqual(job.FONT_PATH, custom_path)
            self.assertEqual(job.CAPTION_FONT_FAMILY, "Brand Font")

    def test_language_voice_filter_does_not_offer_unrelated_locales(self):
        voices = [{"id": "ur-PK-AsadNeural"}, {"id": "hi-IN-MadhurNeural"}, {"id": "ar-SA-HamedNeural"}]
        self.assertEqual([voice["id"] for voice in filter_voices_for_language(voices, "Hindi")], ["hi-IN-MadhurNeural"])
        self.assertEqual([voice["id"] for voice in filter_voices_for_language(voices, "Arabic")], ["ar-SA-HamedNeural"])

    def test_voiceover_target_duration_never_adds_a_silent_final_slide(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                NARRATIONS=["پہلا حصہ", "دوسرا حصہ"],
                VOICE_PROVIDER="edge-tts",
                VOICE_ID="ur-PK-AsadNeural",
                TARGET_DURATION=120,
                job_id="voice-test",
            )
            with (
                patch("history_reels.voiceover.run_command") as run,
                patch("history_reels.voiceover.get_audio_duration", side_effect=[3.0, 4.0]),
            ):
                duration = generate_voiceover(job)

            self.assertEqual(duration, 7.0)
            self.assertEqual(job.SLIDE_TIMINGS, [3.0, 7.0])
            self.assertEqual(job.DURATION_SHORTFALL, 113.0)
            labels = [call.kwargs.get("label") for call in run.call_args_list]
            self.assertNotIn("voice pad", labels)

    def test_local_music_supports_every_dashboard_vibe_without_download_urls(self):
        self.assertEqual(resolve_music_vibe("modern"), "modern")
        self.assertEqual(resolve_music_vibe("unknown"), "mystery")
        command = local_track_command("intense", "track.mp3")
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("anoisesrc", " ".join(command))
        self.assertEqual(command[-1], "track.mp3")
        self.assertNotEqual(local_track_command("intense", "track.mp3", 1), local_track_command("intense", "track.mp3", 5))
        self.assertIn(str(MUSIC_TRACK_DURATION_SECONDS), command)
        self.assertNotIn("afade=", command[command.index("-filter_complex") + 1])

    def test_media_quality_prefers_usable_vertical_sources(self):
        job = SimpleNamespace(VIDEO_WIDTH=720, VIDEO_HEIGHT=1280, MIN_MEDIA_DIMENSION=480)
        vertical = media_quality_score(720, 1280, job, duration=12)
        landscape = media_quality_score(1280, 720, job, duration=12)
        self.assertGreater(vertical, landscape)
        self.assertEqual(media_quality_score(320, 180, job, duration=12), -1)

    def test_media_queries_spread_repeated_concepts_and_candidate_ranking_is_stable(self):
        queries = [
            "artificial intelligence technology",
            "futuristic AI concept",
            "AI applications in daily life",
            "AI workplace",
        ]
        diversified = diversify_media_queries(queries)
        self.assertEqual(diversified[0], queries[0])
        self.assertNotEqual(diversified[1], queries[1])
        self.assertEqual(len(diversified), len(queries))
        self.assertTrue(all(value.startswith(original) for value, original in zip(diversified, queries)))

        job = SimpleNamespace(MEDIA_CREATORS_USED={"repeat creator"})
        top_relevant = media_candidate_score(20, 0, "new creator", job)
        later_result = media_candidate_score(20, 5, "new creator", job)
        repeated_creator = media_candidate_score(20, 0, "repeat creator", job)
        self.assertGreater(top_relevant, later_result)
        self.assertGreater(top_relevant, repeated_creator)
        self.assertGreater(
            media_text_relevance_score("ancient roman aqueduct", "Roman aqueduct ruins in Italy"),
            media_text_relevance_score("ancient roman aqueduct", "modern office workers"),
        )

    def test_ai_media_requires_an_ai_anchor_and_blocks_unsafe_gestures(self):
        job = SimpleNamespace(MIN_MEDIA_RELEVANCE_SCORE=6)
        self.assertTrue(
            acceptable_media_metadata(
                "AI technology in healthcare",
                "surgeon operating robotic surgery system",
                job,
            )
        )
        self.assertFalse(
            acceptable_media_metadata(
                "AI transforming education",
                "woman teaching students in classroom",
                job,
            )
        )
        self.assertFalse(is_safe_media_metadata("person showing a dirty-finger gesture"))
        self.assertFalse(
            acceptable_media_metadata(
                "AI enhancing daily life",
                "person showing a dirty-finger gesture with prosthetic hand",
                job,
            )
        )

    def test_subject_aware_crop_tracks_focus_without_leaving_source_bounds(self):
        centred = crop_window(1920, 1080, 9 / 16, 0.5, 0.5)
        right_focused = crop_window(1920, 1080, 9 / 16, 0.85, 0.5)
        self.assertEqual(centred[:2], right_focused[:2])
        self.assertGreater(right_focused[2], centred[2])
        crop_w, crop_h, x, y = right_focused
        self.assertLessEqual(x + crop_w, 1920)
        self.assertLessEqual(y + crop_h, 1080)
        self.assertEqual((crop_w % 2, crop_h % 2, x % 2, y % 2), (0, 0, 0, 0))

    def test_visual_qa_rejects_blank_and_near_duplicate_frames(self):
        from PIL import Image, ImageDraw

        blank = inspect_image(Image.new("RGB", (320, 180), "black"))
        self.assertFalse(blank["passed"])
        detailed = Image.new("RGB", (320, 180), "white")
        ImageDraw.Draw(detailed).rectangle((180, 30, 300, 160), fill="navy")
        first = inspect_image(detailed)
        duplicate = inspect_image(detailed.copy(), [first["hash"]])
        self.assertTrue(first["passed"])
        self.assertFalse(duplicate["passed"])
        self.assertLessEqual(hash_distance(first["hash"], duplicate["hash"]), 4)

    def test_visual_qa_rejects_a_single_slide_that_consumes_most_of_video(self):
        failures = _timeline_failures(120.0, [float(value) for value in range(4, 69, 4)] + [120.0])
        self.assertEqual(len(failures), 1)
        self.assertIn("prolonged visual repetition", failures[0])

    def test_urdu_caption_overlay_contains_visible_shaped_pixels(self):
        from PIL import Image

        font_path = Path(__file__).resolve().parents[1] / "assets" / "Jameel Noori Nastaleeq.ttf"
        with tempfile.TemporaryDirectory() as temp_dir:
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                CONTENT_LANGUAGE="Urdu",
                FONT_PATH=str(font_path),
                CAPTIONS=["مصنوعی ذہانت ہماری زندگی بدل رہی ہے"],
                SLIDE_TIMINGS=[2.0],
                VIDEO_WIDTH=720,
                VIDEO_HEIGHT=1280,
                CAPTION_FONT_SIZE=52,
            )
            overlays = render_caption_overlays(job)
            self.assertEqual(len(overlays), 1)
            with Image.open(overlays[0]["path"]) as image:
                self.assertIsNotNone(image.getchannel("A").getbbox())
            self.assertEqual(overlays[0]["start"], 0.0)
            self.assertEqual(overlays[0]["end"], 2.0)

    def test_mixed_urdu_english_caption_uses_a_latin_capable_fallback(self):
        from PIL import ImageFont

        primary = ImageFont.truetype(
            str(Path(__file__).resolve().parents[1] / "assets" / "Jameel Noori Nastaleeq.ttf"),
            52,
            layout_engine=ImageFont.Layout.RAQM,
        )
        fallback = _load_mixed_script_fallback(ImageFont, SimpleNamespace(), 52)
        self.assertIs(_font_for_text("مصنوعی ذہانت", primary, fallback), primary)
        self.assertIs(_font_for_text("AI دنیا بدل رہی ہے", primary, fallback), fallback)

    def test_renderer_uses_timed_raster_overlays_for_urdu(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            font_path = os.path.join(temp_dir, "font.ttf")
            overlay_path = os.path.join(temp_dir, "caption_overlay_01.png")
            Path(overlay_path).write_bytes(b"png")
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                MUSIC_DIR=temp_dir,
                BG_MUSIC_VIBE="mystery",
                BG_MUSIC_TRACK_INDEX=1,
                COLOR_FILTER=None,
                SHOW_PROGRESS_BAR=False,
                SHOW_WATERMARK=False,
                OUTPUT_DIR=temp_dir,
                CONTENT_LANGUAGE="Urdu",
                FONT_PATH=font_path,
                FPS=25,
            )
            overlays = [{"path": overlay_path, "start": 0.0, "end": 4.0, "y": 500}]
            with (
                patch("history_reels.renderer.run_command") as run,
                patch("history_reels.renderer.render_caption_overlays", return_value=overlays),
                patch("history_reels.renderer.write_ass_subtitles") as ass_writer,
                patch("history_reels.renderer.setup_fontconfig") as fontconfig,
            ):
                run_ffmpeg(job, voice_dur=4.0)

            merge_call = run.call_args_list[-1]
            merge_command = merge_call.args[0]
            merge_filter = merge_command[merge_command.index("-filter_complex") + 1]
            self.assertIn("overlay=0:500:enable='between(t,0.000,4.000)'", merge_filter)
            self.assertNotIn("subtitles=", merge_filter)
            self.assertIn(overlay_path, merge_command)
            self.assertIsNone(merge_call.kwargs["env"])
            ass_writer.assert_not_called()
            fontconfig.assert_not_called()

    def test_language_font_preset_and_ass_caption_style_are_applied(self):
        self.assertEqual(get_font_preset("Noto Sans Devanagari")["family"], "Noto Sans Devanagari")
        with tempfile.TemporaryDirectory() as temp_dir:
            ass_path = os.path.join(temp_dir, "subtitles.ass")
            job = SimpleNamespace(
                SLIDE_TIMINGS=[2.0],
                CAPTIONS=["नमस्ते {test}\\path"],
                VIDEO_WIDTH=720,
                VIDEO_HEIGHT=1280,
                CAPTION_FONT_FAMILY="Noto Sans Devanagari",
                CAPTION_FONT_SIZE=58,
            )
            write_ass_subtitles(ass_path, job)
            ass = Path(ass_path).read_text(encoding="utf-8")
            self.assertIn("Style: Default,Noto Sans Devanagari,58", ass)
            self.assertIn("\\{test\\}", ass)

    def test_script_prompt_uses_the_job_creative_brief(self):
        response_data = {
            "title": "Smart Study Habits",
            "year": "Beginner Guide",
            "bg_music_vibe": "modern",
            "captions": ["Study smarter"],
            "narrations": ["Study smarter"],
            "queries": ["student studying"] * 8,
            "seo_title": "Study Better",
            "seo_description": "Useful study advice.",
            "seo_hashtags": "#StudyTips #Reels",
            "seo_short_caption": "Study better.",
        }
        response = unittest.mock.MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": __import__("json").dumps(response_data)}}]}
        settings = SimpleNamespace(
            GROQ_API_KEY="test-key",
            TARGET_DURATION=30,
            CONTENT_LANGUAGE="English",
            CONTENT_TONE="Educational",
        )
        with patch("history_reels.script_generator.requests.post", return_value=response) as post:
            result = fetch_ai_script("How to study effectively", provider="groq", settings=settings)

        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertEqual(result["title"], "Smart Study Habits")
        self.assertNotIn("Niche:", prompt)
        self.assertIn("Content language: English", prompt)
        self.assertIn("Tone: Educational", prompt)
        self.assertNotIn("Target platform:", prompt)
        self.assertNotIn("Visual style:", prompt)

    def test_raw_script_prompt_preserves_source_language_without_conflicting_instruction(self):
        response_data = {
            "title": "Raw Script", "year": "Guide", "bg_music_vibe": "modern",
            "captions": ["Texto original"], "narrations": ["Texto original"],
            "queries": ["person speaking"] * 8, "seo_title": "Raw", "seo_description": "Raw",
            "seo_hashtags": "#Reels", "seo_short_caption": "Raw",
        }
        response = unittest.mock.MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": __import__("json").dumps(response_data)}}]}
        settings = SimpleNamespace(
            GROQ_API_KEY="test-key", TARGET_DURATION=30, CONTENT_LANGUAGE="English",
            CONTENT_TONE="Clear",
        )
        with patch("history_reels.script_generator.requests.post", return_value=response) as post:
            fetch_ai_script("Texto original", provider="groq", is_raw_script=True, settings=settings)
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("Preserve captions and narrations in the source script's original language", prompt)
        self.assertNotIn("Write captions and narrations exclusively in English", prompt)

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
        model = ScriptConfig(
            bg_music_vibe="invalid_vibe",
            captions=["caption"],
            narrations=["narration"],
            queries=["topic close up"],
        )
        self.assertEqual(model.bg_music_vibe, "mystery")

    def test_pydantic_short_queries_are_padded(self):
        model = ScriptConfig(
            captions=["caption"],
            narrations=["narration"],
            queries=["q1", "q2", "q3", "q4", "q5", "q6", "q7"],
        )
        self.assertEqual(len(model.queries), 8)
        self.assertEqual(model.queries[-1], "q1 wide establishing shot")

    def test_script_validation_rejects_missing_or_misaligned_slides(self):
        with self.assertRaises(ValueError):
            ScriptConfig(captions=[], narrations=[], queries=["history"])
        with self.assertRaises(ValueError):
            ScriptConfig(captions=["one", "two"], narrations=["one"], queries=["history"])

    def test_input_check_rejects_empty_script_before_asset_downloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=os.path.join(temp_dir, "job"),
                OUTPUT_DIR=temp_dir,
                CAPTIONS=[],
                NARRATIONS=[],
                QUERIES=[],
            )
            with patch("history_reels.cli.ensure_assets") as ensure_assets:
                self.assertFalse(check_inputs(job))
            ensure_assets.assert_not_called()

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

    def test_job_preserves_selected_music_vibe_and_uses_selected_voice_name(self):
        original_vibe = config.BG_MUSIC_VIBE
        original_voice_id = config.VOICE_ID
        original_provider = config.VOICE_PROVIDER
        try:
            config.BG_MUSIC_VIBE = "epic"
            config.VOICE_PROVIDER = "edge-tts"
            config.VOICE_ID = "ur-PK-UzmaNeural"
            job = create_generation_job(config)
            job.apply_script({
                "title": "Titanic",
                "year": "1912",
                "bg_music_vibe": "sad",
                "captions": [],
                "narrations": [],
                "queries": ["ocean"] * 8,
            }, track_index=2)

            self.assertEqual(job.BG_MUSIC_VIBE, "epic")
            self.assertEqual(job.AI_SUGGESTED_MUSIC_VIBE, "sad")
            self.assertIn("Uzma Voice", job.OUTPUT_NAME)
            self.assertNotIn("Asad Voice", job.OUTPUT_NAME)

            job.VOICE_PROVIDER = "elevenlabs"
            self.assertEqual(job.voice_label(), "ElevenLabs Voice")
        finally:
            config.BG_MUSIC_VIBE = original_vibe
            config.VOICE_ID = original_voice_id
            config.VOICE_PROVIDER = original_provider

    def test_pipeline_uses_one_job_snapshot_for_every_stage(self):
        script_data = {
            "title": "Titanic",
            "year": "1912",
            "bg_music_vibe": "sad",
            "captions": ["Slide 1"],
            "narrations": ["Narration 1"],
            "queries": ["ocean"] * 8,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(config)
            job.TEMP_DIR = temp_dir
            job.TOPIC_TEMP_DIR = os.path.join(temp_dir, job.job_id)
            job.OUTPUT_DIR = temp_dir

            with (
                patch("history_reels.cli.fetch_ai_script", return_value=script_data) as fetch_script,
                patch("history_reels.cli.check_inputs", return_value=True) as check_inputs,
                patch("history_reels.cli.generate_voiceover", return_value=12.0) as generate_voiceover,
                patch("history_reels.cli.download_visuals") as download_visuals,
                patch("history_reels.cli.build_video_frames") as build_frames,
                patch("history_reels.cli.run_ffmpeg") as run_ffmpeg,
                patch("history_reels.cli.write_seo_package") as write_seo,
                patch("history_reels.cli.copy_deliverables") as copy_deliverables,
                patch("history_reels.cli.verify_deliverable", return_value={"passed": True}) as verify_deliverable,
                patch("history_reels.cli.cleanup") as cleanup,
            ):
                success = generate_video_for_topic("Titanic", provider="auto", job=job)

            self.assertTrue(success)
            fetch_script.assert_called_once_with("Titanic", provider="auto", is_raw_script=False, settings=job)
            check_inputs.assert_called_once_with(job)
            generate_voiceover.assert_called_once_with(job)
            download_visuals.assert_called_once_with(job, 12.0)
            build_frames.assert_called_once_with(job, 12.0)
            verify_deliverable.assert_called_once_with(job)
            run_ffmpeg.assert_called_once_with(job, 12.0)
            write_seo.assert_called_once_with(job)
            copy_deliverables.assert_called_once_with(job)
            cleanup.assert_called_once_with(job)

    def test_pipeline_records_input_failure_on_the_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(config)
            job.TEMP_DIR = temp_dir
            job.TOPIC_TEMP_DIR = os.path.join(temp_dir, job.job_id)
            job.OUTPUT_DIR = temp_dir

            with (
                patch("history_reels.cli.check_inputs", return_value=False) as check_inputs,
                patch("history_reels.cli.generate_voiceover") as generate_voiceover,
            ):
                success = generate_video_for_topic(None, job=job)

            self.assertFalse(success)
            self.assertIn("Input validation failed", job.last_error)
            check_inputs.assert_called_once_with(job)
            generate_voiceover.assert_not_called()

    def test_job_store_persists_lifecycle_and_cancellation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(config)
            job.OUTPUT_DIR = temp_dir
            job.TOPIC_TEMP_DIR = os.path.join(temp_dir, job.job_id)
            store = JobStore(temp_dir)

            store.create_job(job, {"label": "Titanic", "provider": "auto"})
            store.mark_running(job.job_id)
            store.update_progress(job.job_id, "media", 50, "Downloading source media.")
            self.assertTrue(store.request_cancellation(job.job_id))
            self.assertTrue(store.cancellation_requested(job.job_id))
            store.mark_cancelled(job)

            record = store.list_jobs(limit=1)[0]
            self.assertEqual(record["job_id"], job.job_id)
            self.assertEqual(record["status"], "cancelled")
            self.assertTrue(record["cancel_requested"])
            self.assertEqual(record["current_stage"], "cancelled")
            self.assertEqual(record["progress"], 50)
            self.assertTrue(any(event["stage"] == "media" for event in store.list_events(job.job_id)))

    def test_job_history_lists_completed_deliverable_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir))
            job.OUTPUT_DIR = temp_dir
            job.OUTPUT_NAME = "Completed Reel"
            store = JobStore(temp_dir)
            store.create_job(job, {"label": "Completed Reel", "provider": "auto"})
            self.assertTrue(store.claim_job(job.job_id))
            self.assertTrue(store.mark_succeeded(job))
            record = store.list_jobs(limit=1)[0]
            self.assertEqual(record["output_video_path"], os.path.join(temp_dir, "Completed Reel.mp4"))
            self.assertEqual(record["output_seo_path"], os.path.join(temp_dir, "Completed Reel.txt"))

    def test_pipeline_stops_at_a_cancellation_checkpoint(self):
        script_data = {
            "title": "Titanic",
            "year": "1912",
            "bg_music_vibe": "sad",
            "captions": ["Slide 1"],
            "narrations": ["Narration 1"],
            "queries": ["ocean"] * 8,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(config)
            job.TEMP_DIR = temp_dir
            job.TOPIC_TEMP_DIR = os.path.join(temp_dir, job.job_id)
            job.OUTPUT_DIR = temp_dir

            def cancel_after_voice(active_job):
                active_job.history_store.request_cancellation(active_job.job_id)
                return 12.0

            with (
                patch("history_reels.cli.fetch_ai_script", return_value=script_data),
                patch("history_reels.cli.check_inputs", return_value=True),
                patch("history_reels.cli.generate_voiceover", side_effect=cancel_after_voice),
                patch("history_reels.cli.download_visuals") as download_visuals,
                patch("history_reels.cli.cleanup") as cleanup,
            ):
                success = generate_video_for_topic("Titanic", provider="auto", job=job)

            self.assertFalse(success)
            self.assertEqual(job.status, "cancelled")
            self.assertIn("cancelled", job.last_error.lower())
            download_visuals.assert_not_called()
            cleanup.assert_called_once_with(job)
            self.assertEqual(JobStore(temp_dir).list_jobs(limit=1)[0]["status"], "cancelled")

    def test_background_manager_persists_request_and_can_retry(self):
        calls = []

        def successful_runner(topic, provider, manual_script_data, is_raw_script, job):
            calls.append((topic, provider, manual_script_data, is_raw_script, job.job_id, job.CLIP_DURATION_TARGET))
            job.OUTPUT_NAME = "Queued Reel"
            job.history_store.mark_running(job.job_id)
            job.history_store.mark_succeeded(job)
            job.status = "succeeded"
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(
                TEMP_DIR=temp_dir,
                OUTPUT_DIR=temp_dir,
                CLIP_DURATION_TARGET=3.0,
                OPENAI_API_KEY="must-not-be-persisted",
            )
            manager = JobManager(runner=successful_runner)
            first = create_generation_job(runtime)
            first_id = manager.submit(first, topic="Titanic", provider="auto")
            manager._futures[first_id].result(timeout=5)

            saved = JobStore(temp_dir).get_retry_request(first_id)
            self.assertEqual(saved["topic"], "Titanic")
            self.assertEqual(saved["provider"], "auto")
            stored_record = JobStore(temp_dir).get_job(first_id)
            self.assertEqual(stored_record["settings_json"]["CLIP_DURATION_TARGET"], 3.0)
            self.assertNotIn("OPENAI_API_KEY", stored_record["settings_json"])

            runtime.CLIP_DURATION_TARGET = 7.0
            retry_id = manager.retry(temp_dir, runtime, first_id)
            self.assertIsNotNone(retry_id)
            manager._futures[retry_id].result(timeout=5)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1][-1], 3.0)
            records = JobStore(temp_dir).list_jobs(limit=2)
            retry_record = next(record for record in records if record["job_id"] == retry_id)
            self.assertEqual(retry_record["retry_of"], first_id)
            self.assertEqual(retry_record["status"], "succeeded")

    def test_background_manager_passes_keyword_only_runner_arguments(self):
        received = {}

        def keyword_only_runner(*, topic, provider, manual_script_data, is_raw_script, job):
            received.update({
                "topic": topic,
                "provider": provider,
                "manual_script_data": manual_script_data,
                "is_raw_script": is_raw_script,
            })
            job.history_store.mark_running(job.job_id)
            job.OUTPUT_NAME = "Keyword Safe Reel"
            job.status = "succeeded"
            job.history_store.mark_succeeded(job)
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir)
            manager = JobManager(runner=keyword_only_runner)
            job_id = manager.submit(create_generation_job(runtime), topic="Healthy breakfast ideas", provider="auto")
            self.assertTrue(manager._futures[job_id].result(timeout=5))
            self.assertEqual(received["topic"], "Healthy breakfast ideas")
            self.assertEqual(JobStore(temp_dir).get_job(job_id)["status"], "succeeded")

    def test_default_background_runner_dispatches_topic_without_positional_error(self):
        captured = {}

        def pipeline_stub(*, topic, provider, manual_script_data, is_raw_script, job):
            captured["topic"] = topic
            captured["provider"] = provider
            job.history_store.mark_running(job.job_id)
            job.OUTPUT_NAME = "Dispatch Safe Reel"
            job.status = "succeeded"
            job.history_store.mark_succeeded(job)
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir)
            manager = JobManager()
            with patch("history_reels.cli.generate_video_for_topic", side_effect=pipeline_stub):
                job_id = manager.submit(create_generation_job(runtime), topic="Future of AI", provider="auto")
                self.assertTrue(manager._futures[job_id].result(timeout=5))
            self.assertEqual(captured, {"topic": "Future of AI", "provider": "auto"})
            self.assertEqual(JobStore(temp_dir).get_job(job_id)["status"], "succeeded")

    def test_thread_manager_marks_orphaned_queued_jobs_retryable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir)
            job = create_generation_job(runtime)
            store = JobStore(temp_dir)
            store.create_job(job, {"label": "Interrupted", "provider": "auto"})
            manager = JobManager(mode="thread")
            self.assertEqual(manager.reconcile_orphaned_thread_jobs(temp_dir), 1)
            record = store.get_job(job.job_id)
            self.assertEqual(record["status"], "failed")
            self.assertIn("interrupted", record["error_message"].lower())

    def test_background_manager_retries_transient_failure_once(self):
        attempts = []

        def transient_runner(topic, provider, manual_script_data, is_raw_script, job):
            attempts.append(job.job_id)
            job.history_store.mark_running(job.job_id)
            if len(attempts) == 1:
                job.last_error = "Network timeout while fetching media"
                job.status = "failed"
                job.history_store.mark_failed(job, job.last_error)
                return False
            job.OUTPUT_NAME = "Recovered Reel"
            job.status = "succeeded"
            job.history_store.mark_succeeded(job)
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir, MAX_JOB_ATTEMPTS=2)
            manager = JobManager(runner=transient_runner)
            first_id = manager.submit(create_generation_job(runtime), topic="Titanic", provider="auto")
            manager._futures[first_id].result(timeout=5)

            retry_ids = [job_id for job_id in manager._futures if job_id != first_id]
            self.assertEqual(len(retry_ids), 1)
            manager._futures[retry_ids[0]].result(timeout=5)
            self.assertEqual(len(attempts), 2)

            records = JobStore(temp_dir).list_jobs(limit=2)
            retry_record = next(record for record in records if record["job_id"] == retry_ids[0])
            self.assertEqual(retry_record["attempt"], 2)
            self.assertEqual(retry_record["max_attempts"], 2)
            self.assertEqual(retry_record["retry_of"], first_id)

    def test_error_categories_and_history_retention_preserve_deliverables(self):
        self.assertEqual(categorize_error("Network timeout"), "network")
        self.assertEqual(categorize_error("FFmpeg render failed"), "rendering")
        self.assertEqual(categorize_error("Invalid manual script validation"), "validation")

        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir))
            job.OUTPUT_DIR = temp_dir
            store = JobStore(temp_dir)
            store.create_job(job, {"label": "Titanic", "provider": "auto"})
            store.mark_failed(job, "Network timeout while downloading media")
            with store._connection() as connection:
                connection.execute("UPDATE jobs SET created_at = '2000-01-01T00:00:00+00:00' WHERE job_id = ?", (job.job_id,))
            deliverable = os.path.join(temp_dir, "keep-me.mp4")
            with open(deliverable, "wb") as file:
                file.write(b"video")

            self.assertEqual(store.cleanup_history(older_than_days=1), 1)
            self.assertEqual(store.list_jobs(), [])
            self.assertTrue(os.path.exists(deliverable))

    def test_process_worker_mode_queues_and_recovers_without_running_render(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir)
            with patch("history_reels.job_manager.subprocess.Popen") as popen:
                popen.return_value.poll.return_value = None
                manager = JobManager(mode="process")
                job_id = manager.submit(create_generation_job(runtime), topic="Titanic", provider="auto")
                record = JobStore(temp_dir).get_job(job_id)
                self.assertEqual(record["status"], "queued")
                self.assertEqual(popen.call_count, 1)
                self.assertEqual(manager.recover_queued(temp_dir), 0)
                popen.return_value.poll.return_value = 1
                self.assertEqual(manager.recover_queued(temp_dir), 1)
                self.assertEqual(popen.call_count, 2)

    def test_process_worker_restores_settings_and_auto_retries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(
                TEMP_DIR=temp_dir,
                OUTPUT_DIR=temp_dir,
                CLIP_DURATION_TARGET=3.0,
                MAX_JOB_ATTEMPTS=2,
            )
            store = JobStore(temp_dir)
            job = create_generation_job(runtime)
            request = {
                "label": "Titanic",
                "topic": "Titanic",
                "provider": "auto",
                "attempt": 1,
                "max_attempts": 2,
            }
            store.create_job(job, request)
            captured = []

            def transient_failure(topic, provider, manual_script_data, is_raw_script, job):
                captured.append(job.CLIP_DURATION_TARGET)
                job.status = "failed"
                job.last_error = "Network timeout"
                job.history_store.mark_failed(job, job.last_error)
                return False

            with (
                patch("history_reels.worker.generate_video_for_topic", side_effect=transient_failure),
                patch("history_reels.job_manager.subprocess.Popen"),
            ):
                self.assertFalse(run_job(temp_dir, job.job_id))

            self.assertEqual(captured, [3.0])
            retries = [record for record in store.list_jobs(limit=5) if record["job_id"] != job.job_id]
            self.assertEqual(len(retries), 1)
            self.assertEqual(retries[0]["attempt"], 2)
            self.assertEqual(retries[0]["retry_of"], job.job_id)

    def test_cli_csv_manual_columns_become_caption_lists(self):
        import pandas as pd

        frame = pd.DataFrame([{
            "title": "Titanic",
            "year": "1912",
            "caption_text_1": "Caption one",
            "caption_text_2": float("nan"),
            "narration_text_1": "Narration one",
            "queries": "ocean, ship",
        }])
        with (
            patch("history_reels.cli.config.check_system_dependencies", return_value=True),
            patch("history_reels.cli.os.path.exists", return_value=True),
            patch("history_reels.cli.pd", create=True),
            patch("pandas.read_csv", return_value=frame),
            patch("history_reels.cli.generate_video_for_topic") as generate,
            patch("sys.argv", ["history-reels", "--csv", "batch.csv"]),
        ):
            cli_main()
        manual_data = generate.call_args.kwargs["manual_script_data"]
        self.assertEqual(manual_data["captions"], ["Caption one"])
        self.assertEqual(manual_data["narrations"], ["Narration one"])

    def test_snapshot_safe_settings_strips_private_and_public_keys(self):
        job = SimpleNamespace(values={
            "TOPIC_TITLE": "Printing press",
            "PEXELS_API_KEY": "pexels-secret",
            "STORYBLOCKS_PRIVATE_KEY": "story-private",
            "STORYBLOCKS_PUBLIC_KEY": "story-public",
            "TARGET_DURATION": 30,
        })
        snapshot = snapshot_safe_settings(job)
        self.assertEqual(snapshot.get("TOPIC_TITLE"), "Printing press")
        self.assertEqual(snapshot.get("TARGET_DURATION"), 30)
        self.assertNotIn("PEXELS_API_KEY", snapshot)
        self.assertNotIn("STORYBLOCKS_PRIVATE_KEY", snapshot)
        self.assertNotIn("STORYBLOCKS_PUBLIC_KEY", snapshot)

    def test_stock_media_safe_error_redacts_query_keys(self):
        message = _safe_error_message(
            Exception("https://pixabay.com/api/videos/?key=super-secret&q=ocean HTTP 403")
        )
        self.assertNotIn("super-secret", message)
        self.assertIn("key=***", message)

    def test_renderer_uses_job_watermark_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo_path = os.path.join(temp_dir, "brand_logo.png")
            Path(logo_path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            font_path = os.path.join(temp_dir, "font.ttf")
            Path(font_path).write_bytes(b"0" * 64)
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=temp_dir,
                MUSIC_DIR=temp_dir,
                BG_MUSIC_VIBE="mystery",
                BG_MUSIC_TRACK_INDEX=1,
                COLOR_FILTER=None,
                SHOW_PROGRESS_BAR=False,
                SHOW_WATERMARK=True,
                WATERMARK_PATH=logo_path,
                WATERMARK_SIZE=80,
                WATERMARK_OPACITY=0.4,
                WATERMARK_POSITION="20:20",
                OUTPUT_DIR=temp_dir,
                FONT_PATH=font_path,
            )
            with (
                patch("history_reels.renderer.run_command") as run,
                patch("history_reels.renderer.write_ass_subtitles"),
                patch("history_reels.renderer.setup_fontconfig", return_value=os.path.join(temp_dir, "fonts.conf")),
            ):
                run_ffmpeg(job, voice_dur=8.0)
            merge_command = run.call_args_list[-1].args[0]
            self.assertIn(logo_path, merge_command)

    def test_bumper_stitch_normalizes_to_48k_and_reencodes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "workspace")
            output_dir = os.path.join(temp_dir, "output")
            os.makedirs(source_dir)
            os.makedirs(output_dir)
            Path(source_dir, "output.mp4").write_bytes(b"video")
            Path(source_dir, "output.txt").write_text("SEO package", encoding="utf-8")
            intro = os.path.join(temp_dir, "intro.mp4")
            Path(intro).write_bytes(b"intro")
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=source_dir,
                OUTPUT_DIR=output_dir,
                video_path=os.path.join(output_dir, "reel.mp4"),
                seo_path=os.path.join(output_dir, "reel.txt"),
                INTRO_BUMPER=intro,
                OUTRO_BUMPER=None,
                VIDEO_WIDTH=720,
                VIDEO_HEIGHT=1280,
                FPS=25,
            )

            def fake_run(cmd, *args, **kwargs):
                if cmd and cmd[0] == "ffprobe":
                    return SimpleNamespace(stdout="", stderr="", returncode=0, args=cmd)
                if cmd and cmd[0] == "ffmpeg":
                    output = cmd[-1]
                    if isinstance(output, str) and output.endswith(".mp4"):
                        Path(output).write_bytes(b"normalized")
                    return SimpleNamespace(returncode=0, stdout="", stderr="", args=cmd)
                return SimpleNamespace(returncode=0, stdout="", stderr="", args=cmd)

            with patch("history_reels.ffmpeg_runner.run_command", side_effect=fake_run):
                self.assertTrue(copy_deliverables(job))

            self.assertTrue(Path(job.video_path).is_file())
            # Final stitched file should have been produced via re-encode (not demuxer -c copy).
            with patch("history_reels.ffmpeg_runner.run_command", side_effect=fake_run) as run:
                copy_deliverables(job)
            ffmpeg_calls = [call.args[0] for call in run.call_args_list if call.args and call.args[0][0] == "ffmpeg"]
            self.assertTrue(ffmpeg_calls)
            concat_cmd = ffmpeg_calls[-1]
            self.assertIn("-filter_complex", concat_cmd)
            self.assertIn("concat=", concat_cmd[concat_cmd.index("-filter_complex") + 1])
            # Stream-copy concat is no longer used; audio is forced to 48 kHz.
            self.assertFalse(
                any(cmd[i:i + 2] == ["-c", "copy"] for cmd in ffmpeg_calls for i in range(len(cmd) - 1))
            )
            self.assertTrue(any(str(part) == "48000" for cmd in ffmpeg_calls for part in cmd))

    def test_dashboard_metrics_use_completed_and_storage_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir, "sample.mp4")
            sample.write_bytes(b"0" * 2048)
            job = create_generation_job(SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir))
            job.OUTPUT_DIR = temp_dir
            job.OUTPUT_NAME = "sample"
            store = JobStore(temp_dir)
            store.create_job(job, {"label": "Metrics", "provider": "auto"})
            store.claim_job(job.job_id)
            store.mark_succeeded(job)
            metrics = get_dashboard_metrics(temp_dir)
            self.assertIn("total_completed_videos", metrics)
            self.assertIn("total_storage_bytes", metrics)
            self.assertEqual(metrics["total_completed_videos"], 1)
            self.assertGreaterEqual(metrics["total_storage_bytes"], 2048)

    def test_claim_job_is_atomic_and_blocks_double_workers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir))
            store = JobStore(temp_dir)
            store.create_job(job, {"label": "Atomic", "provider": "auto"})
            self.assertTrue(store.claim_job(job.job_id))
            self.assertFalse(store.claim_job(job.job_id))
            self.assertEqual(store.get_job(job.job_id)["status"], "running")

    def test_terminal_status_cannot_be_overwritten_by_late_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job = create_generation_job(SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir))
            job.OUTPUT_NAME = "late"
            store = JobStore(temp_dir)
            store.create_job(job, {"label": "Late", "provider": "auto"})
            store.claim_job(job.job_id)
            store.request_cancellation(job.job_id)
            store.mark_cancelled(job, "User cancelled")
            self.assertFalse(store.mark_succeeded(job))
            self.assertEqual(store.get_job(job.job_id)["status"], "cancelled")

    def test_reconcile_marks_stuck_running_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SimpleNamespace(TEMP_DIR=temp_dir, OUTPUT_DIR=temp_dir)
            job = create_generation_job(runtime)
            store = JobStore(temp_dir)
            store.create_job(job, {"label": "Stuck", "provider": "auto"})
            store.claim_job(job.job_id)
            manager = JobManager(mode="thread")
            count = manager.reconcile_orphaned_thread_jobs(temp_dir)
            self.assertGreaterEqual(count, 1)
            self.assertEqual(store.get_job(job.job_id)["status"], "failed")

    def test_media_quality_profile_floor_and_image_accept(self):
        balanced = SimpleNamespace(MEDIA_QUALITY_PROFILE="balanced", MIN_MEDIA_DIMENSION=0)
        high = SimpleNamespace(MEDIA_QUALITY_PROFILE="high", MIN_MEDIA_DIMENSION=0)
        self.assertEqual(effective_min_media_dimension(balanced), 480)
        self.assertEqual(effective_min_media_dimension(high), 720)
        self.assertGreaterEqual(media_quality_score(1280, 720, high, 10), 0)
        self.assertLess(media_quality_score(500, 500, high, 10), 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            tiny = Path(temp_dir, "tiny.jpg")
            tiny.write_bytes(b"not-an-image")
            job = SimpleNamespace(MEDIA_QUALITY_PROFILE="balanced", MIN_MEDIA_DIMENSION=480)
            with patch("history_reels.ffmpeg_runner.get_media_dimensions", return_value=(120, 90)):
                self.assertFalse(accept_downloaded_image(str(tiny), job))
            self.assertFalse(tiny.exists())

    def test_run_command_raises_render_error_on_nonzero(self):
        with patch("history_reels.ffmpeg_runner.subprocess.Popen") as popen:
            process = popen.return_value
            process.communicate.return_value = ("", "filter graph failed")
            process.returncode = 1
            process.poll.return_value = 1
            with self.assertRaises(RenderError) as raised:
                run_command(["ffmpeg", "-y", "broken"], timeout=5, label="test encode")
            self.assertIn("filter graph failed", str(raised.exception))
            self.assertEqual(raised.exception.returncode, 1)

    def test_kill_job_processes_is_safe_when_empty(self):
        self.assertEqual(kill_job_processes("missing-job"), 0)

    def test_cleanup_keeps_workspace_when_flag_set(self):
        from history_reels.cli import cleanup

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir, "workspace")
            workspace.mkdir()
            (workspace / "clip.mp4").write_bytes(b"x")
            job = SimpleNamespace(
                TOPIC_TEMP_DIR=str(workspace),
                TEMP_DIR=temp_dir,
                KEEP_WORKSPACE=True,
            )
            cleanup(job)
            self.assertTrue(workspace.exists())

if __name__ == "__main__":
    unittest.main()
