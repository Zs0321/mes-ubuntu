#!/usr/bin/env python3
"""Run local edge-frontend regression with optional auto-start services.

Flow:
1) Ensure MES web (8891) and edge bridge stub (19091) are reachable.
2) Login to MES web and open edge mode task page.
3) Scan-start session, simulate button-end from bridge, verify timeline/state.
4) Open manual review page and verify "review-only" filter behavior.
5) Save JSON report + screenshots under output/playwright.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_WEB_DIR = REPO_ROOT / "app_web"
OUTPUT_ROOT = REPO_ROOT / "output" / "playwright"


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def json_request(
    url: str,
    method: str = "GET",
    payload: Optional[dict] = None,
    timeout: float = 5.0,
) -> Tuple[int, str]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return int(getattr(resp, "status", 200)), body


def is_http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        status, _body = json_request(url, timeout=timeout)
        return 200 <= status < 500
    except Exception:
        return False


def wait_http_ok(url: str, timeout: float, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_http_ok(url, timeout=2.0):
            return True
        time.sleep(interval)
    return False


@dataclass
class ManagedProc:
    name: str
    popen: subprocess.Popen
    log_file: Path


def start_process(name: str, cmd: List[str], cwd: Path, log_file: Path) -> ManagedProc:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handle = log_file.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    return ManagedProc(name=name, popen=proc, log_file=log_file)


def stop_process(proc: ManagedProc) -> None:
    if proc.popen.poll() is not None:
        return
    try:
        os.killpg(proc.popen.pid, signal.SIGTERM)
        proc.popen.wait(timeout=6)
    except Exception:
        try:
            os.killpg(proc.popen.pid, signal.SIGKILL)
        except Exception:
            pass


def first_fill(page, selectors: List[str], value: str) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.fill(value)
            return True
    return False


def first_click(page, selectors: List[str]) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            return True
    return False


def parse_json_or_text(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def launch_browser(playwright):
    errors: List[str] = []
    # In this environment Chromium can hang intermittently; prefer WebKit first.
    for name in ["webkit", "chromium", "firefox"]:
        try:
            browser_type = getattr(playwright, name)
            browser = browser_type.launch(headless=True, timeout=30000)
            return name, browser
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("unable to launch Playwright browser: " + " | ".join(errors))


def run_playwright_flow(config: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        return {
            "fatal_error": f"playwright import failed: {exc}",
            "checks": [],
            "console_errors": [],
            "request_failures": [],
            "http_errors": [],
        }

    base_url = config["base_url"].rstrip("/")
    bridge_url = config["bridge_url"].rstrip("/")
    project_id = config["project_id"]

    report: Dict[str, Any] = {
        "started_at": datetime.now().isoformat(),
        "base_url": base_url,
        "bridge_url": bridge_url,
        "project_id": project_id,
        "serial": config["serial"],
        "checks": [],
        "console_errors": [],
        "request_failures": [],
        "http_errors": [],
    }

    def add_check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": ok, "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {('- ' + detail) if detail else ''}")

    def resolve_project_id(preferred_project_id: str) -> str:
        api_url = f"{base_url}/motor-qc/api/projects"
        try:
            resp = context.request.get(api_url, timeout=20000)
            if resp.status != 200:
                report["project_api_status"] = resp.status
                return preferred_project_id
            payload = parse_json_or_text(resp.text())
            projects = payload.get("projects") if isinstance(payload, dict) else []
            if not isinstance(projects, list) or not projects:
                return preferred_project_id

            preferred = str(preferred_project_id or "").strip()
            if preferred:
                for item in projects:
                    pid = str((item or {}).get("project_id") or "").strip()
                    name = str((item or {}).get("name") or "").strip()
                    if preferred == pid or preferred == name:
                        return pid or preferred

            first = projects[0] or {}
            first_pid = str(first.get("project_id") or "").strip()
            return first_pid or preferred_project_id
        except Exception:
            return preferred_project_id

    with sync_playwright() as p:
        browser_name, browser = launch_browser(p)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(30000)
        report["browser"] = browser_name

        page.on(
            "console",
            lambda msg: report["console_errors"].append(msg.text)
            if msg.type == "error"
            else None,
        )
        page.on(
            "requestfailed",
            lambda req: report["request_failures"].append(
                {
                    "url": req.url,
                    "method": req.method,
                    "error": (
                        (req.failure.get("errorText") if isinstance(req.failure, dict) else str(req.failure))
                        if req.failure
                        else "unknown"
                    ),
                }
            ),
        )
        page.on(
            "response",
            lambda res: report["http_errors"].append(
                {"url": res.url, "status": res.status, "method": res.request.method}
            )
            if res.status >= 400
            else None,
        )

        try:
            page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=60000)
            user_ok = first_fill(page, ["#username", "input[name='username']"], config["username"])
            pass_ok = first_fill(page, ["#password", "input[name='password']"], config["password"])
            protocol_loc = page.locator("#protocol, select[name='protocol']")
            if protocol_loc.count() > 0:
                protocol_loc.first.select_option(config["protocol"])
            submit_ok = first_click(page, ["button[type='submit']", "button:has-text('登录')"])
            page.wait_for_load_state("networkidle", timeout=60000)
            login_ok = user_ok and pass_ok and submit_ok and ("/login" not in page.url)
            add_check("登录成功", login_ok, f"url={page.url}")
            page.screenshot(path=str(out_dir / "01-after-login.png"), full_page=True)
            if not login_ok:
                return report

            resolved_project_id = resolve_project_id(project_id)
            report["resolved_project_id"] = resolved_project_id
            if resolved_project_id != project_id:
                add_check("项目ID自动回退", True, f"from={project_id}, to={resolved_project_id}")
            encoded_project = quote(resolved_project_id, safe="")
            tasks_url = f"{base_url}/motor-qc/tasks/{encoded_project}?view=edge"
            resp = page.goto(tasks_url, wait_until="domcontentloaded", timeout=60000)
            if not resp or resp.status != 200:
                add_check("任务页边缘模式可访问", False, f"status={resp.status if resp else 0}")
                return report
            current_url = page.url
            if "/motor-qc/tasks/" not in current_url:
                add_check(
                    "任务页边缘模式可访问",
                    False,
                    f"redirected_to={current_url}; likely missing web:run_qc permission",
                )
                return report
            if page.locator("#edge-station-shell").count() == 0:
                add_check("任务页边缘模式可访问", False, "edge shell missing")
                return report
            edge_visible = page.evaluate(
                "() => { const el = document.querySelector('#edge-station-shell'); return !!el && !el.classList.contains('hidden'); }"
            )
            add_check(
                "任务页边缘模式可访问",
                bool(resp and resp.status == 200 and edge_visible),
                f"status={resp.status if resp else 0}, edge_visible={edge_visible}",
            )
            page.screenshot(path=str(out_dir / "02-edge-tasks.png"), full_page=True)
            if not edge_visible:
                return report

            page.fill("#edge-station-id", config["station_id"])
            page.fill("#edge-operator-id", config["operator_id"])
            page.select_option("#edge-camera-source", config["camera_source"])
            page.select_option("#edge-button-source", config["button_source"])
            page.fill("#edge-bridge-url", bridge_url)
            page.fill("#edge-scan-input", config["serial"])
            page.click("#edge-scan-btn")

            page.wait_for_function(
                "() => { const t = (document.querySelector('#edge-session-state')?.textContent || '').trim(); return t === 'RUNNING' || t === 'ERROR'; }",
                timeout=35000,
            )
            session_state = page.inner_text("#edge-session-state").strip()
            hint_text = page.inner_text("#edge-hint").strip() if page.locator("#edge-hint").count() > 0 else ""
            add_check("扫码开始会话", session_state == "RUNNING", f"session_state={session_state}, hint={hint_text}")
            if session_state != "RUNNING":
                return report

            # Ensure bridge button queue works and triggers frontend end flow.
            bridge_press = context.request.post(
                f"{bridge_url}/api/button/press",
                data=json.dumps({"station_id": config["station_id"]}),
                headers={"Content-Type": "application/json"},
                timeout=20000,
            )
            add_check("桥接按钮触发请求成功", bridge_press.status == 200, f"status={bridge_press.status}")

            page.wait_for_function(
                "() => { const t = (document.querySelector('#edge-session-state')?.textContent || '').trim(); return t === 'CLOSED' || t === 'ERROR'; }",
                timeout=60000,
            )
            final_state = page.inner_text("#edge-session-state").strip()
            add_check("按钮结束后会话退出RUNNING", final_state in {"CLOSED", "ERROR"}, f"state={final_state}")

            timeline = page.eval_on_selector_all(
                "#edge-timeline .edge-timeline-item",
                "els => els.map((el) => el.innerText || '')",
            )
            has_button_end = any("BUTTON_END" in row for row in timeline)
            has_final = any(("FINAL_UPLOAD" in row) or ("FINAL_UPLOAD_FAIL" in row) or ("SESSION_END" in row) for row in timeline)
            add_check("时间线包含按钮结束事件", has_button_end, f"events={len(timeline)}")
            add_check("时间线包含最终上传结果", has_final, f"events={len(timeline)}")
            page.screenshot(path=str(out_dir / "03-after-end.png"), full_page=True)

            review_url = f"{base_url}/motor-qc/review/{encoded_project}"
            page.goto(review_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#task-filter-status", timeout=20000)
            status_value = page.input_value("#task-filter-status")
            status_disabled = page.evaluate("() => !!document.querySelector('#task-filter-status')?.disabled")
            ai_filter_exists = page.locator("#task-filter-ai").count() > 0
            add_check("人工确认页可访问", True, f"url={page.url}")
            add_check("人工确认页状态固定review", status_value == "review" and status_disabled, f"value={status_value}, disabled={status_disabled}")
            add_check("人工确认页AI筛选可见", ai_filter_exists, "")

            page.click("#task-reset-btn")
            page.wait_for_timeout(500)
            reset_status_value = page.input_value("#task-filter-status")
            add_check("人工确认页重置后仍保持review", reset_status_value == "review", f"value={reset_status_value}")
            page.screenshot(path=str(out_dir / "04-review-page.png"), full_page=True)

            tasks_api = context.request.get(
                f"{base_url}/motor-qc/api/projects/{encoded_project}/tasks?serial={quote(config['serial'], safe='')}&include_children=1&per_page=20&page=1&seed_if_empty=0",
                timeout=30000,
            )
            task_payload = parse_json_or_text(tasks_api.text())
            task_count = -1
            if isinstance(task_payload, dict):
                task_count = len(task_payload.get("tasks") or [])
            add_check("任务API可访问", tasks_api.status == 200, f"status={tasks_api.status}, tasks={task_count}")
        except Exception as exc:
            add_check("自动化流程异常", False, str(exc))
        finally:
            report["finished_at"] = datetime.now().isoformat()
            report["passed"] = sum(1 for c in report["checks"] if c.get("ok"))
            report["failed"] = sum(1 for c in report["checks"] if not c.get("ok"))
            try:
                page.screenshot(path=str(out_dir / "99-final.png"), full_page=True)
            except Exception:
                pass
            browser.close()

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local edge frontend regression")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8891"))
    parser.add_argument("--bridge-url", default=os.getenv("EDGE_BRIDGE_URL", "http://127.0.0.1:19091"))
    parser.add_argument("--project-id", default=os.getenv("MOTOR_QC_PROJECT", "柳工3.5T双12叉车"))
    parser.add_argument("--serial", default=os.getenv("EDGE_SERIAL", f"EDGE{datetime.now().strftime('%m%d%H%M%S')}"))
    parser.add_argument("--station-id", default=os.getenv("EDGE_STATION_ID", "S01"))
    parser.add_argument("--operator-id", default=os.getenv("EDGE_OPERATOR_ID", "edge-op"))
    parser.add_argument("--username", default=os.getenv("MES_USER", "zhiqiang.zhu"))
    parser.add_argument("--password", default=os.getenv("MES_PASS", "Clt@123456"))
    parser.add_argument("--protocol", default=os.getenv("MES_PROTOCOL", "smb"))
    parser.add_argument("--camera-source", choices=["browser", "local_bridge", "mock"], default=os.getenv("EDGE_CAMERA_SOURCE", "local_bridge"))
    parser.add_argument("--button-source", choices=["manual", "local_bridge", "keyboard"], default=os.getenv("EDGE_BUTTON_SOURCE", "local_bridge"))
    parser.add_argument("--mes-start-timeout", type=float, default=45.0)
    parser.add_argument("--bridge-start-timeout", type=float, default=12.0)
    parser.add_argument("--no-auto-start", action="store_true", help="Do not auto start local services")
    args = parser.parse_args()

    ts = now_ts()
    out_dir = OUTPUT_ROOT / f"edge-local-regression-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    mes_health = f"{args.base_url.rstrip('/')}/motor-qc/api/health"
    bridge_health = f"{args.bridge_url.rstrip('/')}/api/health"

    started: List[ManagedProc] = []
    bootstrap: Dict[str, Any] = {
        "mes_health": mes_health,
        "bridge_health": bridge_health,
        "mes_reused": False,
        "bridge_reused": False,
        "started_processes": [],
    }

    try:
        if is_http_ok(mes_health):
            bootstrap["mes_reused"] = True
            print(f"[INFO] Reusing MES service: {mes_health}")
        elif args.no_auto_start:
            print(f"[ERROR] MES service not reachable: {mes_health}")
            return 2
        else:
            log_file = out_dir / "mesapp.log"
            proc = start_process("mesapp", ["python3", "mesapp.py"], APP_WEB_DIR, log_file)
            started.append(proc)
            bootstrap["started_processes"].append({"name": proc.name, "pid": proc.popen.pid, "log": str(proc.log_file)})
            if not wait_http_ok(mes_health, timeout=args.mes_start_timeout):
                print(f"[ERROR] MES service start timeout. See log: {log_file}")
                return 2
            print(f"[INFO] MES service started: pid={proc.popen.pid}")

        if is_http_ok(bridge_health):
            bootstrap["bridge_reused"] = True
            print(f"[INFO] Reusing bridge stub: {bridge_health}")
        elif args.no_auto_start:
            print(f"[ERROR] Bridge service not reachable: {bridge_health}")
            return 2
        else:
            log_file = out_dir / "edge-bridge.log"
            proc = start_process(
                "edge_bridge_stub",
                ["python3", str(REPO_ROOT / "scripts" / "edge_local_bridge_stub.py"), "--host", "127.0.0.1", "--port", "19091"],
                REPO_ROOT,
                log_file,
            )
            started.append(proc)
            bootstrap["started_processes"].append({"name": proc.name, "pid": proc.popen.pid, "log": str(proc.log_file)})
            if not wait_http_ok(bridge_health, timeout=args.bridge_start_timeout):
                print(f"[ERROR] Bridge stub start timeout. See log: {log_file}")
                return 2
            print(f"[INFO] Bridge stub started: pid={proc.popen.pid}")

        flow_config = {
            "base_url": args.base_url,
            "bridge_url": args.bridge_url,
            "project_id": args.project_id,
            "serial": args.serial,
            "station_id": args.station_id,
            "operator_id": args.operator_id,
            "username": args.username,
            "password": args.password,
            "protocol": args.protocol,
            "camera_source": args.camera_source,
            "button_source": args.button_source,
        }
        report = run_playwright_flow(flow_config, out_dir)
        report["bootstrap"] = bootstrap
        report_path = out_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"REPORT_FILE={report_path}")

        failed = int(report.get("failed") or 0)
        if report.get("fatal_error"):
            print(f"[ERROR] {report['fatal_error']}")
            return 3
        return 0 if failed == 0 else 1
    finally:
        for proc in reversed(started):
            stop_process(proc)


if __name__ == "__main__":
    raise SystemExit(main())
