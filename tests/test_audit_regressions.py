"""Audit regression tests. No real credentials, downloads or account writes."""

from datetime import date, datetime
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

import communication
import features
import numeric
import overview
import pdf_text
import server


class PaginationTests(unittest.TestCase):
    def test_every_page_and_last_offset(self):
        rows = list(range(35))
        for offset, expected in ((0, 10), (10, 20), (20, 30), (30, None)):
            selected, page = communication.paginate(rows, {"limit": 10, "offset": offset})
            self.assertEqual(page["next_offset"], expected)
            self.assertEqual(page["total_count"], 35)
        self.assertIsNone(communication.paginate(rows, {"offset": 30})[1]["next_offset"])

    def test_download_metadata(self):
        item = NS(id="a1", name="fictional.pdf", type=1, url="https://example.invalid/file")
        file = communication.attachment(item, "lesson", "content1", {"date_from": "2026-09-10", "date_to": "2026-09-10"})
        self.assertTrue(file["downloadable"])
        self.assertTrue(file["readable_as_pdf"])
        self.assertEqual(file["download"]["source_id"], "content1")
        item.type = 0
        link = communication.attachment(item, "lesson", "content1")
        self.assertFalse(link["downloadable"])
        self.assertIsNone(link["download"])


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.file = {"id": "a1", "name": "fictional.pdf", "type": 1, "url": "https://example.invalid/file"}
        self.client = Mock()
        self.page = {"lesson_contents": [{"id": "content1", "lesson_id": "lesson1", "attachments": [self.file]}], "next_offset": None}
        self.args = {"source": "lesson", "source_id": "content1", "attachment_id": "a1", "date_from": "2026-09-10", "date_to": "2026-09-10"}

    def test_content_and_lesson_ids_resolve(self):
        for identifier in ("content1", "lesson1"):
            with self.subTest(identifier=identifier), patch.object(features.pedagogy, "handle", return_value=self.page) as handle:
                self.assertEqual(features.resolve_attachment(self.client, {**self.args, "source_id": identifier}), self.file)
                options = handle.call_args.args[2]
                self.assertEqual(options["date_from"], "2026-09-10")
                self.assertEqual(options["date_to"], "2026-09-10")

    def test_lookup_continues_after_first_page(self):
        pages = [{"lesson_contents": [], "next_offset": 200}, self.page]
        with patch.object(features.pedagogy, "handle", side_effect=pages) as handle:
            self.assertEqual(features.resolve_attachment(self.client, self.args), self.file)
            self.assertEqual(handle.call_args.args[2]["offset"], 200)

    def test_missing_file_has_date_guidance(self):
        with patch.object(features.pedagogy, "handle", return_value={"lesson_contents": [], "next_offset": None}):
            with self.assertRaises(features.ToolError) as result:
                features.resolve_attachment(self.client, self.args)
        self.assertEqual(result.exception.code, "ATTACHMENT_NOT_FOUND")
        self.assertIn("date_from/date_to", str(result.exception))


class NumericTests(unittest.TestCase):
    def test_numeric_and_non_numeric_grades(self):
        self.assertEqual(numeric.number("16,5"), 16.5)
        self.assertEqual(numeric.number(" 10 "), 10)
        for value in (None, True, "Abs", "Disp", "N.Not", "NaN", "Infinity"):
            self.assertIsNone(numeric.number(value))
        self.assertEqual(numeric.grade_values("10", "10")["grade_on_20"], 20)
        self.assertIsNone(numeric.grade_values("10", "0")["grade_on_20"])

    def test_raw_flags_are_not_reinterpreted(self):
        grade = NS(subject=NS(name="Fictional"), grade="10", out_of="10", date=date(2026, 9, 10), is_out_of_20=False)
        data = server._format_grade(grade)
        self.assertEqual(data["grade"], "10")
        self.assertFalse(data["is_out_of_20"])
        self.assertEqual(data["grade_on_20"], 20)


class ErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_and_false_confirmation_never_connect(self):
        with patch.dict(os.environ, {"PRONOTE_ENABLE_WRITES": "1"}), patch.object(server, "_get_client") as connect:
            for args in ({}, {"confirm": False}, {"confirm": 1}, {"confirm": "true"}):
                result = await server.call_tool("create_discussion", args)
                self.assertFalse(result.isError)
                self.assertEqual(result.structuredContent["error_code"], "CONFIRMATION_REQUIRED")
        connect.assert_not_called()

    async def test_invalid_source_is_structured(self):
        with patch.object(server, "_get_client") as connect:
            result = await server.call_tool("download_attachment", {"source": "lesson_contents", "source_id": "fictional", "attachment_id": "fictional"})
        self.assertEqual(result.structuredContent["error_code"], "INVALID_ARGUMENT")
        self.assertIn("teaching_resource", result.structuredContent["error"])
        connect.assert_not_called()

    async def test_schema_validation_still_runs(self):
        with patch.object(server, "_get_client") as connect:
            result = await server.call_tool("get_discussions", {"limit": 0})
        self.assertEqual(result.structuredContent["error_code"], "INVALID_ARGUMENT")
        connect.assert_not_called()

    async def test_authentication_error_sets_relogin_flag(self):
        with patch.object(server, "_get_client", side_effect=server.pronotepy.CryptoError("fictional-secret")):
            result = await server.call_tool("get_grades", {})
        self.assertTrue(result.structuredContent["relogin_required"])
        self.assertNotIn("fictional-secret", json.dumps(result.structuredContent))

    async def test_credential_storage_failure_keeps_error_flag(self):
        with patch.object(server, "_dispatch_tool", new=AsyncMock(return_value=server._json_result({"success": True}))), \
                patch.object(server, "_persist_client_credentials", side_effect=OSError("fictional-secret")):
            result = await server.call_tool("get_grades", {})
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["error_code"], "CREDENTIAL_STORAGE_FAILED")
        self.assertNotIn("fictional-secret", json.dumps(result.structuredContent))


