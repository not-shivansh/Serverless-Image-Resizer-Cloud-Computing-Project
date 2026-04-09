"""AI image detection service using offline EXIF heuristics."""

import logging
from io import BytesIO
from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

class AIDetectionService:
    """Uses offline heuristics based on image metadata to detect AI generation."""
    
    @staticmethod
    def analyze_image(file_bytes: bytes, filename: str) -> dict:
        """
        Analyze image properties and EXIF metadata to determine if it is likely AI-generated.
        
        Returns:
            dict: {"is_ai_generated": bool | None, "ai_confidence": float | None}
        """
        try:
            image = Image.open(BytesIO(file_bytes))
            
            # Known AI platforms often populate "Software" or use PNG text chunks
            ai_software_signatures = [
                "midjourney", "dall-e", "stable diffusion", "bing", 
                "novelai", "leonardo", "civitai", "openai"
            ]
            
            # Real cameras leave these EXIF footprints
            photo_fields = [
                "Make", "Model", "FNumber", "ExposureTime", "ISOSpeedRatings", 
                "FocalLength", "LensModel", "DateTimeOriginal", "Flash"
            ]

            is_ai = False
            confidence = 0.5
            
            # --- PNG Metadata Check ---
            if image.format == "PNG" and hasattr(image, "info"):
                for k, v in image.info.items():
                    val_str = str(v).lower()
                    if any(ai_name in val_str for ai_name in ai_software_signatures):
                        return {"is_ai_generated": True, "ai_confidence": 0.99}
                    if str(k).lower() in ("parameters", "prompt", "workflow") and len(val_str) > 10:
                        return {"is_ai_generated": True, "ai_confidence": 0.95}

            # --- EXIF Check ---
            exif_data = image.getexif()
            
            if not exif_data:
                # No EXIF data: extremely common for web screenshots, WhatsApp images, and AI pictures.
                # Default to real to prevent annoying false positives.
                return {"is_ai_generated": False, "ai_confidence": 0.50}

            # Map EXIF tag IDs to string names
            exif_dict = {}
            for tag_id, value in exif_data.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                exif_dict[str(tag)] = str(value)
                
            # 1. Direct Software footprint check
            software = str(exif_dict.get("Software", "")).lower()
            if any(name in software for name in ai_software_signatures):
                return {"is_ai_generated": True, "ai_confidence": 0.99}

            # 2. Camera Metadata check
            photo_score = sum(1 for field in photo_fields if field in exif_dict)
            
            if photo_score >= 2:
                # Fair amount of camera metadata
                return {"is_ai_generated": False, "ai_confidence": 0.95}
                
            # Sparse metadata (e.g., just orientation) but no obvious AI signatures.
            # Default to real to prevent annoying false positives.
            return {"is_ai_generated": False, "ai_confidence": 0.60}

        except Exception as e:
            logger.warning("Failed to analyze image for AI detection: %s", e)
            return {"is_ai_generated": None, "ai_confidence": None}
