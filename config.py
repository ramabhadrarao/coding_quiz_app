import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///coding_quiz.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Piston API settings
    PISTON_API_URL = os.environ.get('PISTON_API_URL') or 'https://emkc.org/api/v2/piston'
    
    # Supported programming languages
    SUPPORTED_LANGUAGES = {
        'python': {
            'name': 'Python',
            'version': '3.10',
            'mode': 'python',
        },
        'c': {
            'name': 'C',
            'version': 'gcc-11.2.0',
            'mode': 'c',
        },
        'java': {
            'name': 'Java',
            'version': '17',
            'mode': 'java',
        }
    }
    
    # Quiz settings
    DEFAULT_TIME_LIMIT = 30  # minutes
