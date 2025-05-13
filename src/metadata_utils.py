# src/metadata_utils.py
import logging
import json
from PIL import Image

logger = logging.getLogger(__name__)

def _im_decode_exif(exif_data):
    """Helper function adapted from ImageMover's decode_exif."""
    if isinstance(exif_data, bytes):
        try:
            unicode_start = exif_data.find(b'UNICODE\x00\x00')
            if unicode_start != -1:
                data = exif_data[unicode_start + 8:]
                try:
                    return data.decode('utf-16-be', errors='replace')
                except UnicodeDecodeError:
                    return data.decode('utf-16-le', errors='replace')
            else:
                # Try utf-8 first, then fall back to latin-1 or ascii with replace
                try:
                    return exif_data.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return exif_data.decode('latin-1') # Common for some EXIF data
                    except UnicodeDecodeError:
                        return exif_data.decode('ascii', errors='replace')
        except Exception as e:
            logger.debug(f"EXIF decode error in _im_decode_exif: {e}")
    return str(exif_data) # Return as string if decoding fails

def _im_parse_parameters(text, image_path_for_debug=None, is_target_file_for_debug=False): # Added parameters for debugging
    """Helper function adapted from ImageMover's parse_parameters."""
    # if is_target_file_for_debug:
        # logger.info(f"DEBUG_TARGET_FILE_PARSE: _im_parse_parameters called for {image_path_for_debug}")
        # logger.info(f"DEBUG_TARGET_FILE_PARSE: Input text (first 500 chars): '{text[:500]}'")

    params = {
        'positive_prompt': '',
        'negative_prompt': '',
        'generation_info': ''
    }
    if not isinstance(text, str):
        logger.debug(f"_im_parse_parameters received non-string input: {type(text)} for path {image_path_for_debug}")
        return params
    try:
        neg_markers = ['Negative prompt:', 'negative_prompt:', 'neg_prompt:']
        neg_prompt_start = -1
        neg_marker_len = 0 # Store the length of the found marker
        for marker in neg_markers:
            pos = text.find(marker)
            if pos != -1:
                neg_prompt_start = pos
                neg_marker_len = len(marker)
                break
        
        info_markers_priority = ['Steps:']
        info_markers_fallback = ['Model:', 'Size:', 'Seed:', 'Sampler:', 'CFG scale:', 'Clip skip:']
        
        steps_start = -1
        
        for marker in info_markers_priority:
            pos = text.find(marker, neg_prompt_start + neg_marker_len if neg_prompt_start != -1 else 0)
            if pos != -1:
                if neg_prompt_start != -1 and pos < neg_prompt_start + neg_marker_len : 
                    continue
                steps_start = pos
                break
        
        if steps_start == -1:
            search_after_pos = neg_prompt_start + neg_marker_len if neg_prompt_start != -1 else 0
            for marker in info_markers_fallback:
                pos = text.find(marker, search_after_pos)
                if pos != -1:
                    if neg_prompt_start != -1 and pos < neg_prompt_start + neg_marker_len:
                        continue
                    if steps_start == -1 or pos < steps_start: 
                        steps_start = pos

        if neg_prompt_start != -1:
            params['positive_prompt'] = text[:neg_prompt_start].strip()
            if steps_start != -1 and steps_start > neg_prompt_start: 
                params['negative_prompt'] = text[neg_prompt_start + neg_marker_len : steps_start].strip()
                params['generation_info'] = text[steps_start:].strip()
            else:
                params['negative_prompt'] = text[neg_prompt_start + neg_marker_len:].strip()
        else: 
            if steps_start != -1:
                params['positive_prompt'] = text[:steps_start].strip()
                params['generation_info'] = text[steps_start:].strip()
            else:
                params['positive_prompt'] = text.strip()
                
    except Exception as e:
        logger.error(f"Error parsing parameters in _im_parse_parameters: {e}", exc_info=True)
        params['positive_prompt'] = text.strip()
        params['negative_prompt'] = ""
        params['generation_info'] = ""
    
    # if is_target_file_for_debug:
        # logger.info(f"DEBUG_TARGET_FILE_PARSE: neg_prompt_start = {neg_prompt_start}, steps_start = {steps_start}")
        # logger.info(f"DEBUG_TARGET_FILE_PARSE: Parsed params = {params}")
    return params

