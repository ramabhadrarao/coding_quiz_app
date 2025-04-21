import os
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.urls import url_parse
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta
import json
import secrets
from functools import wraps

from config import Config
from models import db, User, Quiz, Question, TestCase, Submission, QuestionSubmission, TestResult, QuestionOption, SelectedOption
from forms import (LoginForm, RegistrationForm, QuizForm, CodeQuestionForm,  # Changed from QuestionForm
                  TestCaseForm, MultipleChoiceQuestionForm,
                  TrueFalseQuestionForm, CodeSubmissionForm,
                  MultipleChoiceSubmissionForm, TrueFalseSubmissionForm,
                  OptionForm)
from utils import PistonAPI, format_time_remaining

app = Flask(__name__)
app.config.from_object(Config)

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database
db.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'danger'  # Bootstrap alert style
login_manager.session_protection = 'strong'  # Stronger session protection

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Helper function to check admin status
def admin_required(func):
    @login_required
    def decorated_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return func(*args, **kwargs)
    decorated_view.__name__ = func.__name__
    return decorated_view

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
        
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    
    return render_template('login.html', form=form, title='Sign In')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form, title='Register')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# Admin routes
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    quizzes = Quiz.query.filter_by(author_id=current_user.id).all()
    recent_submissions = Submission.query.filter(
        Submission.quiz_id.in_([q.id for q in quizzes])
    ).order_by(Submission.completed_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html', 
                          quizzes=quizzes, 
                          recent_submissions=recent_submissions,
                          title='Admin Dashboard')

@app.route('/admin/quizzes', methods=['GET'])
@admin_required
def admin_quizzes():
    quizzes = Quiz.query.filter_by(author_id=current_user.id).all()
    return render_template('admin/quizzes.html', quizzes=quizzes, title='Manage Quizzes')

@app.route('/admin/quizzes/new', methods=['GET', 'POST'])
@admin_required
def create_quiz():
    form = QuizForm()
    if form.validate_on_submit():
        quiz = Quiz(
            title=form.title.data,
            description=form.description.data,
            time_limit=form.time_limit.data,
            is_active=form.is_active.data,
            author_id=current_user.id
        )
        db.session.add(quiz)
        db.session.commit()
        flash('Quiz created successfully!', 'success')
        return redirect(url_for('edit_quiz', quiz_id=quiz.id))
    
    return render_template('admin/quiz_form.html', form=form, title='Create Quiz')

