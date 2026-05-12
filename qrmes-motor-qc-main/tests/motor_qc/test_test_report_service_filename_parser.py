from pathlib import Path

from app_web.test_report_service import WordDocParser


def make_parser() -> WordDocParser:
    # 不依赖 python-docx，直接测试纯字符串解析逻辑
    return WordDocParser.__new__(WordDocParser)


def test_parse_filename_with_underscore_format():
    parser = make_parser()
    info = parser._parse_filename("TZ210009225100001_2025_10_24_19_17_52_Pass.docx")

    assert info["serial_number"] == "TZ210009225100001"
    assert info["test_result"] == "Pass"
    assert info["test_time"].strftime("%Y-%m-%d %H:%M:%S") == "2025-10-24 19:17:52"


def test_parse_filename_with_space_format():
    parser = make_parser()
    info = parser._parse_filename("TZ80013925090008 2025 09 28 16 34 27 Fail.docx")

    assert info["serial_number"] == "TZ80013925090008"
    assert info["test_result"] == "Fail"
    assert info["test_time"].strftime("%Y-%m-%d %H:%M:%S") == "2025-09-28 16:34:27"


def test_parse_path_context_time_fallback():
    parser = make_parser()
    path = Path(
        "/Volumes/测试中心/3、下线台架测试 Offline test data/1、台架测试数据/3、反电势数据/"
        "三一5T油泵/反电势_2025_10_09_17_44_26/三一5T油泵/TestCaseReport.docx"
    )

    info = parser._parse_path_context(path)
    assert info["test_time"].strftime("%Y-%m-%d %H:%M:%S") == "2025-10-09 17:44:26"


def test_parse_filename_generic_name_should_not_be_serial():
    parser = make_parser()
    info = parser._parse_filename("TestCaseReport.docx")

    assert info == {}
