# src/thumbnail_loader.py
import logging
import json
import os # For os.path.getmtime and os.cpu_count()
import concurrent.futures # For ThreadPoolExecutor
import threading # For Lock
from PyQt6.QtCore import QThread, pyqtSignal
from PIL import Image
try:
    from PIL import ImageQt
except ImportError:
    ImageQt = None

logger = logging.getLogger(__name__)

# --- Metadata Extraction Logic (remains unchanged) ---
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
    return str(exif_data)

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
        
        # Prioritize "Steps:" as the primary separator for generation_info
        # then other common markers if "Steps:" is not found earlier.
        info_markers_priority = ['Steps:']
        info_markers_fallback = ['Model:', 'Size:', 'Seed:', 'Sampler:', 'CFG scale:', 'Clip skip:']
        
        steps_start = -1
        
        # Search for "Steps:" first
        for marker in info_markers_priority:
            pos = text.find(marker, neg_prompt_start + neg_marker_len if neg_prompt_start != -1 else 0)
            if pos != -1:
                if neg_prompt_start != -1 and pos < neg_prompt_start + neg_marker_len : # ensure steps_start is after negative prompt
                    continue
                steps_start = pos
                break
        
        # If "Steps:" not found or found before negative prompt, search for other markers
        if steps_start == -1:
            search_after_pos = neg_prompt_start + neg_marker_len if neg_prompt_start != -1 else 0
            for marker in info_markers_fallback:
                pos = text.find(marker, search_after_pos)
                if pos != -1:
                    if neg_prompt_start != -1 and pos < neg_prompt_start + neg_marker_len:
                        continue
                    if steps_start == -1 or pos < steps_start: # Find the earliest marker
                        steps_start = pos

        if neg_prompt_start != -1:
            params['positive_prompt'] = text[:neg_prompt_start].strip()
            if steps_start != -1 and steps_start > neg_prompt_start: # Ensure steps_start is after neg_prompt
                params['negative_prompt'] = text[neg_prompt_start + neg_marker_len : steps_start].strip()
                params['generation_info'] = text[steps_start:].strip()
            else:
                params['negative_prompt'] = text[neg_prompt_start + neg_marker_len:].strip()
        else: # No negative prompt
            if steps_start != -1:
                params['positive_prompt'] = text[:steps_start].strip()
                params['generation_info'] = text[steps_start:].strip()
            else:
                params['positive_prompt'] = text.strip()
                
    except Exception as e:
        logger.error(f"Error parsing parameters in _im_parse_parameters: {e}", exc_info=True)
        # Fallback: put the whole text into positive_prompt if parsing fails
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
    This version is closely based on ImageMover's extract_metadata logic.
    """
    # Use raw string for Windows path and normalize incoming path for comparison
    # Updated path to the new test location
    target_file_for_debug_raw = r"G:\test\00005-4187066497.jpg"
    # Normalize both paths to use forward slashes for consistent comparison
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
            # if is_target_file:
                # logger.info(f"DEBUG_TARGET_FILE: img.format = {img.format}")
                # logger.info(f"DEBUG_TARGET_FILE: img.info = {img.info}")
                # try:
                    # exif_obj = img.getexif()
                    # logger.info(f"DEBUG_TARGET_FILE: img.getexif() class = {type(exif_obj)}")
                    # if hasattr(exif_obj, 'items'): # Check if it's dict-like
                         # logger.info(f"DEBUG_TARGET_FILE: img.getexif() items = {dict(exif_obj.items())}")
                    # else:
                         # logger.info(f"DEBUG_TARGET_FILE: img.getexif() = {exif_obj}") # If not dict-like, print as is
                # except Exception as e_exif:
                    # logger.error(f"DEBUG_TARGET_FILE: Error getting exif for {image_path}: {e_exif}")


            # Attempt to get 'parameters' from img.info (common for A1111 PNGs)
            if 'parameters' in img.info and isinstance(img.info['parameters'], str):
                raw_text_to_parse = img.info['parameters']
                logger.debug(f"Found 'parameters' in info for {image_path}")
                # if is_target_file:
                    # logger.info(f"DEBUG_TARGET_FILE: Found 'parameters' in img.info: {raw_text_to_parse[:500]}")
            
            # If not found, try to get 'exif' data from img.info
            # This 'exif' in img.info is often raw bytes that need decoding.
            if raw_text_to_parse is None and 'exif' in img.info:
                decoded_exif_info = _im_decode_exif(img.info['exif'])
                if isinstance(decoded_exif_info, str) and ("Steps:" in decoded_exif_info or "Negative prompt:" in decoded_exif_info or "Seed:" in decoded_exif_info): # Added Seed as a common keyword
                    raw_text_to_parse = decoded_exif_info
                    logger.debug(f"Used decoded 'exif' from img.info for {image_path}")
                    # if is_target_file:
                        # logger.info(f"DEBUG_TARGET_FILE: Used decoded 'exif' from img.info: {raw_text_to_parse[:500]}")

            # For JPEGs and WebPs, Pillow's getexif() might provide more structured EXIF
            if raw_text_to_parse is None and (img.format == "JPEG" or img.format == "WEBP"):
                exif_data_obj = img.getexif() 
                if exif_data_obj: # exif_data_obj is an instance of Exif, not a dict
                    user_comment = exif_data_obj.get(0x9286) # UserComment
                    if user_comment:
                        decoded_comment = _im_decode_exif(user_comment)
                        if isinstance(decoded_comment, str) and decoded_comment.strip():
                            raw_text_to_parse = decoded_comment
                            logger.debug(f"Found UserComment (0x9286) in EXIF for {image_path}")
                            # if is_target_file:
                                # logger.info(f"DEBUG_TARGET_FILE: Found UserComment (0x9286): {raw_text_to_parse[:500]}")
                    
                    if raw_text_to_parse is None:
                        image_desc = exif_data_obj.get(0x010e) # ImageDescription
                        if image_desc:
                            decoded_desc = _im_decode_exif(image_desc)
                            if isinstance(decoded_desc, str) and decoded_desc.strip():
                                raw_text_to_parse = decoded_desc
                                logger.debug(f"Found ImageDescription (0x010e) in EXIF for {image_path}")
                                # if is_target_file:
                                    # logger.info(f"DEBUG_TARGET_FILE: Found ImageDescription (0x010e): {raw_text_to_parse[:500]}")
            
            # ComfyUI often stores parameters in a 'Comment' tEXt chunk as JSON
            if raw_text_to_parse is None and 'Comment' in img.info:
                comment_content = img.info['Comment']
                if isinstance(comment_content, str):
                    try:
                        comment_json = json.loads(comment_content)
                        if isinstance(comment_json, dict):
                            if 'prompt' in comment_json and isinstance(comment_json['prompt'], str):
                                raw_text_to_parse = comment_json['prompt']
                                logger.debug(f"Used 'prompt' from JSON in Comment for {image_path}")
                                # if is_target_file:
                                    # logger.info(f"DEBUG_TARGET_FILE: Used 'prompt' from JSON in Comment: {raw_text_to_parse[:500]}")
                            # Add other ComfyUI specific heuristics if needed here
                    except json.JSONDecodeError:
                        if ("Steps:" in comment_content or "Negative prompt:" in comment_content or "Seed:" in comment_content):
                             raw_text_to_parse = comment_content
                             logger.debug(f"Used raw string from Comment for {image_path}")
                             # if is_target_file:
                                 # logger.info(f"DEBUG_TARGET_FILE: Used raw string from Comment: {raw_text_to_parse[:500]}")

            # If any text was found, parse it
            if raw_text_to_parse:
                # if is_target_file:
                    # logger.info(f"DEBUG_TARGET_FILE: Final raw_text_to_parse for {image_path}: '{raw_text_to_parse[:500]}...'")
                extracted_params = _im_parse_parameters(raw_text_to_parse, image_path, is_target_file) # Pass debug info
            else:
                logger.debug(f"No suitable metadata text found to parse in {image_path}")
                # if is_target_file:
                    # logger.info(f"DEBUG_TARGET_FILE: No suitable metadata text found to parse.")

    except FileNotFoundError:
        logger.error(f"Metadata extraction: File not found {image_path}")
    except Exception as e:
        logger.error(f"Error extracting metadata for {image_path}: {e}", exc_info=True)
    
    return extracted_params
# --- End of Metadata Extraction Logic ---

class ThumbnailLoaderThread(QThread):
    thumbnailLoaded = pyqtSignal(object, object, dict) # item, q_image, metadata_dict
    progressUpdated = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, file_paths, items_to_process, target_size):
        super().__init__()
        self.file_paths = file_paths
        self.items_to_process = items_to_process # List of QStandardItem
        self.target_size = target_size
        self._is_running = True
        self._processed_count = 0
        self._lock = threading.Lock() # Lock for atomically updating _processed_count

    def _process_single_image(self, file_path, item):
        """Processes a single image: creates thumbnail and extracts metadata."""
        if not self._is_running:
            # Return default/empty data if stopping
            return item, None, {'positive_prompt': '', 'negative_prompt': '', 'generation_info': ''}

        q_image = None
        metadata_dict = {
            'positive_prompt': '',
            'negative_prompt': '',
            'generation_info': ''
        }

        try:
            img = Image.open(file_path)
            img.thumbnail((self.target_size, self.target_size))

            # Revert to original ImageQt conversion logic based on mode for safety/optimality
            if img.mode == "RGBA":
                q_image = ImageQt.ImageQt(img)
            elif img.mode == "RGB":
                q_image = ImageQt.ImageQt(img.convert("RGBA")) # Convert RGB to RGBA
            else: # Other modes like P, L, 1, etc.
                q_image = ImageQt.ImageQt(img.convert("RGBA")) # Convert to RGBA as a general fallback
            
            metadata_dict = extract_image_metadata(file_path)
            return item, q_image, metadata_dict

        except FileNotFoundError:
            logger.error(f"サムネイル生成/メタデータ抽出エラー (ファイルが見つかりません): {file_path}")
            return item, None, metadata_dict
        except Exception as e:
            logger.error(f"サムネイル生成/メタデータ抽出エラー ({file_path}): {e}", exc_info=True)
            return item, None, metadata_dict

    def run(self):
        if ImageQt is None:
            logger.error("ImageQt module not found in thread. Cannot generate thumbnails.")
            self.finished.emit()
            return

        total_files = len(self.file_paths)
        if total_files == 0: # No files to process
            self.finished.emit()
            return
        
        with self._lock: # Ensure _processed_count is reset safely
            self._processed_count = 0

        # Determine number of workers. os.cpu_count() can be None.
        cpu_cores = os.cpu_count()
        if cpu_cores is None or cpu_cores < 1:
            num_workers = 1 # Fallback if os.cpu_count() fails or returns invalid
        else:
            num_workers = cpu_cores
        
        # Adjust num_workers: no more than total_files, and at least 1.
        num_workers = max(1, min(num_workers, total_files))

        logger.info(f"ThumbnailLoaderThread: Using up to {num_workers} workers for {total_files} files.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []

            for i, file_path in enumerate(self.file_paths):
                if not self._is_running:
                    logger.info("ThumbnailLoaderThread: Stop requested, halting submission of new tasks.")
                    break 
                item = self.items_to_process[i]
                future = executor.submit(self._process_single_image, file_path, item)
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                if not self._is_running:
                    logger.info("ThumbnailLoaderThread: Stop requested during task completion processing.")
                    # Note: Already submitted tasks to as_completed will continue to be processed here
                    # until this loop naturally finishes or this break is hit repeatedly.
                    break 
                
                try:
                    item_result, q_image_result, metadata_result = future.result()
                    # Ensure item_result is valid before emitting
                    if item_result is not None:
                         self.thumbnailLoaded.emit(item_result, q_image_result, metadata_result)
                    else:
                        logger.warning(f"Skipping thumbnailLoaded.emit due to None item from future for a task.")

                except concurrent.futures.CancelledError:
                    logger.info("A thumbnail processing task was cancelled.")
                except Exception as e: # Catch errors from future.result() or task execution
                    # This catch is for errors from future.result() itself, or if _process_single_image re-raises
                    logger.error(f"Error retrieving result from future: {e}", exc_info=True)
                    # We don't know which item this was for easily unless we used future_to_item map
                    # And even then, emitting an error for a specific item might be complex here.
                    # _process_single_image should handle its own errors and return (item, None, metadata).

                with self._lock:
                    self._processed_count += 1
                    current_processed_count = self._processed_count
                
                self.progressUpdated.emit(current_processed_count, total_files)
        
        logger.info("ThumbnailLoaderThread: Processing loop finished. Emitting finished signal.")
        self.finished.emit()

    def stop(self):
        logger.info("ThumbnailLoaderThread.stop() called. Setting _is_running to False.")
        self._is_running = False
        # The ThreadPoolExecutor used with a 'with' statement will automatically call
        # shutdown(wait=True) when the 'with' block exits.
        # The _is_running flag is checked within _process_single_image and
        # before submitting new tasks, and in the as_completed loop.
        # This provides a cooperative way to stop processing.
