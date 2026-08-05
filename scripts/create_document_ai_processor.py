#!/usr/bin/env python3
"""Find or create the Case Closed Enterprise OCR processor."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402


def processor_id(*, apply: bool) -> str | None:
    if not config.PROJECT_ID:
        raise RuntimeError("PROJECT_ID is required")
    from google.cloud import documentai
    client = documentai.DocumentProcessorServiceClient(client_options={
        "api_endpoint": f"{config.DOCUMENT_AI_LOCATION}-documentai.googleapis.com"})
    parent = client.common_location_path(config.PROJECT_ID, config.DOCUMENT_AI_LOCATION)
    if config.DOCUMENT_AI_PROCESSOR_ID:
        name = client.processor_path(config.PROJECT_ID, config.DOCUMENT_AI_LOCATION,
                                     config.DOCUMENT_AI_PROCESSOR_ID)
        client.get_processor(name=name)
        return config.DOCUMENT_AI_PROCESSOR_ID
    for processor in client.list_processors(parent=parent):
        if processor.type_ == "OCR_PROCESSOR" and processor.display_name == "caseclosed-ocr":
            return processor.name.rsplit("/", 1)[-1]
    if not apply:
        return None
    processor = client.create_processor(parent=parent, processor=documentai.Processor(
        display_name="caseclosed-ocr", type_="OCR_PROCESSOR"))
    return processor.name.rsplit("/", 1)[-1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    found = processor_id(apply=args.apply)
    if found:
        print(f"DOCUMENT_AI_PROCESSOR_ID={found}")
    else:
        print("No caseclosed-ocr processor exists; rerun with --apply to create it.")