class PdfTests(unittest.TestCase):
    def setUp(self):
        preferred = Path("/tmp/opencode")
        self.temp = tempfile.TemporaryDirectory(dir=preferred if preferred.is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fictional.pdf"

    def write_pdf(self, texts):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        writer = PdfWriter()
        for text in texts:
            page = writer.add_blank_page(width=200, height=200)
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(self.path)

    def test_page_pagination_and_text_budget(self):
        self.write_pdf(["First fictional page", "Second fictional page"])
        data = pdf_text.extract(self.path, 1, 1, 30000)
        self.assertIn("First fictional page", data["pages"][0]["text"])
        self.assertEqual(data["next_page"], 2)
        short = pdf_text.extract(self.path, 1, 2, 5)
        self.assertEqual(short["pages"][0]["text"], "First")
        self.assertTrue(short["truncated"])
        self.assertEqual(short["next_page"], 1)

    def test_real_worker_and_cleanup(self):
        self.write_pdf(["Fictional PDF text"])
        with patch.object(features, "download", return_value={"path": str(self.path), "original_name": "fictional.pdf", "bytes": self.path.stat().st_size}):
            result = pdf_text.handle(Mock(), {})
        self.assertTrue(result["has_text"])
        self.assertIn("Fictional PDF text", result["pages"][0]["text"])
        self.assertFalse(self.path.exists())

    def test_non_pdf_rejected_and_removed(self):
        self.path.write_bytes(b"not a PDF")
        with patch.object(features, "download", return_value={"path": str(self.path), "original_name": "fictional.pdf", "bytes": 9}):
            with self.assertRaises(features.ToolError) as result:
                pdf_text.handle(Mock(), {})
        self.assertEqual(result.exception.code, "UNSUPPORTED_DOCUMENT")
        self.assertFalse(self.path.exists())

    def test_blank_pdf_no_text_is_explicit(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(self.path)
        result = pdf_text.extract(self.path, 1, 10, 1000)
        self.assertFalse(result["has_text"])
        self.assertFalse(result["ocr_supported"])

    def test_timeout_cleans_download(self):
        import subprocess
        self.write_pdf(["Fictional"])
        with patch.object(features, "download", return_value={"path": str(self.path), "original_name": "fictional.pdf", "bytes": 100}), \
                patch.object(pdf_text.subprocess, "run", side_effect=subprocess.TimeoutExpired("worker", 25)):
            with self.assertRaises(features.ToolError) as result:
                pdf_text.handle(Mock(), {})
        self.assertEqual(result.exception.code, "DOCUMENT_LIMIT_EXCEEDED")
        self.assertFalse(self.path.exists())


class OverviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_week_filters_attendance_and_keeps_partial_errors(self):
        client = Mock()
        client.periods = [NS(start=datetime(2026, 9, 1), end=datetime(2026, 12, 31),
                             absences=[NS(from_date=datetime(2026, 9, 28), to_date=datetime(2026, 9, 29)),
                                       NS(from_date=datetime(2026, 9, 10), to_date=datetime(2026, 9, 11))], delays=[])]
        handlers = {"timetable": AsyncMock(return_value=server._json_result({"lessons": []})),
                    "homework": AsyncMock(side_effect=RuntimeError("fictional-secret"))}
        with patch.object(overview.pedagogy, "handle", return_value={"lesson_contents": [], "next_offset": None}):
            result = await overview.handle("summarize_week", client, {"date": "2026-10-04"}, None, handlers, Mock(), Mock(), lambda row: {"start": row.from_date.isoformat()}, Mock())
        self.assertEqual(result["date_from"], "2026-09-28")
        self.assertEqual(len(result["sections"]["attendance"]["absences"]), 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("fictional-secret", json.dumps(result))

    async def test_grade_history_deduplicates_period_overlap(self):
        row = NS(id="g1", subject=NS(name="French"), grade="10", out_of="10", date=date(2026, 9, 1), comment="Fictional", coefficient="1")
        other = NS(id="g2", subject=row.subject, grade="16,5", out_of="20", date=date(2026, 10, 1), comment="Fictional", coefficient="2")
        first = NS(name="Period 1", grades=[row])
        second = NS(name="Semester", grades=[row, other])
        result = await overview.handle("get_grade_trend", Mock(), {"period_names": ["Period 1", "Semester"]}, None, {}, Mock(side_effect=[first, second]), server._format_grade, Mock(), Mock())
        subject = result["subjects"][0]
        self.assertEqual(subject["grade_count"], 2)
        self.assertEqual(subject["mean_on_20"], 18.25)
        self.assertEqual(subject["change_on_20"], -3.5)
        self.assertIn("not official", result["note"])
