import requests
import json
from config import Config
import time

class PistonAPI:
    """
    A utility class for interacting with the Piston API to run code in various languages.
    Piston API docs: https://github.com/engineer-man/piston
    """
    
    @staticmethod
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
        
        language_config = Config.SUPPORTED_LANGUAGES[language]
        
        url = f"{Config.PISTON_API_URL}/execute"
        
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
            "compile_timeout": 10000,
            "run_timeout": 3000,
            "compile_memory_limit": -1,
            "run_memory_limit": -1
        }
        
        try:
            start_time = time.time()
            response = requests.post(url, json=payload)
            end_time = time.time()
            execution_time = end_time - start_time
            
            if response.status_code == 200:
                result = response.json()
                result['execution_time'] = execution_time
                result['success'] = True
                return result
            else:
                return {
                    'success': False,
                    'error': f'API error: {response.status_code} - {response.text}'
                }
        except Exception as e:
            return {
                'success': False,
                'error': f'Request error: {str(e)}'
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
        
        passed = actual_output == expected_output and not error_output
        
        return {
            'passed': passed,
            'output': actual_output,
            'error': error_output,
            'execution_time': result.get('execution_time', 0)
        }

def get_filename_for_language(language):
    """Return appropriate filename for the given language"""
    extensions = {
        'python': 'main.py',
        'c': 'main.c',
        'java': 'Main.java',
        # Add more languages as needed
    }
    return extensions.get(language, f'main.{language}')

def format_time_remaining(seconds):
    """Format time remaining in minutes and seconds"""
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"
