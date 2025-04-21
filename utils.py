import requests
import json
import time
import logging
import os
import bleach
from functools import lru_cache
import secrets
from datetime import datetime, timedelta

# Import configuration 
from config import Config

logger = logging.getLogger(__name__)

class PistonAPI:
    """
    A utility class for interacting with the Piston API to run code in various languages.
    Piston API docs: https://github.com/engineer-man/piston
    
    This enhanced version includes:
    - Better error handling
    - Timeouts and retries
    - Input sanitization
    - Response caching
    - Rate limiting
    """
    
    # Track API calls to implement rate limiting
    _api_calls = {}
    _rate_limit = 60  # calls per minute
    
    @classmethod
    def _check_rate_limit(cls, key='default'):
        """Check if we've hit the rate limit"""
        now = time.time()
        
        # Initialize or clean old data
        if key not in cls._api_calls:
            cls._api_calls[key] = []
        else:
            # Remove calls older than 1 minute
            cls._api_calls[key] = [t for t in cls._api_calls[key] if t > now - 60]
        
        # Check if under rate limit
        if len(cls._api_calls[key]) < cls._rate_limit:
            cls._api_calls[key].append(now)
            return True
        
        return False
    
    @staticmethod
    @lru_cache(maxsize=128)  # Cache results for identical inputs
    def execute_code(language, code, stdin=""):
        """
        Execute code using the Piston API
        
        Args:
            language (str): Programming language (python, c, java, etc.)
            code (str): Source code to execute
            stdin (str): Input to pass to the program
            
        Returns:
            dict: API response containing execution results
        """
        if language not in Config.SUPPORTED_LANGUAGES:
            return {
                'success': False,
                'error': f'Language {language} is not supported'
            }
        
        # Check rate limit
        if not PistonAPI._check_rate_limit(language):
            return {
                'success': False,
                'error': 'Rate limit exceeded. Please try again later.'
            }
        
        language_config = Config.SUPPORTED_LANGUAGES[language]
        
        url = f"{Config.PISTON_API_URL}/execute"
        
        # Sanitize stdin to prevent injection
        stdin = bleach.clean(stdin) if stdin else ""
        
        payload = {
            "language": language,
            "version": language_config['version'],
            "files": [
                {
                    "name": get_filename_for_language(language),
                    "content": code
                }
            ],
            "stdin": stdin,
            "args": [],
            "compile_timeout": Config.CODE_COMPILE_TIMEOUT * 1000,  # convert to ms
            "run_timeout": Config.CODE_EXECUTION_TIMEOUT * 1000,    # convert to ms
            "compile_memory_limit": -1,
            "run_memory_limit": -1
        }
        
        try:
            start_time = time.time()
            
            # Make request with timeout
            timeout = Config.PISTON_API_TIMEOUT
            response = requests.post(url, json=payload, timeout=timeout)
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            if response.status_code == 200:
                result = response.json()
                result['execution_time'] = execution_time
                result['success'] = True
                
                # Check for execution errors
                if 'run' in result and 'code' in result['run'] and result['run']['code'] != 0:
                    # Program executed but with non-zero exit code
                    logger.warning(f"Code execution returned non-zero exit code: {result['run']['code']}")
                
                return result
            else:
                error_msg = f'API error: {response.status_code}'
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg = f"API error: {error_data['message']}"
                except:
                    pass
                
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except requests.exceptions.Timeout:
            logger.error(f"API timeout while executing {language} code")
            return {
                'success': False,
                'error': 'API request timed out'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            return {
                'success': False,
                'error': f'Request error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error executing code: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    @staticmethod
    def run_test_case(language, code, test_case):
        """
        Run a test case against provided code
        
        Args:
            language (str): Programming language
            code (str): Source code
            test_case (TestCase): Test case model instance
            
        Returns:
            dict: Test execution result
        """
        # Validate inputs
        if not code or not language:
            return {
                'passed': False,
                'output': None,
                'error': 'Invalid code or language',
                'execution_time': 0
            }
        
        result = PistonAPI.execute_code(language, code, test_case.input_data or "")
        
        if not result['success']:
            return {
                'passed': False,
                'output': None,
                'error': result.get('error', 'Unknown error'),
                'execution_time': 0
            }
        
        # Clean output (remove trailing newlines)
        expected_output = test_case.expected_output.strip()
        actual_output = result.get('run', {}).get('stdout', '').strip()
        error_output = result.get('run', {}).get('stderr', '')
        
        # Check for compilation error
        if result.get('compile', {}).get('stderr'):
            return {
                'passed': False,
                'output': None,
                'error': result['compile']['stderr'],
                'execution_time': result.get('execution_time', 0),
                'compile_error': True
            }
        
        # Check for runtime error (non-zero exit code)
        if result.get('run', {}).get('code', 0) != 0:
            return {
                'passed': False,
                'output': actual_output,
                'error': error_output or f"Program exited with code {result['run']['code']}",
                'execution_time': result.get('execution_time', 0),
                'runtime_error': True
            }
        
        passed = actual_output == expected_output and not error_output
        
        return {
            'passed': passed,
            'output': actual_output,
            'error': error_output,
            'execution_time': result.get('execution_time', 0)
        }

def get_filename_for_language(language):
    """Return appropriate filename for the given language"""
    language_config = Config.SUPPORTED_LANGUAGES.get(language, {})
    
    # Use configured file extension if available
    if 'file_extension' in language_config:
        return f"main{language_config['file_extension']}"
    
    # Fallback to default extensions
    extensions = {
        'python': 'main.py',
        'c': 'main.c',
        'java': 'Main.java',
        'javascript': 'main.js',
        'typescript': 'main.ts',
        'rust': 'main.rs',
        'go': 'main.go',
    }
    
    return extensions.get(language, f'main.{language}')

def format_time_remaining(seconds):
    """Format time remaining in minutes and seconds"""
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"

def sanitize_html(html_content):
    """Sanitize HTML content to prevent XSS attacks"""
    allowed_tags = [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'span', 'div', 'ul', 'ol', 
        'li', 'strong', 'em', 'code', 'pre', 'blockquote', 'table', 'thead', 
        'tbody', 'tr', 'th', 'td', 'img', 'br', 'hr', 'sup', 'sub'
    ]
    allowed_attrs = {
        '*': ['class', 'style'],
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'width', 'height'],
    }
    
    return bleach.clean(
        html_content, 
        tags=allowed_tags, 
        attributes=allowed_attrs, 
        strip=True
    )

def is_valid_markdown(text):
    """Check if a string contains valid markdown"""
    if not text:
        return False
    
    # Basic check for markdown syntax
    markdown_indicators = ['#', '##', '*', '1.', '```', '>', '[', '![', '|']
    
    # Check if any markdown indicators are present
    for indicator in markdown_indicators:
        if indicator in text:
            return True
    
    return False

def secure_filename_with_salt(filename):
    """Generate a secure filename with a salt and timestamp"""
    if not filename:
        return None
    
    from werkzeug.utils import secure_filename
    
    _, ext = os.path.splitext(secure_filename(filename))
    salt = secrets.token_hex(8)
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    return f"{timestamp}_{salt}{ext}"