@app.route('/admin/quizzes/<int:quiz_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    form = QuizForm(obj=quiz)
    if form.validate_on_submit():
        quiz.title = form.title.data
        quiz.description = form.description.data
        quiz.time_limit = form.time_limit.data
        quiz.is_active = form.is_active.data
        quiz.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Quiz updated successfully!', 'success')
        return redirect(url_for('admin_quizzes'))
    
    questions = quiz.questions.order_by(Question.order).all()
    return render_template('admin/quiz_form.html', 
                          form=form, 
                          quiz=quiz, 
                          questions=questions,
                          title='Edit Quiz')

@app.route('/admin/quizzes/<int:quiz_id>/delete', methods=['POST'])
@admin_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    db.session.delete(quiz)
    db.session.commit()
    flash('Quiz deleted successfully!', 'success')
    return redirect(url_for('admin_quizzes'))

# Question type selector route
@app.route('/admin/quizzes/<int:quiz_id>/questions/select-type', methods=['GET'])
@admin_required
def select_question_type(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    return render_template('admin/question_type_selector.html', quiz=quiz, title='Select Question Type')

# Code Question Routes
@app.route('/admin/quizzes/<int:quiz_id>/questions/code/new', methods=['GET', 'POST'])
@admin_required
def create_code_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    form = CodeQuestionForm()
    if form.validate_on_submit():
        question = Question(
            quiz_id=quiz_id,
            title=form.title.data,
            description=form.description.data,
            problem_statement=form.problem_statement.data,
            starter_code=form.starter_code.data,
            language=form.language.data,
            question_type='code',
            points=form.points.data,
            order=form.order.data
        )
        db.session.add(question)
        db.session.commit()
        flash('Code question created successfully!', 'success')
        return redirect(url_for('edit_question', quiz_id=quiz_id, question_id=question.id))
    
    # Default values for new question
    form.order.data = quiz.questions.count() + 1
    form.points.data = 10
    
    return render_template('admin/question_form.html', 
                          form=form, 
                          quiz=quiz,
                          title='Create Code Question')

@app.route('/admin/quizzes/<int:quiz_id>/questions/<int:question_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_question(quiz_id, question_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id:
        abort(403)
    
    # Route based on question type
    if question.question_type == 'multiple_choice':
        return redirect(url_for('edit_multiple_choice_question', quiz_id=quiz_id, question_id=question_id))
    elif question.question_type == 'true_false':
        return redirect(url_for('edit_true_false_question', quiz_id=quiz_id, question_id=question_id))
    elif question.question_type == 'code' or not question.question_type:  # Default to code for backward compatibility
        form = QuestionForm(obj=question)
        if form.validate_on_submit():
            question.title = form.title.data
            question.description = form.description.data
            question.problem_statement = form.problem_statement.data
            question.starter_code = form.starter_code.data
            question.language = form.language.data
            question.points = form.points.data
            question.order = form.order.data
            question.question_type = 'code'  # Ensure type is set
            
            db.session.commit()
            flash('Question updated successfully!', 'success')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
        
        test_cases = question.test_cases.order_by(TestCase.order).all()
        return render_template('admin/question_form.html', 
                            form=form, 
                            quiz=quiz, 
                            question=question,
                            test_cases=test_cases,
                            title='Edit Question')

@app.route('/admin/quizzes/<int:quiz_id>/questions/<int:question_id>/delete', methods=['POST'])
@admin_required
def delete_question(quiz_id, question_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id:
        abort(403)
    
    db.session.delete(question)
    db.session.commit()
    flash('Question deleted successfully!', 'success')
    return redirect(url_for('edit_quiz', quiz_id=quiz_id))

# Multiple Choice Question Routes
@app.route('/admin/quizzes/<int:quiz_id>/questions/multiple-choice/new', methods=['GET', 'POST'])
@admin_required
def create_multiple_choice_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    form = MultipleChoiceQuestionForm()
    if form.validate_on_submit():
        # Create the question
        question = Question(
            quiz_id=quiz_id,
            title=form.title.data,
            description=form.description.data,
            problem_statement=form.problem_statement.data,
            question_type='multiple_choice',
            points=form.points.data,
            order=form.order.data
        )
        db.session.add(question)
        db.session.flush()  # Get the question ID without committing
        
        # Process options
        for i, option_form in enumerate(form.options):
            # Handle image upload
            image_path = None
            if 'options-{}-image'.format(i) in request.files:
                file = request.files['options-{}-image'.format(i)]
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Create unique filename with timestamp
                    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    image_path = filename
            
            # Create option
            option = QuestionOption(
                question_id=question.id,
                text=option_form.text.data,
                is_correct=option_form.is_correct.data,
                order=option_form.order.data,
                image_path=image_path
            )
            db.session.add(option)
        
        db.session.commit()
        flash('Multiple choice question created successfully!', 'success')
        return redirect(url_for('edit_quiz', quiz_id=quiz_id))
    
    # Default values for new question
    form.order.data = quiz.questions.count() + 1
    form.points.data = 10
    
    return render_template('admin/multiple_choice_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          title='Create Multiple Choice Question')

@app.route('/admin/quizzes/<int:quiz_id>/questions/<int:question_id>/multiple-choice/edit', methods=['GET', 'POST'])
@admin_required
def edit_multiple_choice_question(quiz_id, question_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id:
        abort(403)
    
    if question.question_type != 'multiple_choice':
        abort(400)
    
    form = MultipleChoiceQuestionForm(obj=question)
    
    # Pre-populate options
    if request.method == 'GET':
        form.options = []
        for option in question.options.order_by(QuestionOption.order).all():
            option_form = OptionForm()
            option_form.text.data = option.text
            option_form.is_correct.data = option.is_correct
            option_form.order.data = option.order
            # We don't pre-populate the image field
            form.options.append(option_form)
    
    if form.validate_on_submit():
        # Update question
        question.title = form.title.data
        question.description = form.description.data
        question.problem_statement = form.problem_statement.data
        question.points = form.points.data
        question.order = form.order.data
        
        # Delete existing options
        for option in question.options.all():
            db.session.delete(option)
        
        # Process options
        for i, option_form in enumerate(form.options):
            # Handle image upload
            image_path = None
            if 'options-{}-image'.format(i) in request.files:
                file = request.files['options-{}-image'.format(i)]
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Create unique filename with timestamp
                    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    image_path = filename
            
            # Create option
            option = QuestionOption(
                question_id=question.id,
                text=option_form.text.data,
                is_correct=option_form.is_correct.data,
                order=option_form.order.data,
                image_path=image_path
            )
            db.session.add(option)
        
        db.session.commit()
        flash('Multiple choice question updated successfully!', 'success')
        return redirect(url_for('edit_quiz', quiz_id=quiz_id))
    
    return render_template('admin/multiple_choice_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          title='Edit Multiple Choice Question')

# True/False Question Routes
@app.route('/admin/quizzes/<int:quiz_id>/questions/true-false/new', methods=['GET', 'POST'])
@admin_required
def create_true_false_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    form = TrueFalseQuestionForm()
    if form.validate_on_submit():
        # Create the question
        question = Question(
            quiz_id=quiz_id,
            title=form.title.data,
            description=form.description.data,
            problem_statement=form.problem_statement.data,
            question_type='true_false',
            points=form.points.data,
            order=form.order.data
        )
        db.session.add(question)
        db.session.flush()  # Get the question ID without committing
        
        # Create true option
        true_option = QuestionOption(
            question_id=question.id,
            text='True',
            is_correct=(form.correct_answer.data == 'true'),
            order=0
        )
        db.session.add(true_option)
        
        # Create false option
        false_option = QuestionOption(
            question_id=question.id,
            text='False',
            is_correct=(form.correct_answer.data == 'false'),
            order=1
        )
        db.session.add(false_option)
        
        db.session.commit()
        flash('True/False question created successfully!', 'success')
        return redirect(url_for('edit_quiz', quiz_id=quiz_id))
    
    # Default values for new question
    form.order.data = quiz.questions.count() + 1
    form.points.data = 5
    
    return render_template('admin/true_false_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          title='Create True/False Question')

@app.route('/admin/quizzes/<int:quiz_id>/questions/<int:question_id>/true-false/edit', methods=['GET', 'POST'])
@admin_required
def edit_true_false_question(quiz_id, question_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id:
        abort(403)
    
    if question.question_type != 'true_false':
        abort(400)
    
    form = TrueFalseQuestionForm(obj=question)
    
    # Pre-populate correct answer
    if request.method == 'GET':
        true_option = question.options.filter_by(text='True').first()
        if true_option and true_option.is_correct:
            form.correct_answer.data = 'true'
        else:
            form.correct_answer.data = 'false'
    
    if form.validate_on_submit():
        # Update question
        question.title = form.title.data
        question.description = form.description.data
        question.problem_statement = form.problem_statement.data
        question.points = form.points.data
        question.order = form.order.data
        
        # Update options
        true_option = question.options.filter_by(text='True').first()
        false_option = question.options.filter_by(text='False').first()
        
        if true_option:
            true_option.is_correct = (form.correct_answer.data == 'true')
        else:
            true_option = QuestionOption(
                question_id=question.id,
                text='True',
                is_correct=(form.correct_answer.data == 'true'),
                order=0
            )
            db.session.add(true_option)
        
        if false_option:
            false_option.is_correct = (form.correct_answer.data == 'false')
        else:
            false_option = QuestionOption(
                question_id=question.id,
                text='False',
                is_correct=(form.correct_answer.data == 'false'),
                order=1
            )
            db.session.add(false_option)
        
        db.session.commit()
        flash('True/False question updated successfully!', 'success')
        return redirect(url_for('edit_quiz', quiz_id=quiz_id))
    
    return render_template('admin/true_false_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          title='Edit True/False Question')
@app.route('/admin/quizzes/<int:quiz_id>/questions/new', methods=['GET', 'POST'])
@admin_required
def create_question(quiz_id):
    # Redirect to question type selector
    return redirect(url_for('select_question_type', quiz_id=quiz_id))

@app.route('/admin/quizzes/<int:quiz_id>/questions/<int:question_id>/test-cases/new', methods=['GET', 'POST'])
@admin_required
def create_test_case(quiz_id, question_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id:
        abort(403)
    
    form = TestCaseForm()
    if form.validate_on_submit():
        test_case = TestCase(
            question_id=question_id,
            input_data=form.input_data.data,
            expected_output=form.expected_output.data,
            is_hidden=form.is_hidden.data,
            order=form.order.data
        )
        db.session.add(test_case)
        db.session.commit()
        flash('Test case created successfully!', 'success')
        return redirect(url_for('edit_question', quiz_id=quiz_id, question_id=question_id))
    
    # Default values for new test case
    form.order.data = question.test_cases.count() + 1
    
    return render_template('admin/test_case_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          title='Create Test Case')

@app.route('/admin/quizzes/<int:quiz_id>/questions/<int:question_id>/test-cases/<int:test_case_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_test_case(quiz_id, question_id, test_case_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    test_case = TestCase.query.get_or_404(test_case_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id or test_case.question_id != question_id:
        abort(403)
    
    form = TestCaseForm(obj=test_case)
    if form.validate_on_submit():
        test_case.input_data = form.input_data.data
        test_case.expected_output = form.expected_output.data
        test_case.is_hidden = form.is_hidden.data
        test_case.order = form.order.data
        
        db.session.commit()
        flash('Test case updated successfully!', 'success')
        return redirect(url_for('edit_question', quiz_id=quiz_id, question_id=question_id))
    
    return render_template('admin/test_case_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          test_case=test_case,
                          title='Edit Test Case')

@app.route('/admin/quizzes/<int:quiz_id>/questions/<int:question_id>/test-cases/<int:test_case_id>/delete', methods=['POST'])
@admin_required
def delete_test_case(quiz_id, question_id, test_case_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    test_case = TestCase.query.get_or_404(test_case_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id or test_case.question_id != question_id:
        abort(403)
    
    db.session.delete(test_case)
    db.session.commit()
    flash('Test case deleted successfully!', 'success')
    return redirect(url_for('edit_question', quiz_id=quiz_id, question_id=question_id))

@app.route('/admin/results')
@admin_required
def admin_results():
    quizzes = Quiz.query.filter_by(author_id=current_user.id).all()
    submissions = Submission.query.filter(
        Submission.quiz_id.in_([q.id for q in quizzes])
    ).order_by(Submission.completed_at.desc()).all()
    
    return render_template('admin/results.html', 
                          submissions=submissions,
                          title='Quiz Results')

@app.route('/admin/submission/<int:submission_id>')
@admin_required
def admin_view_submission(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    quiz = Quiz.query.get_or_404(submission.quiz_id)
    
    if quiz.author_id != current_user.id:
        abort(403)
    
    question_submissions = submission.question_submissions.all()
    
    return render_template('admin/submission_detail.html',
                          submission=submission,
                          quiz=quiz,
                          question_submissions=question_submissions,
                          title='Submission Details')
# Student routes
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    active_quizzes = Quiz.query.filter_by(is_active=True).all()
    my_submissions = Submission.query.filter_by(user_id=current_user.id).order_by(Submission.started_at.desc()).all()
    
    # Group submissions by quiz
    completed_quiz_ids = [s.quiz_id for s in my_submissions if s.is_completed]
    
    return render_template('student/dashboard.html',
                          active_quizzes=active_quizzes,
                          my_submissions=my_submissions,
                          completed_quiz_ids=completed_quiz_ids,
                          title='Student Dashboard')

@app.route('/student/quizzes/<int:quiz_id>/start', methods=['GET', 'POST'])
@login_required
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    if not quiz.is_active:
        flash('This quiz is not active.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    # Check if the user already started but not completed the quiz
    existing_submission = Submission.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz_id,
        is_completed=False
    ).first()
    
    if existing_submission:
        # Continue existing submission
        return redirect(url_for('take_quiz', quiz_id=quiz_id, submission_id=existing_submission.id))
    
    # Check if the user already completed the quiz
    completed_submission = Submission.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz_id,
        is_completed=True
    ).first()
    
    if completed_submission:
        flash('You have already completed this quiz.', 'info')
        return redirect(url_for('student_view_submission', submission_id=completed_submission.id))
    
    # Create new submission
    submission = Submission(
        user_id=current_user.id,
        quiz_id=quiz_id,
        started_at=datetime.utcnow()
    )
    db.session.add(submission)
    db.session.commit()
    
    return redirect(url_for('take_quiz', quiz_id=quiz_id, submission_id=submission.id))
# Update the take_quiz route to handle different question types
@app.route('/student/quizzes/<int:quiz_id>/submissions/<int:submission_id>', methods=['GET', 'POST'])
@login_required
def take_quiz(quiz_id, submission_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    submission = Submission.query.get_or_404(submission_id)
    
    if submission.user_id != current_user.id:
        abort(403)
    
    if submission.is_completed:
        return redirect(url_for('student_view_submission', submission_id=submission.id))
    
    # Check if time is up
    time_limit_seconds = quiz.time_limit * 60
    elapsed_seconds = (datetime.utcnow() - submission.started_at).total_seconds()
    time_remaining = max(0, time_limit_seconds - elapsed_seconds)
    
    if time_remaining <= 0:
        # Time's up - mark as completed
        submission.is_completed = True
        submission.completed_at = datetime.utcnow()
        submission.calculate_score()
        db.session.commit()
        flash('Time\'s up! Your quiz has been automatically submitted.', 'info')
        return redirect(url_for('student_view_submission', submission_id=submission.id))
    
    # Get all questions for this quiz
    questions = quiz.questions.order_by(Question.order).all()
    
    if not questions:
        flash('This quiz has no questions yet.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Get current question (first unanswered or first)
    current_question = None
    for question in questions:
        # Check if this question has already been submitted
        question_submission = QuestionSubmission.query.filter_by(
            submission_id=submission.id,
            question_id=question.id
        ).first()
        
        if not question_submission:
            current_question = question
            break
    
    if not current_question:
        # All questions have been answered
        current_question = questions[0]
    
    # Check if a specific question was requested
    requested_question_id = request.args.get('question_id', type=int)
    if requested_question_id:
        requested_question = Question.query.get(requested_question_id)
        if requested_question and requested_question.quiz_id == quiz_id:
            current_question = requested_question
    
    # Get existing submission for this question if any
    question_submission = QuestionSubmission.query.filter_by(
        submission_id=submission.id,
        question_id=current_question.id
    ).first()
    
    # Initialize variables for templates
    code_form = None
    multiple_choice_form = None
    true_false_form = None
    test_results = []
    selected_options = []
    selected_answer = None
    
    if current_question.question_type == 'code':
        # Create form for code submission
        code_form = CodeSubmissionForm()
        code_form.language.data = current_question.language  # Default to question language
        
        if code_form.validate_on_submit():
            # Save the code submission
            if question_submission is None:
                question_submission = QuestionSubmission(
                    submission_id=submission.id,
                    question_id=current_question.id,
                    code=code_form.code.data,
                    language=code_form.language.data,
                    submitted_at=datetime.utcnow()
                )
                db.session.add(question_submission)
            else:
                question_submission.code = code_form.code.data
                question_submission.language = code_form.language.data
                question_submission.submitted_at = datetime.utcnow()
            
            db.session.commit()
            
            # Run test cases
            test_cases = current_question.test_cases.all()
            for test_case in test_cases:
                # Check if we already have a result for this test case
                test_result = TestResult.query.filter_by(
                    question_submission_id=question_submission.id,
                    test_case_id=test_case.id
                ).first()
                
                # Run the test case
                result = PistonAPI.run_test_case(code_form.language.data, code_form.code.data, test_case)
                
                if test_result is None:
                    test_result = TestResult(
                        question_submission_id=question_submission.id,
                        test_case_id=test_case.id,
                        passed=result['passed'],
                        output=result['output'],
                        error=result['error'],
                        execution_time=result['execution_time']
                    )
                    db.session.add(test_result)
                else:
                    test_result.passed = result['passed']
                    test_result.output = result['output']
                    test_result.error = result['error']
                    test_result.execution_time = result['execution_time']
            
            # Calculate score for this question
            question_submission.calculate_score()
            db.session.commit()
            
            # Check if all questions have been answered
            all_answered = True
            for q in questions:
                q_submission = QuestionSubmission.query.filter_by(
                    submission_id=submission.id,
                    question_id=q.id
                ).first()
                if not q_submission:
                    all_answered = False
                    break
            
            if all_answered:
                flash('All questions have been answered! You can review your answers or submit the quiz.', 'success')
            else:
                # Move to next unanswered question
                next_question = None
                found_current = False
                for q in questions:
                    if found_current:
                        q_submission = QuestionSubmission.query.filter_by(
                            submission_id=submission.id,
                            question_id=q.id
                        ).first()
                        if not q_submission:
                            next_question = q
                            break
                    if q.id == current_question.id:
                        found_current = True
                
                if next_question:
                    flash('Your answer has been saved. Moving to the next question.', 'success')
                    return redirect(url_for('take_quiz', quiz_id=quiz_id, submission_id=submission.id, question_id=next_question.id))
                else:
                    flash('Your answer has been saved.', 'success')
                    return redirect(url_for('take_quiz', quiz_id=quiz_id, submission_id=submission.id))
        
        # Pre-populate form with existing submission if any
        if question_submission and not code_form.is_submitted():
            code_form.code.data = question_submission.code
            code_form.language.data = question_submission.language
        elif not code_form.is_submitted():
            # Use starter code if available
            code_form.code.data = current_question.starter_code
        
        # Get test results for this question
        if question_submission:
            test_results = TestResult.query.join(TestCase).filter(
                TestResult.question_submission_id == question_submission.id,
                TestCase.is_hidden == False
            ).all()
    
    elif current_question.question_type == 'multiple_choice':
        # Create form for multiple choice submission
        multiple_choice_form = MultipleChoiceSubmissionForm()
        
        # Get the options for this question
        options = current_question.options.order_by(QuestionOption.order).all()
        
        if request.method == 'POST':
            # Process form submission
            selected_option_ids = []
            for key, value in request.form.items():
                if key.startswith('selected_options-') and value:
                    selected_option_ids.append(int(value))
            
            # Create or update submission
            if question_submission is None:
                question_submission = QuestionSubmission(
                    submission_id=submission.id,
                    question_id=current_question.id,
                    submitted_at=datetime.utcnow()
                )
                db.session.add(question_submission)
                db.session.flush()  # Get the ID without committing
            else:
                # Remove existing selected options
                SelectedOption.query.filter_by(question_submission_id=question_submission.id).delete()
            
            # Add selected options
            for option_id in selected_option_ids:
                selected_option = SelectedOption(
                    question_submission_id=question_submission.id,
                    option_id=option_id
                )
                db.session.add(selected_option)
            
            db.session.commit()
            
            # Calculate score
            question_submission.calculate_score()
            db.session.commit()
            
            flash('Your answer has been saved.', 'success')
            
            # Check if all questions have been answered or move to next unanswered
            # (Similar to code question handling above)
            all_answered = True
            for q in questions:
                q_submission = QuestionSubmission.query.filter_by(
                    submission_id=submission.id,
                    question_id=q.id
                ).first()
                if not q_submission:
                    all_answered = False
                    break
            
            if all_answered:
                flash('All questions have been answered! You can review your answers or submit the quiz.', 'success')
            else:
                # Move to next unanswered question
                next_question = None
                found_current = False
                for q in questions:
                    if found_current:
                        q_submission = QuestionSubmission.query.filter_by(
                            submission_id=submission.id,
                            question_id=q.id
                        ).first()
                        if not q_submission:
                            next_question = q
                            break
                    if q.id == current_question.id:
                        found_current = True
                
                if next_question:
                    flash('Moving to the next question.', 'success')
                    return redirect(url_for('take_quiz', quiz_id=quiz_id, submission_id=submission.id, question_id=next_question.id))
        
        # Get previously selected options
        if question_submission:
            selected_options = [opt.option_id for opt in question_submission.selected_options]
    
    elif current_question.question_type == 'true_false':
        # Create form for true/false submission
        true_false_form = TrueFalseSubmissionForm()
        
        if request.method == 'POST':
            selected_answer = request.form.get('answer')
            
            # Create or update submission
            if question_submission is None:
                question_submission = QuestionSubmission(
                    submission_id=submission.id,
                    question_id=current_question.id,
                    submitted_at=datetime.utcnow()
                )
                db.session.add(question_submission)
                db.session.flush()  # Get the ID without committing
            else:
                # Remove existing selected option
                SelectedOption.query.filter_by(question_submission_id=question_submission.id).delete()
            
            # Find the option ID based on the selected answer
            option = None
            if selected_answer == 'true':
                option = current_question.options.filter_by(text='True').first()
            else:
                option = current_question.options.filter_by(text='False').first()
            
            if option:
                selected_option = SelectedOption(
                    question_submission_id=question_submission.id,
                    option_id=option.id
                )
                db.session.add(selected_option)
            
            db.session.commit()
            
            # Calculate score
            question_submission.calculate_score()
            db.session.commit()
            
            flash('Your answer has been saved.', 'success')
            
            # Check if all questions have been answered or move to next unanswered
            # (Similar to code question handling above)
            all_answered = True
            for q in questions:
                q_submission = QuestionSubmission.query.filter_by(
                    submission_id=submission.id,
                    question_id=q.id
                ).first()
                if not q_submission:
                    all_answered = False
                    break
            
            if all_answered:
                flash('All questions have been answered! You can review your answers or submit the quiz.', 'success')
            else:
                # Move to next unanswered question
                next_question = None
                found_current = False
                for q in questions:
                    if found_current:
                        q_submission = QuestionSubmission.query.filter_by(
                            submission_id=submission.id,
                            question_id=q.id
                        ).first()
                        if not q_submission:
                            next_question = q
                            break
                    if q.id == current_question.id:
                        found_current = True
                
                if next_question:
                    flash('Moving to the next question.', 'success')
                    return redirect(url_for('take_quiz', quiz_id=quiz_id, submission_id=submission.id, question_id=next_question.id))
        
        # Get previously selected answer
        if question_submission and question_submission.selected_options.first():
            option = question_submission.selected_options.first().option
            if option.text == 'True':
                selected_answer = 'true'
            else:
                selected_answer = 'false'
    
    # Format time remaining
    formatted_time = format_time_remaining(time_remaining)
    
    return render_template('student/quiz.html',
                          quiz=quiz,
                          submission=submission,
                          questions=questions,
                          current_question=current_question,
                          code_form=code_form,
                          multiple_choice_form=multiple_choice_form,
                          true_false_form=true_false_form,
                          question_submission=question_submission,
                          test_results=test_results,
                          selected_options=selected_options,
                          selected_answer=selected_answer,
                          time_remaining=int(time_remaining),
                          formatted_time=formatted_time,
                          title=f'Quiz: {quiz.title}')

@app.route('/student/quizzes/<int:quiz_id>/submissions/<int:submission_id>/submit', methods=['POST'])
@login_required
def submit_quiz(quiz_id, submission_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    submission = Submission.query.get_or_404(submission_id)
    
    if submission.user_id != current_user.id:
        abort(403)
    
    if submission.is_completed:
        flash('This quiz has already been submitted.', 'info')
        return redirect(url_for('student_view_submission', submission_id=submission.id))
    
    # Mark as completed
    submission.is_completed = True
    submission.completed_at = datetime.utcnow()
    submission.calculate_score()
    db.session.commit()
    
    flash('Quiz submitted successfully!', 'success')
    return redirect(url_for('student_view_submission', submission_id=submission.id))

@app.route('/student/submissions/<int:submission_id>')
@login_required
def student_view_submission(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    
    if submission.user_id != current_user.id:
        abort(403)
    
    quiz = Quiz.query.get_or_404(submission.quiz_id)
    questions = quiz.questions.order_by(Question.order).all()
    
    # Get all question submissions
    question_submissions = {}
    for q in questions:
        q_submission = QuestionSubmission.query.filter_by(
            submission_id=submission.id,
            question_id=q.id
        ).first()
        if q_submission:
            question_submissions[q.id] = q_submission
    
    # Get test results for each question
    test_results = {}
    selected_options = {}
    
    for q_id, q_submission in question_submissions.items():
        question = Question.query.get(q_id)
        
        if question.question_type == 'code':
            results = TestResult.query.join(TestCase).filter(
                TestResult.question_submission_id == q_submission.id,
                TestCase.is_hidden == False
            ).all()
            test_results[q_id] = results
        elif question.question_type in ['multiple_choice', 'true_false']:
            selected_opts = [so.option_id for so in q_submission.selected_options]
            selected_options[q_id] = selected_opts
    
    return render_template('student/submission_detail.html',
                          submission=submission,
                          quiz=quiz,
                          questions=questions,
                          question_submissions=question_submissions,
                          test_results=test_results,
                          selected_options=selected_options,
                          title='Quiz Results')

@app.route('/student/results')
@login_required
def student_results():
    submissions = Submission.query.filter_by(
        user_id=current_user.id,
        is_completed=True
    ).order_by(Submission.completed_at.desc()).all()
    
    return render_template('student/results.html',
                          submissions=submissions,
                          title='My Results')
# API routes for AJAX requests
@app.route('/api/run-code', methods=['POST'])
@login_required
def api_run_code():
    data = request.get_json()
    
    if not data or 'code' not in data or 'language' not in data:
        return jsonify({'error': 'Invalid request data'}), 400
    
    code = data.get('code')
    language = data.get('language')
    stdin = data.get('stdin', '')
    
    result = PistonAPI.execute_code(language, code, stdin)
    
    return jsonify(result)

@app.route('/api/time-remaining/<int:submission_id>', methods=['GET'])
@login_required
def api_time_remaining(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    
    if submission.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if submission.is_completed:
        return jsonify({'timeRemaining': 0, 'formatted': '00:00'})
    
    quiz = Quiz.query.get_or_404(submission.quiz_id)
    time_limit_seconds = quiz.time_limit * 60
    elapsed_seconds = (datetime.utcnow() - submission.started_at).total_seconds()
    time_remaining = max(0, time_limit_seconds - elapsed_seconds)
    
    return jsonify({
        'timeRemaining': int(time_remaining),
        'formatted': format_time_remaining(time_remaining)
    })

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        # Drop all existing tables (be careful with this in production!)
        db.drop_all()
        
        # Recreate all tables with the latest schema
        db.create_all()
        
        # Create admin user if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin/admin')
    
    app.run(debug=True)