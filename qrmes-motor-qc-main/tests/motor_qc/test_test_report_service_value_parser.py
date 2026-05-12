from app_web.test_report_service import WordDocParser


class _Cell:
    def __init__(self, text: str):
        self.text = text


class _Row:
    def __init__(self, cells):
        self.cells = [_Cell(c) for c in cells]


def make_parser() -> WordDocParser:
    return WordDocParser.__new__(WordDocParser)


def test_parse_test_values_table_should_only_keep_calibration_values():
    parser = make_parser()
    info = {"test_values": []}
    rows = [
        _Row(["测试模块", "三一4.5T", "三一4.5T", "三一4.5T", "三一4.5T"]),
        _Row(["说明", "", "", "", ""]),
        _Row(["测试结果", "通过", "通过", "通过", "通过"]),
        _Row(["校验测试值", "名称", "值", "最小值", "最大值"]),
        _Row(["校验测试值", "4.5T", "49.136", "12.5", "50"]),
        _Row(["记录测试值", "名称", "名称", "值", "值"]),
        _Row(["记录测试值", "序列号", "序列号", "TZ210009225100001", "TZ210009225100001"]),
        _Row(["总线记录", "", "", "", ""]),
        _Row(["运行记录", "", "", "", ""]),
    ]

    parser._parse_test_values_table(rows, 3, info)

    assert len(info["test_values"]) == 1
    tv = info["test_values"][0]
    assert tv.name == "4.5T"
    assert tv.value == 49.136
    assert tv.min_value == 12.5
    assert tv.max_value == 50.0
    assert tv.is_pass is True


def test_parse_test_values_table_should_parse_numeric_with_unit():
    parser = make_parser()
    info = {"test_values": []}
    rows = [
        _Row(["校验测试值", "名称", "值", "最小值", "最大值"]),
        _Row(["校验测试值", "柳工双12油泵", "11.128V", "6V", "16V"]),
        _Row(["记录测试值", "名称", "名称", "值", "值"]),
    ]

    parser._parse_test_values_table(rows, 0, info)

    assert len(info["test_values"]) == 1
    tv = info["test_values"][0]
    assert tv.name == "柳工双12油泵"
    assert tv.value == 11.128
    assert tv.min_value == 6.0
    assert tv.max_value == 16.0
    assert tv.is_pass is True


def test_parse_table_should_extract_serial_from_record_section():
    parser = make_parser()
    info = {"test_values": [], "attachments": {}}
    rows = [
        _Row(["记录测试值", "序列号SN", "序列号SN", "GenesisLiGFLF10C2026021100098", "GenesisLiGFLF10C2026021100098"]),
    ]
    table = type("TableStub", (), {"rows": rows})()

    parser._parse_table(table, info)

    assert info["serial_number"] == "GenesisLiGFLF10C2026021100098"
