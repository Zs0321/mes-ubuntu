from flask import Flask, redirect, request, session, url_for

try:
    from .finance_demo import finance_demo_bp
except ImportError:  # pragma: no cover
    from finance_demo import finance_demo_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = 'finance-demo-split-dev'
    app.register_blueprint(finance_demo_bp)

    @app.route('/login', methods=['GET'])
    def login():
        next_url = request.args.get('next') or '/finance-demo/'
        session['user'] = {
            'id': 'local-finance-demo',
            'username': 'local-finance-demo',
            'display_name': '本地报价调试',
            'role': 'admin',
            'must_change_password': False,
            'is_active': True,
        }
        return redirect(next_url)

    @app.route('/')
    def index():
        return redirect('/finance-demo/')

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9003, debug=False)
