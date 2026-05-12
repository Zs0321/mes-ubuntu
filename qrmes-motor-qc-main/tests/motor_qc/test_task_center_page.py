def test_task_center_route_requires_permission(app, client_user):
    if "login" not in app.view_functions:
        app.add_url_rule("/login", "login", lambda: "login")
    if "index" not in app.view_functions:
        app.add_url_rule("/", "index", lambda: "index")
    resp = client_user.get("/motor-qc/tasks/test-project")
    assert resp.status_code in (302, 403)


def test_task_center_route_renders_for_admin(app, client_admin, monkeypatch):
    from app_web.motor_qc import routes as motor_routes

    monkeypatch.setattr(
        motor_routes.motor_project_manager,
        "load_project",
        lambda project_id: {
            "project_id": project_id,
            "name": "测试项目",
            "processes": [],
        },
    )
    monkeypatch.setattr(motor_routes, "render_template", lambda *_args, **_kwargs: "ok")

    resp = client_admin.get("/motor-qc/tasks/test-project")
    assert resp.status_code == 200
    assert resp.data == b"ok"
