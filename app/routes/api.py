from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime

from models import Submission
from utils import PistonAPI

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/run-code', methods=['POST'])
@login_required
def run_code():
    data = request.get_json()
    
    if not data or 'code' not in data or 'language' not in data:
        return jsonify({'error': 'Invalid request data'}), 400
    
    code = data.get('code')
    language = data.get('language')
    stdin = data.get('stdin', '')
    
    result = PistonAPI.execute_code(language, code, stdin)
    
    return jsonify(result)

@api_bp.route('/time-remaining/<int:submission_id>', methods=['GET'])
@login_required
def time_remaining(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    
    if submission.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if submission.is_completed:
        return jsonify({'timeRemaining': 0, 'formatted': '00:00'})
    
    from utils import format_time_remaining
    
    time_limit_seconds = submission.quiz.time_limit * 60
    elapsed_seconds = (datetime.utcnow() - submission.started_at).total_seconds()
    time_remaining = max(0, time_limit_seconds - elapsed_seconds)
    
    return jsonify({
        'timeRemaining': int(time_remaining),
        'formatted': format_time_remaining(time_remaining)
    })
