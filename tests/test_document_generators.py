"""Tests de document_generators (sin llamar a Gemini)."""
import os
from unittest import mock

import document_generators
from document_generators import CoverLetterGenerator, ResumeOptimizer, _safe_filename


def test_safe_filename_strips_path_separators():
    name = _safe_filename("resume", "../../etc/passwd", "Acme/Corp", "docx")
    assert "/" not in name and ".." not in name
    assert name.startswith("resume_") and name.endswith(".docx")


def test_cover_letter_strips_markdown():
    with mock.patch.object(document_generators, "_call_gemini", return_value="**Hola** # equipo"):
        letter = CoverLetterGenerator().generate_cover_letter("cv", "desc", "Dev", "Acme")
    assert letter == "Hola  equipo"


def test_optimize_resume_passes_job_data_to_prompt():
    with mock.patch.object(document_generators, "_call_gemini", return_value="CV") as call:
        ResumeOptimizer().optimize_resume("mi cv", "Python y SQL", "Data Engineer", "Acme")
    prompt = call.call_args[0][0]
    assert "mi cv" in prompt and "Python y SQL" in prompt and "Data Engineer" in prompt


def test_save_resume_writes_file(tmp_path):
    filename = ResumeOptimizer().save_resume("RESUMEN\n\n- Python", "Dev", "Acme", output_dir=str(tmp_path))
    assert os.path.dirname(filename) == ""
    assert filename.startswith("resume_Dev_Acme_")
