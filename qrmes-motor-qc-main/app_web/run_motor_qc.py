from flask import Flask
from motor_qc import motor_qc_bp
from motor_qc.models import db

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = 'motor-qc-split-dev'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///motor_qc.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(motor_qc_bp)
    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9002, debug=False)
