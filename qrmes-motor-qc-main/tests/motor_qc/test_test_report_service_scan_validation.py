from datetime import datetime
from pathlib import Path
import zipfile

from app_web import test_report_service as trs


class _StubParser:
    def __init__(self):
        self.calls = []

    def parse(self, file_path: Path):
        self.calls.append(file_path.name)
        return trs.TestReport(
            serial_number="S1",
            project_name=file_path.parent.name,
            test_module="M1",
            test_result="Pass",
            test_time=datetime(2025, 1, 1, 0, 0, 0),
            file_path=str(file_path),
            file_name=file_path.name,
            description="",
            test_values=[],
            attachments={},
        )


def test_scan_should_skip_non_docx_packages(tmp_path):
    data_root = tmp_path / "root"
    project_dir = data_root / "项目A"
    project_dir.mkdir(parents=True)

    # 合法 ZIP（作为可解析 docx 包）
    valid_docx = project_dir / "valid.docx"
    with zipfile.ZipFile(valid_docx, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")

    # 大写扩展名同样应被识别
    valid_upper_docx = project_dir / "valid_upper.DOCX"
    with zipfile.ZipFile(valid_upper_docx, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")

    # 非法 docx（仅扩展名匹配）
    invalid_docx = project_dir / "invalid.docx"
    invalid_docx.write_text("not a real docx", encoding="utf-8")

    # Office 临时文件应被直接忽略
    temp_docx = project_dir / "~$temp.docx"
    temp_docx.write_text("tmp", encoding="utf-8")

    db_path = tmp_path / "test_reports.db"
    service = trs.TestReportService(db_path, data_root)
    parser = _StubParser()
    service.parser = parser

    result = service.scan_and_import()
    stats = result["stats"]

    assert result["success"] is True
    assert stats["scanned"] == 3
    assert stats["imported"] == 2
    assert stats["failed"] == 0
    assert stats["skipped_invalid_docx"] == 1
    assert parser.calls == ["valid.docx", "valid_upper.DOCX"]
    assert stats["skipped_invalid_docx_samples"] == [str(invalid_docx)]