def extract_image_metadata(image_path):
    """
    Extracts positive_prompt, negative_prompt, and generation_info from an image,
    returning them as a dictionary.
    """
    target_file_for_debug_raw = r"G:\test\00005-4187066497.jpg"
    normalized_target_path = target_file_for_debug_raw.replace("\\", "/")
    normalized_image_path = image_path.replace("\\", "/")
    is_target_file = (normalized_image_path == normalized_target_path)
    
    # if is_target_file:
        # logger.info(f"DEBUG_TARGET_FILE: Processing {image_path} (Normalized: {normalized_image_path})")

    extracted_params = {
        'positive_prompt': '',
        'negative_prompt': '',
        'generation_info': ''
    }
    raw_text_to_parse = None

    try:
        with Image.open(image_path) as img:
            if 'parameters' in img.info and isinstance(img.info['parameters'], str):
                raw_text_to_parse = img.info['parameters']
                logger.debug(f"Found 'parameters' in info for {image_path}")
            
            if raw_text_to_parse is None and 'exif' in img.info:
                decoded_exif_info = _im_decode_exif(img.info['exif'])
                if isinstance(decoded_exif_info, str) and ("Steps:" in decoded_exif_info or "Negative prompt:" in decoded_exif_info or "Seed:" in decoded_exif_info):
                    raw_text_to_parse = decoded_exif_info
                    logger.debug(f"Used decoded 'exif' from img.info for {image_path}")

            if raw_text_to_parse is None and (img.format == "JPEG" or img.format == "WEBP"):
                exif_data_obj = img.getexif() 
                if exif_data_obj:
                    user_comment = exif_data_obj.get(0x9286) 
                    if user_comment:
                        decoded_comment = _im_decode_exif(user_comment)
                        if isinstance(decoded_comment, str) and decoded_comment.strip():
                            raw_text_to_parse = decoded_comment
                            logger.debug(f"Found UserComment (0x9286) in EXIF for {image_path}")
                    
                    if raw_text_to_parse is None:
                        image_desc = exif_data_obj.get(0x010e) 
                        if image_desc:
                            decoded_desc = _im_decode_exif(image_desc)
                            if isinstance(decoded_desc, str) and decoded_desc.strip():
                                raw_text_to_parse = decoded_desc
                                logger.debug(f"Found ImageDescription (0x010e) in EXIF for {image_path}")
            
            if raw_text_to_parse is None and 'Comment' in img.info:
                comment_content = img.info['Comment']
                if isinstance(comment_content, str):
                    try:
                        comment_json = json.loads(comment_content)
                        if isinstance(comment_json, dict):
                            if 'prompt' in comment_json and isinstance(comment_json['prompt'], str):
                                raw_text_to_parse = comment_json['prompt']
                                logger.debug(f"Used 'prompt' from JSON in Comment for {image_path}")
                    except json.JSONDecodeError:
                        if ("Steps:" in comment_content or "Negative prompt:" in comment_content or "Seed:" in comment_content):
                             raw_text_to_parse = comment_content
                             logger.debug(f"Used raw string from Comment for {image_path}")

            if raw_text_to_parse:
                extracted_params = _im_parse_parameters(raw_text_to_parse, image_path, is_target_file)
            else:
                logger.debug(f"No suitable metadata text found to parse in {image_path}")

    except FileNotFoundError:
        logger.error(f"Metadata extraction: File not found {image_path}")
    except Exception as e:
        logger.error(f"Error extracting metadata for {image_path}: {e}", exc_info=True)
    
    return extracted_params