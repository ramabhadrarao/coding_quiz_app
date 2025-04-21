import os
from dotenv import load_dotenv
import secrets

# Load environment variables from .env file
load_dotenv()

class Config:
    # Generate a secure SECRET_KEY if not provided
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///coding_quiz.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Security settings
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = 2592000  # 30 days in seconds
    REMEMBER_COOKIE_SECURE = os.environ.get('REMEMBER_COOKIE_SECURE', 'False').lower() == 'true'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    
    # CSRF protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour in seconds
    
    # File upload settings
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max upload size
    UPLOAD_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif']
    
    # Logging configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Piston API settings
    PISTON_API_URL = os.environ.get('PISTON_API_URL') or 'https://emkc.org/api/v2/piston'
    PISTON_API_TIMEOUT = int(os.environ.get('PISTON_API_TIMEOUT', 10))  # 10 seconds timeout
    
    # Code execution time limits (seconds)
    CODE_EXECUTION_TIMEOUT = int(os.environ.get('CODE_EXECUTION_TIMEOUT', 3))  
    CODE_COMPILE_TIMEOUT = int(os.environ.get('CODE_COMPILE_TIMEOUT', 5))
    
    # Supported programming languages with version and editor mode
    SUPPORTED_LANGUAGES = {
        'python': {
            'name': 'Python',
            'version': '3.10',
            'mode': 'python',
            'file_extension': '.py'
        },
        'c': {
            'name': 'C',
            'version': 'gcc-11.2.0',
            'mode': 'c',
            'file_extension': '.c'
        },
        'java': {
            'name': 'Java',
            'version': '17',
            'mode': 'java',
            'file_extension': '.java'
        },
        'javascript': {
            'name': 'JavaScript',
            'version': 'node-18.12.1',
            'mode': 'javascript',
            'file_extension': '.js'
        },
        'rust': {
            'name': 'Rust',
            'version': '1.65.0',
            'mode': 'rust',
            'file_extension': '.rs'
        }
    }
    
    # Quiz settings
    DEFAULT_TIME_LIMIT = 30  # minutes
    MAX_TIME_LIMIT = 180  # maximum time limit in minutes
    
    # Rate limiting settings
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL') or "memory://"
    
    # Cache settings (if using Redis)
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache')
    CACHE_REDIS_URL = os.environ.get('REDIS_URL')
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes
    
    # Development settings
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = os.environ.get('FLASK_TESTING', 'False').lower() == 'true'
    
    @staticmethod
    def init_app(app):
        """Initialize application with extended settings"""
        pass


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Log to console in development
        import logging
        from logging import StreamHandler
        file_handler = StreamHandler()
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)


class ProductionConfig(Config):
    """Production configuration"""
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Log to file in production
        import logging
        from logging.handlers import RotatingFileHandler
        import os
        
        if not os.path.exists('logs'):
            os.mkdir('logs')
            
        file_handler = RotatingFileHandler('logs/coding_quiz.log', 
                                          maxBytes=10485760, # 10MB
                                          backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Application configurations
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

# Use configuration based on environment
config_name = os.environ.get('FLASK_CONFIG', 'default')
active_config = config[config_name]