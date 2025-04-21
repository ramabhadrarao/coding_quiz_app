import os
from flask import Flask
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from models import db, User

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Add ProxyFix for proper handling of X-Forwarded-For, X-Forwarded-Proto headers
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Configuration for file uploads
    UPLOAD_FOLDER = os.path.join(app.root_path, 'static/uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max upload size

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

    # Create uploads directory if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Initialize database
    db.init_app(app)

    # Initialize login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'danger'  # Bootstrap alert style
    login_manager.session_protection = 'strong'  # Stronger session protection

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.student import student_bp
    from app.routes.api import api_bp
    from app.routes.main import main_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(main_bp)

    # Register error handlers
    register_error_handlers(app)

    return app

def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        db.session.rollback()
        return render_template('errors/500.html'), 500