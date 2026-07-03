import os
import uuid
import logging
from docx import Document as DocxDocument
from pdfminer.high_level import extract_text as extract_pdf_text_miner
from werkzeug.utils import secure_filename

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'docx', 'doc', 'txt'}

def secure_save_document(file_obj, upload_folder: str) -> tuple[str, str]:
    """Generates a UUID-locked filename preventing cross-request race conditions."""
    safe_name = secure_filename(file_obj.filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    path = os.path.join(upload_folder, unique_name)
    file_obj.save(path)
    return safe_name, path

def extract_pdf_text(filepath: str) -> str:
    try:
        pdf_text = extract_pdf_text_miner(filepath)
        if not pdf_text or len(pdf_text.strip()) < 10:
            return "[PDF extracted but yielded minimal content]"
        return pdf_text
    except Exception as e:
        return f"[Error extracting text from PDF: {e}]"

def extract_docx_text(filepath: str) -> str:
    try:
        doc = DocxDocument(filepath)
        return '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        return f"[Error extracting DOCX: {e}]"

def extract_txt_text(filepath: str) -> str:
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def extract_document_text(filepath: str, original_filename: str) -> str:
    ext = original_filename.rsplit('.', 1)[-1].lower()
    if ext == 'pdf':
        return extract_pdf_text(filepath)
    elif ext in ('docx', 'doc'):
        return extract_docx_text(filepath)
    elif ext == 'txt':
        return extract_txt_text(filepath)
    else:
        raise ValueError(f'Unsupported file type: .{ext}')

def process_upload(file_obj, upload_folder: str) -> dict:
    """End-to-end ingestion: saves, parses, cleans up, and returns payload securely."""
    if not file_obj or not allowed_file(file_obj.filename):
        raise ValueError("Invalid or unsupported file type.")
        
    safe_name, path = secure_save_document(file_obj, upload_folder)
    try:
        text = extract_document_text(path, safe_name)
        return {
            "filename": safe_name,
            "text": text,
            "included": False
        }
    finally:
        cleanup_temp_file(path)

def cleanup_temp_file(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        logging.error("Failed to delete temp file %s: %s", filepath, e)
