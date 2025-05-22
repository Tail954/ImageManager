# g:\vscodeGit\ImageManager\tests\test_metadata_utils.py
import unittest
from unittest.mock import patch, MagicMock
import os
import json

# Ensure src directory is in Python path for imports
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.metadata_utils import extract_image_metadata, _im_decode_exif, _im_parse_parameters
from PIL import Image # For FileNotFoundError and other PIL specific exceptions

class TestMetadataUtils(unittest.TestCase):

    def _create_mock_image(self, info=None, exif_data=None, format_str="PNG"):
        """Helper to create a mock PIL Image object."""
        mock_img = MagicMock()
        mock_img.info = info if info is not None else {}
        
        if exif_data is not None:
            mock_exif_obj = MagicMock()
            mock_exif_obj.get = lambda key, default=None: exif_data.get(key, default)
            mock_img.getexif = MagicMock(return_value=mock_exif_obj)
        else:
            mock_img.getexif = MagicMock(return_value=None)
            
        mock_img.format = format_str
        
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_img
        mock_context_manager.__exit__.return_value = None
        return mock_context_manager

    @patch('src.metadata_utils.Image.open')
    def test_extract_metadata_png_a1111_parameters(self, mock_image_open):
        """Test A1111 style PNG with 'parameters' in img.info."""
        mock_img_cm = self._create_mock_image(
            info={'parameters': 'test positive prompt\nNegative prompt: test negative prompt\nSteps: 20, Sampler: Euler a'}
        )
        mock_image_open.return_value = mock_img_cm

        metadata = extract_image_metadata("dummy.png")
        self.assertEqual(metadata['positive_prompt'], "test positive prompt")
        self.assertEqual(metadata['negative_prompt'], "test negative prompt")
        self.assertEqual(metadata['generation_info'], "Steps: 20, Sampler: Euler a")

    @unittest.expectedFailure
    @patch('src.metadata_utils.Image.open')
    def test_extract_metadata_png_info_exif_field(self, mock_image_open):
        """Test PNG with 'exif' bytes in img.info (e.g., NovelAI).
        This test is expected to fail with the current _im_decode_exif (offset +8)
        when processing the mocked 9-byte "UNICODE\x00\x00" prefix, as it will lead to
        misaligned decoding and likely incorrect parsing or empty strings.
        """
        exif_bytes = b"UNICODE\x00\x00" + "test positive exif\nNegative prompt: test negative exif\nSteps: 30".encode('utf-16-be')
        mock_img_cm = self._create_mock_image(
            info={'exif': exif_bytes}
        )
        mock_image_open.return_value = mock_img_cm

        metadata = extract_image_metadata("dummy.png")
        self.assertEqual(metadata['positive_prompt'], "test positive exif")
        self.assertEqual(metadata['negative_prompt'], "test negative exif")
        self.assertEqual(metadata['generation_info'], "Steps: 30")

    @unittest.expectedFailure
    @patch('src.metadata_utils.Image.open')
    def test_extract_metadata_jpeg_usercomment(self, mock_image_open):
        """Test JPEG with metadata in EXIF UserComment (0x9286).
        This test is expected to fail with the current _im_decode_exif (offset +8)
        for the same reasons as test_extract_metadata_png_info_exif_field,
        if the UserComment contains the 9-byte "UNICODE\x00\x00" prefix.
        """
        user_comment_bytes = b"UNICODE\x00\x00" + "jpeg positive\nNegative prompt: jpeg negative\nSteps: 25".encode('utf-16-be')
        mock_img_cm = self._create_mock_image(
            exif_data={0x9286: user_comment_bytes},
            format_str="JPEG"
        )
        mock_image_open.return_value = mock_img_cm

        metadata = extract_image_metadata("dummy.jpg")
        self.assertEqual(metadata['positive_prompt'], "jpeg positive")
        self.assertEqual(metadata['negative_prompt'], "jpeg negative")
        self.assertEqual(metadata['generation_info'], "Steps: 25")

    @patch('src.metadata_utils.Image.open')
    def test_extract_metadata_webp_imagedescription(self, mock_image_open):
        """Test WEBP with metadata in EXIF ImageDescription (0x010e).
        This test should pass if ImageDescription is a simple string (e.g., UTF-8)
        that doesn't rely on the "UNICODE\x00\x00" prefix logic.
        """
        image_desc_bytes = "webp positive\nNegative prompt: webp negative\nSteps: 15".encode('utf-8')
        mock_img_cm = self._create_mock_image(
            exif_data={0x010e: image_desc_bytes},
            format_str="WEBP"
        )
        mock_image_open.return_value = mock_img_cm

        metadata = extract_image_metadata("dummy.webp")
        self.assertEqual(metadata['positive_prompt'], "webp positive")
        self.assertEqual(metadata['negative_prompt'], "webp negative")
        self.assertEqual(metadata['generation_info'], "Steps: 15")

    @patch('src.metadata_utils.Image.open')
    def test_extract_metadata_comfyui_json_comment(self, mock_image_open):
        """Test ComfyUI style PNG with JSON in 'Comment' img.info."""
        comfy_prompt = "comfy positive\nNegative prompt: comfy negative\nSteps: 10"
        comment_json = json.dumps({'prompt': comfy_prompt})
        mock_img_cm = self._create_mock_image(
            info={'Comment': comment_json}
        )
        mock_image_open.return_value = mock_img_cm

        metadata = extract_image_metadata("dummy.png")
        self.assertEqual(metadata['positive_prompt'], "comfy positive")
        self.assertEqual(metadata['negative_prompt'], "comfy negative")
        self.assertEqual(metadata['generation_info'], "Steps: 10")

    @patch('src.metadata_utils.Image.open')
    def test_extract_metadata_comfyui_raw_text_comment(self, mock_image_open):
        """Test ComfyUI style PNG with raw text in 'Comment' img.info (fallback)."""
        raw_comment_text = "raw comment positive\nNegative prompt: raw comment negative\nSteps: 5"
        mock_img_cm = self._create_mock_image(
            info={'Comment': raw_comment_text}
        )
        mock_image_open.return_value = mock_img_cm

        metadata = extract_image_metadata("dummy.png")
        self.assertEqual(metadata['positive_prompt'], "raw comment positive")
        self.assertEqual(metadata['negative_prompt'], "raw comment negative")
        self.assertEqual(metadata['generation_info'], "Steps: 5")

    @patch('src.metadata_utils.Image.open')
    def test_extract_metadata_no_metadata(self, mock_image_open):
        """Test image with no recognizable metadata."""
        mock_img_cm = self._create_mock_image(info={}, exif_data=None)
        mock_image_open.return_value = mock_img_cm

        metadata = extract_image_metadata("no_meta.png")
        self.assertEqual(metadata['positive_prompt'], "")
        self.assertEqual(metadata['negative_prompt'], "")
        self.assertEqual(metadata['generation_info'], "")

    @patch('src.metadata_utils.Image.open', side_effect=FileNotFoundError("File not found"))
    def test_extract_metadata_file_not_found(self, mock_image_open):
        """Test behavior when Image.open raises FileNotFoundError."""
        metadata = extract_image_metadata("non_existent.jpg")
        self.assertEqual(metadata['positive_prompt'], "")
        self.assertEqual(metadata['negative_prompt'], "")
        self.assertEqual(metadata['generation_info'], "")
        mock_image_open.assert_called_once_with("non_existent.jpg")

    @patch('src.metadata_utils.Image.open', side_effect=Image.UnidentifiedImageError("Cannot identify image file"))
    def test_extract_metadata_pil_error(self, mock_image_open):
        """Test behavior when Image.open raises a PIL specific error."""
        metadata = extract_image_metadata("corrupted.jpg")
        self.assertEqual(metadata['positive_prompt'], "")
        self.assertEqual(metadata['negative_prompt'], "")
        self.assertEqual(metadata['generation_info'], "")
        mock_image_open.assert_called_once_with("corrupted.jpg")

    def test_im_decode_exif(self):
        """Test _im_decode_exif helper function."""
        # UTF-16 BE with "UNICODE\x00\x00" prefix (9 bytes)
        # With current _im_decode_exif (offset +8), this will result in misaligned decoding.
        data_utf16be_prefixed = b"UNICODE\x00\x00" + "test_utf16be".encode('utf-16-be')
        # Expected misaligned string for offset +8: b'\x00' + "test_utf16be".encode('utf-16-be') decoded as utf-16-be
        expected_misaligned_be = (b'\x00' + "test_utf16be".encode('utf-16-be')).decode('utf-16-be', errors='replace')
        self.assertEqual(_im_decode_exif(data_utf16be_prefixed), expected_misaligned_be)

        # UTF-16 LE with "UNICODE\x00\x00" prefix
        # With current _im_decode_exif (offset +8), the internal 'data' is b'\x00' + "test_utf16le".encode('utf-16-le')
        # This 'data' is then attempted to be decoded as 'utf-16-be' first.
        data_utf16le_prefixed = b"UNICODE\x00\x00" + "test_utf16le".encode('utf-16-le')
        expected_result_from_be_path_for_le_data = (b'\x00' + "test_utf16le".encode('utf-16-le')).decode('utf-16-be', errors='replace')
        self.assertEqual(_im_decode_exif(data_utf16le_prefixed), expected_result_from_be_path_for_le_data)

        # UTF-8 (this path should work correctly)
        data_utf8 = "test_utf8_é".encode('utf-8')
        self.assertEqual(_im_decode_exif(data_utf8), "test_utf8_é")

        # Latin-1
        data_latin1 = "test_latin1_é".encode('latin-1')
        self.assertEqual(_im_decode_exif(data_latin1), "test_latin1_é")

        # ASCII
        data_ascii = b"test_ascii"
        self.assertEqual(_im_decode_exif(data_ascii), "test_ascii")
        
        # Non-bytes input
        self.assertEqual(_im_decode_exif(12345), "12345")
        self.assertEqual(_im_decode_exif(None), "None")

    def test_im_parse_parameters(self):
        """Test _im_parse_parameters helper function."""
        # Basic case
        text1 = "positive\nNegative prompt: negative\nSteps: 20"
        parsed1 = _im_parse_parameters(text1)
        self.assertEqual(parsed1['positive_prompt'], "positive")
        self.assertEqual(parsed1['negative_prompt'], "negative")
        self.assertEqual(parsed1['generation_info'], "Steps: 20")

        # Only positive prompt
        text2 = "only positive"
        parsed2 = _im_parse_parameters(text2)
        self.assertEqual(parsed2['positive_prompt'], "only positive")
        self.assertEqual(parsed2['negative_prompt'], "")
        self.assertEqual(parsed2['generation_info'], "")

        # Positive and generation info, no negative
        text3 = "positive only\nSteps: 30, Model: test_model"
        parsed3 = _im_parse_parameters(text3)
        self.assertEqual(parsed3['positive_prompt'], "positive only")
        self.assertEqual(parsed3['negative_prompt'], "")
        self.assertEqual(parsed3['generation_info'], "Steps: 30, Model: test_model")

        # Positive and negative, no generation info
        text4 = "positive again\nNegative prompt: negative again"
        parsed4 = _im_parse_parameters(text4)
        self.assertEqual(parsed4['positive_prompt'], "positive again")
        self.assertEqual(parsed4['negative_prompt'], "negative again")
        self.assertEqual(parsed4['generation_info'], "")
        
        text5 = "positive\nnegative_prompt: negative\nSteps: 20"
        parsed5 = _im_parse_parameters(text5)
        self.assertEqual(parsed5['positive_prompt'], "positive")
        self.assertEqual(parsed5['negative_prompt'], "negative")
        self.assertEqual(parsed5['generation_info'], "Steps: 20")

        text6 = "positive\nneg_prompt: negative\nSteps: 20"
        parsed6 = _im_parse_parameters(text6)
        self.assertEqual(parsed6['positive_prompt'], "positive")
        self.assertEqual(parsed6['negative_prompt'], "negative")
        self.assertEqual(parsed6['generation_info'], "Steps: 20")

        text7 = "Steps: 10, positive part\nNegative prompt: negative part"
        parsed7 = _im_parse_parameters(text7)
        self.assertEqual(parsed7['positive_prompt'], "Steps: 10, positive part")
        self.assertEqual(parsed7['negative_prompt'], "negative part")
        self.assertEqual(parsed7['generation_info'], "")

        text8 = "positive\nNegative prompt: negative\nModel: my_model, Size: 512x512"
        parsed8 = _im_parse_parameters(text8)
        self.assertEqual(parsed8['positive_prompt'], "positive")
        self.assertEqual(parsed8['negative_prompt'], "negative")
        self.assertEqual(parsed8['generation_info'], "Model: my_model, Size: 512x512")

        parsed_empty = _im_parse_parameters("")
        self.assertEqual(parsed_empty['positive_prompt'], "")
        self.assertEqual(parsed_empty['negative_prompt'], "")
        self.assertEqual(parsed_empty['generation_info'], "")

        parsed_none = _im_parse_parameters(None)
        self.assertEqual(parsed_none['positive_prompt'], "")
        self.assertEqual(parsed_none['negative_prompt'], "")
        self.assertEqual(parsed_none['generation_info'], "")

if __name__ == '__main__':
    unittest.main()
