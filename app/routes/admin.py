import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps

from models import db, Quiz, Question, TestCase, Submission, QuestionOption
from forms import (QuizForm, CodeQuestionForm, TestCaseForm, 
                  MultipleChoiceQuestionForm, TrueFalseQuestionForm, OptionForm)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Helper function to check admin status
def admin_required(func):
    @wraps(func)
    @login_required
    def decorated_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return func(*args, **kwargs)
    return decorated_view

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    quizzes = Quiz.query.filter_by(author_id=current_user.id).all()
    recent_submissions = Submission.query.filter(
        Submission.quiz_id.in_([q.id for q in quizzes])
    ).order_by(Submission.completed_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html', 
                          quizzes=quizzes, 
                          recent_submissions=recent_submissions,
                          title='Admin Dashboard')

@admin_bp.route('/quizzes', methods=['GET'])
@admin_required
def quizzes():
    quizzes = Quiz.query.filter_by(author_id=current_user.id).all()
    return render_template('admin/quizzes.html', quizzes=quizzes, title='Manage Quizzes')

@admin_bp.route('/quizzes/new', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.edit_quiz', quiz_id=quiz.id))
    
    return render_template('admin/quiz_form.html', form=form, title='Create Quiz')

@admin_bp.route('/quizzes/<int:quiz_id>/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.quizzes'))
    
    questions = quiz.questions.order_by(Question.order).all()
    return render_template('admin/quiz_form.html', 
                          form=form, 
                          quiz=quiz, 
                          questions=questions,
                          title='Edit Quiz')

@admin_bp.route('/quizzes/<int:quiz_id>/delete', methods=['POST'])
@admin_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    db.session.delete(quiz)
    db.session.commit()
    flash('Quiz deleted successfully!', 'success')
    return redirect(url_for('admin.quizzes'))

# Question type selector route
@admin_bp.route('/quizzes/<int:quiz_id>/questions/select-type', methods=['GET'])
@admin_required
def select_question_type(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.author_id != current_user.id:
        abort(403)
    
    return render_template('admin/question_type_selector.html', quiz=quiz, title='Select Question Type')

# Code Question Routes
@admin_bp.route('/quizzes/<int:quiz_id>/questions/code/new', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.edit_question', quiz_id=quiz_id, question_id=question.id))
    
    # Default values for new question
    form.order.data = quiz.questions.count() + 1
    form.points.data = 10
    
    return render_template('admin/question_form.html', 
                          form=form, 
                          quiz=quiz,
                          title='Create Code Question')

@admin_bp.route('/quizzes/<int:quiz_id>/questions/<int:question_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_question(quiz_id, question_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id:
        abort(403)
    
    # Route based on question type
    if question.question_type == 'multiple_choice':
        return redirect(url_for('admin.edit_multiple_choice_question', quiz_id=quiz_id, question_id=question_id))
    elif question.question_type == 'true_false':
        return redirect(url_for('admin.edit_true_false_question', quiz_id=quiz_id, question_id=question_id))
    elif question.question_type == 'code' or not question.question_type:  # Default to code for backward compatibility
        form = CodeQuestionForm(obj=question)
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
            return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))
        
        test_cases = question.test_cases.order_by(TestCase.order).all()
        return render_template('admin/question_form.html', 
                            form=form, 
                            quiz=quiz, 
                            question=question,
                            test_cases=test_cases,
                            title='Edit Question')

@admin_bp.route('/quizzes/<int:quiz_id>/questions/<int:question_id>/delete', methods=['POST'])
@admin_required
def delete_question(quiz_id, question_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    question = Question.query.get_or_404(question_id)
    
    if quiz.author_id != current_user.id or question.quiz_id != quiz_id:
        abort(403)
    
    db.session.delete(question)
    db.session.commit()
    flash('Question deleted successfully!', 'success')
    return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))

# Multiple Choice Question Routes
@admin_bp.route('/quizzes/<int:quiz_id>/questions/multiple-choice/new', methods=['GET', 'POST'])
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
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
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
        return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))
    
    # Default values for new question
    form.order.data = quiz.questions.count() + 1
    form.points.data = 10
    
    return render_template('admin/multiple_choice_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          title='Create Multiple Choice Question')

@admin_bp.route('/quizzes/<int:quiz_id>/questions/<int:question_id>/multiple-choice/edit', methods=['GET', 'POST'])
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
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
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
        return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))
    
    return render_template('admin/multiple_choice_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          title='Edit Multiple Choice Question')

# True/False Question Routes
@admin_bp.route('/quizzes/<int:quiz_id>/questions/true-false/new', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))
    
    # Default values for new question
    form.order.data = quiz.questions.count() + 1
    form.points.data = 5
    
    return render_template('admin/true_false_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          title='Create True/False Question')

@admin_bp.route('/quizzes/<int:quiz_id>/questions/<int:question_id>/true-false/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))
    
    return render_template('admin/true_false_question_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          title='Edit True/False Question')

@admin_bp.route('/quizzes/<int:quiz_id>/questions/new', methods=['GET', 'POST'])
@admin_required
def create_question(quiz_id):
    # Redirect to question type selector
    return redirect(url_for('admin.select_question_type', quiz_id=quiz_id))

@admin_bp.route('/quizzes/<int:quiz_id>/questions/<int:question_id>/test-cases/new', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.edit_question', quiz_id=quiz_id, question_id=question_id))
    
    # Default values for new test case
    form.order.data = question.test_cases.count() + 1
    
    return render_template('admin/test_case_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          title='Create Test Case')

@admin_bp.route('/quizzes/<int:quiz_id>/questions/<int:question_id>/test-cases/<int:test_case_id>/edit', methods=['GET', 'POST'])
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
        return redirect(url_for('admin.edit_question', quiz_id=quiz_id, question_id=question_id))
    
    return render_template('admin/test_case_form.html', 
                          form=form, 
                          quiz=quiz,
                          question=question,
                          test_case=test_case,
                          title='Edit Test Case')

@admin_bp.route('/quizzes/<int:quiz_id>/questions/<int:question_id>/test-cases/<int:test_case_id>/delete', methods=['POST'])
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
    return redirect(url_for('admin.edit_question', quiz_id=quiz_id, question_id=question_id))

@admin_bp.route('/results')
@admin_required
def results():
    quizzes = Quiz.query.filter_by(author_id=current_user.id).all()
    submissions = Submission.query.filter(
        Submission.quiz_id.in_([q.id for q in quizzes])
    ).order_by(Submission.completed_at.desc()).all()
    
    return render_template('admin/results.html', 
                          submissions=submissions,
                          title='Quiz Results')

@admin_bp.route('/submission/<int:submission_id>')
@admin_required
def view_submission(submission_id):
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