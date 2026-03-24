import os
import logging

from pdfminer.high_level import extract_text
from werkzeug.utils import secure_filename

import config


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS


def save_uploaded_pdf(file_obj, upload_folder: str):
    name = secure_filename(file_obj.filename)
    path = os.path.join(upload_folder, name)
    file_obj.save(path)
    return name, path


def extract_pdf_text(path: str, filename: str) -> str:
    try:
        pdf_text = extract_text(path)
        if not pdf_text or len(pdf_text.strip()) < 10:
            pdf_text = f"[PDF {filename} uploaded but text extraction yielded minimal content]"
    except Exception as e:
        pdf_text = f"[Error extracting text from PDF: {e}]"
    return pdf_text


def cleanup_temp_file(filepath: str):
    try:
        os.remove(filepath)
    except FileNotFoundError:
        logging.warning("Temp file already removed or missing: %s", filepath)
    except Exception as e:
        logging.warning("Failed to delete temp file %s: %s", filepath, e)
