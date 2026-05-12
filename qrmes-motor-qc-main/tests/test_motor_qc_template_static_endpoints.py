from pathlib import Path


TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "app_web" / "templates" / "motor_qc"


def test_motor_qc_templates_use_blueprint_static_endpoint_in_split_repo():
    html_files = sorted(TEMPLATE_ROOT.glob("*.html"))
    assert html_files, "motor_qc 模板目录不应为空"

    offending = []
    for template in html_files:
        text = template.read_text(encoding="utf-8")
        if "url_for('static'" in text or 'url_for("static"' in text:
            offending.append(template.name)

    assert not offending, (
        "split 后 motor_qc 静态资源不再位于 web-core 全局 /static，下列模板仍在错误使用全局 static 端点："
        + ", ".join(offending)
    )


def test_motor_qc_templates_reference_blueprint_static_assets():
    base_html = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")
    tasks_html = (TEMPLATE_ROOT / "tasks.html").read_text(encoding="utf-8")

    assert "url_for('motor_qc.static'" in base_html
    assert "url_for('motor_qc.static'" in tasks_html
