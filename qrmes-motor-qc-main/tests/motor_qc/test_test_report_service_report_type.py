from datetime import datetime
from pathlib import Path
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


def test_scan_should_store_report_type_for_multi_sources(tmp_path):
    bemf_root = tmp_path / "3、反电势数据"
    hil_root = tmp_path / "5、柳工3.5T双12 HILL 测试报告"

    bemf_file = bemf_root / "项目A" / "A_2026_01_01_10_00_00_Pass.docx"
    hil_file = hil_root / "项目H" / "H_2026_01_01_11_00_00_Pass.docx"
    _make_valid_docx(bemf_file)
    _make_valid_docx(hil_file)

    db_path = tmp_path / "test_reports.db"
    service = trs.TestReportService(db_path, [(bemf_root, "BEMF"), (hil_root, "HIL")])
    service.parser = _StubParser()

    result = service.scan_and_import()
    assert result["success"] is True
    assert result["stats"]["imported"] == 2

    hil_reports, _ = service.list_reports(report_type="HIL", limit=20, offset=0)
    bemf_reports, _ = service.list_reports(report_type="BEMF", limit=20, offset=0)

    assert len(hil_reports) == 1
    assert len(bemf_reports) == 1
    assert hil_reports[0]["report_type"] == "HIL"
    assert bemf_reports[0]["report_type"] == "BEMF"


def test_statistics_should_support_report_type_filter(tmp_path):
    bemf_root = tmp_path / "3、反电势数据"
    hil_root = tmp_path / "5、柳工3.5T双12 HILL 测试报告"

    _make_valid_docx(bemf_root / "项目A" / "A1_2026_01_01_10_00_00_Pass.docx")
    _make_valid_docx(hil_root / "项目H" / "H1_2026_01_01_11_00_00_Fail.docx")

    db_path = tmp_path / "test_reports.db"
    service = trs.TestReportService(db_path, [(bemf_root, "BEMF"), (hil_root, "HIL")])
    service.parser = _StubParser()

    service.scan_and_import()

    all_stats = service.get_statistics()
    hil_stats = service.get_statistics(report_type="HIL")
    bemf_stats = service.get_statistics(report_type="BEMF")

    assert all_stats["total"] == 2
    assert hil_stats["total"] == 1
    assert bemf_stats["total"] == 1


def test_list_reports_should_support_serial_keyword_filter(tmp_path):
    root = tmp_path / "3、反电势数据"
    _make_valid_docx(root / "项目A" / "SERIAL_A_2026_01_01_10_00_00_Pass.docx")
    _make_valid_docx(root / "项目A" / "SERIAL_B_2026_01_01_11_00_00_Pass.docx")

    db_path = tmp_path / "test_reports.db"
    service = trs.TestReportService(db_path, [(root, "BEMF")])
    service.parser = _StubParser()
    service.scan_and_import()

    rows, total = service.list_reports(serial_keyword="SERIAL_A", limit=20, offset=0)

    assert total == 1
    assert len(rows) == 1
    assert rows[0]["serial_number"].startswith("SERIAL_A")
