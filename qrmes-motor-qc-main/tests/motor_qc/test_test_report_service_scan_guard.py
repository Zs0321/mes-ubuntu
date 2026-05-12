from datetime import datetime
from pathlib import Path
import sqlite3
import zipfile

from app_web import test_report_service as trs


class _StubParser:
    def parse(self, file_path: Path):
        return trs.TestReport(
            serial_number=file_path.stem,
            project_name=file_path.parent.name,
            test_module="M1",
            test_result="Pass",
            test_time=datetime(2026, 1, 1, 12, 0, 0),
            file_path=str(file_path),
            file_name=file_path.name,
            description="",
            test_values=[],
            attachments={},
        )


def _make_valid_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")


def test_scan_should_reject_reentrant_requests(tmp_path):
    root = tmp_path / "3、反电势数据"
    _make_valid_docx(root / "项目A" / "A_2026_01_01_10_00_00_Pass.docx")

    service = trs.TestReportService(tmp_path / "test_reports.db", [(root, "BEMF")])
    service.parser = _StubParser()

    assert service._scan_lock.acquire(blocking=False) is True
    try:
        result = service.scan_and_import()
    finally:
        service._scan_lock.release()

    assert result["success"] is False
    assert "正在执行" in result["error"]


def test_save_report_should_update_existing_path_without_duplicates(tmp_path):
    repo = trs.TestReportRepository(tmp_path / "test_reports.db")

    report = trs.TestReport(
        serial_number="TZ001",
        project_name="项目A",
        test_module="M1",
        test_result="Pass",
        test_time=datetime(2026, 1, 1, 12, 0, 0),
        file_path="/tmp/report.docx",
        file_name="report.docx",
        report_type="BEMF",
        description="first",
        test_values=[trs.TestValue("value", 1.0, 0.0, 2.0, True, "record")],
        attachments={"raw": "raw.docx"},
    )
    report_id_1 = repo.save_report(report)

    updated = trs.TestReport(
        serial_number="TZ001",
        project_name="项目A",
        test_module="M2",
        test_result="Fail",
        test_time=datetime(2026, 1, 1, 13, 0, 0),
        file_path="/tmp/report.docx",
        file_name="report.docx",
        report_type="BEMF",
        description="second",
        test_values=[trs.TestValue("value", 3.0, 0.0, 2.0, False, "record")],
        attachments={"raw": "raw2.docx"},
    )
    report_id_2 = repo.save_report(updated)

    assert report_id_1 == report_id_2

    with sqlite3.connect(tmp_path / "test_reports.db") as conn:
        cur = conn.cursor()
        cur.execute("select count(*) from test_reports where file_path = ?", ("/tmp/report.docx",))
        assert cur.fetchone()[0] == 1
        cur.execute("select test_module, test_result, description from test_reports where id = ?", (report_id_1,))
        assert cur.fetchone() == ("M2", "Fail", "second")
        cur.execute("select count(*) from test_values where report_id = ?", (report_id_1,))
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from test_attachments where report_id = ?", (report_id_1,))
        assert cur.fetchone()[0] == 1
