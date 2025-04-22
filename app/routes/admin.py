import os
import traceback
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
    
    if request.method == 'POST':
        # Debug the POST data
        print("\n===== MULTIPLE CHOICE FORM SUBMISSION =====")
        print(f"Form data keys: {request.form.keys()}")
        
        # Process manually instead of using form.validate_on_submit()
        try:
            # Extract basic question data
            title = request.form.get('title', '')
            description = request.form.get('description', '')
            problem_statement = request.form.get('problem_statement', '')
            points = request.form.get('points', 10)
            order = request.form.get('order', 1)
            
            # Validate required fields
            errors = []
            if not title:
                errors.append("Title is required")
            if not problem_statement:
                errors.append("Problem statement is required")
                
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('admin/multiple_choice_question_form.html', 
                                      form=form, 
                                      quiz=quiz,
                                      title='Create Multiple Choice Question')
            
            # Create the question
            question = Question(
                quiz_id=quiz_id,
                title=title,
                description=description,
                problem_statement=problem_statement,
                question_type='multiple_choice',
                points=int(points),
                order=int(order)
            )
            db.session.add(question)
            db.session.flush()  # Get the question ID without committing
            print(f"Question created with ID: {question.id}")
            
            # Extract and process options
            option_count = 0
            for key in request.form.keys():
                if key.startswith('options-') and key.endswith('-text'):
                    option_index = key.split('-')[1]
                    text_key = f'options-{option_index}-text'
                    is_correct_key = f'options-{option_index}-is_correct'
                    order_key = f'options-{option_index}-order'
                    
                    option_text = request.form.get(text_key, '')
                    is_correct = is_correct_key in request.form
                    order_value = request.form.get(order_key, option_count)
                    
                    print(f"Processing option {option_index}: Text: '{option_text[:20]}...', Correct: {is_correct}")
                    
                    # Handle image upload
                    image_path = None
                    file_field = f'options-{option_index}-image'
                    if file_field in request.files:
                        file = request.files[file_field]
                        if file and file.filename and allowed_file(file.filename):
                            try:
                                filename = secure_filename(file.filename)
                                # Create unique filename with timestamp
                                filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
                                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                                file.save(file_path)
                                image_path = filename
                                print(f"Saved image: {image_path}")
                            except Exception as e:
                                print(f"Error saving file: {str(e)}")
                                flash(f"Error saving image: {str(e)}", 'warning')
                    
                    # Create the option if text is provided
                    if option_text.strip():
                        option = QuestionOption(
                            question_id=question.id,
                            text=option_text,
                            is_correct=is_correct,
                            order=int(order_value) if order_value else option_count,
                            image_path=image_path
                        )
                        db.session.add(option)
                        option_count += 1
            
            # Ensure we have at least one option
            if option_count == 0:
                db.session.rollback()
                flash('Please add at least one option for the multiple choice question.', 'danger')
                return render_template('admin/multiple_choice_question_form.html', 
                                      form=form, 
                                      quiz=quiz,
                                      title='Create Multiple Choice Question')
            
            # Commit the transaction
            db.session.commit()
            flash('Multiple choice question created successfully!', 'success')
            return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating multiple choice question: {str(e)}")
            traceback.print_exc()
            flash(f'Error creating question: {str(e)}', 'danger')
    
    # For GET requests or if form validation fails
    form.order.data = quiz.questions.count() + 1
    form.points.data = 10
    
    # Ensure we have at least 2 option forms
    while len(form.options) < 2:
        form.options.append_entry()
    
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
    
    # For POST requests, process the form manually
    if request.method == 'POST':
        print("\n===== EDIT MULTIPLE CHOICE FORM SUBMISSION =====")
        print(f"Form data keys: {list(request.form.keys())}")
        
        try:
            # Extract basic question data
            title = request.form.get('title', '')
            description = request.form.get('description', '')
            problem_statement = request.form.get('problem_statement', '')
            points = request.form.get('points', 10)
            order = request.form.get('order', 1)
            
            # Validate required fields
            errors = []
            if not title:
                errors.append("Title is required")
            if not problem_statement:
                errors.append("Problem statement is required")
                
            if errors:
                for error in errors:
                    flash(error, 'danger')
                # Create basic form for error redisplay
                form = MultipleChoiceQuestionForm()
                form.title.data = title
                form.description.data = description
                form.problem_statement.data = problem_statement
                form.points.data = points
                form.order.data = order
                return render_template('admin/multiple_choice_question_form.html', 
                                      form=form, 
                                      quiz=quiz,
                                      question=question,
                                      title='Edit Multiple Choice Question')
            
            # Update the question
            question.title = title
            question.description = description
            question.problem_statement = problem_statement
            question.points = int(points)
            question.order = int(order)
            print(f"Updated question fields: {question.title}")
            
            # Delete all existing options first
            for option in question.options.all():
                db.session.delete(option)
            db.session.flush()
            print("Deleted all existing options")
            
            # Process and create new options from form data
            option_count = 0
            option_indices = set()
            
            # Find all unique option indices in the form
            for key in request.form.keys():
                if key.startswith('options-') and '-text' in key:
                    parts = key.split('-')
                    if len(parts) >= 3:
                        try:
                            option_indices.add(int(parts[1]))
                        except ValueError:
                            continue
            
            print(f"Found option indices: {sorted(option_indices)}")
            
            # Process each option
            for idx in sorted(option_indices):
                text_key = f'options-{idx}-text'
                is_correct_key = f'options-{idx}-is_correct'
                order_key = f'options-{idx}-order'
                
                option_text = request.form.get(text_key, '').strip()
                is_correct = is_correct_key in request.form
                order_value = request.form.get(order_key, option_count)
                
                # Skip empty options
                if not option_text:
                    print(f"Skipping empty option at index {idx}")
                    continue
                
                print(f"Processing option {idx}: Text: '{option_text[:20]}...', Correct: {is_correct}")
                
                # Handle image upload
                image_path = None
                file_field = f'options-{idx}-image'
                if file_field in request.files:
                    file = request.files[file_field]
                    if file and file.filename and allowed_file(file.filename):
                        try:
                            filename = secure_filename(file.filename)
                            # Create unique filename with timestamp
                            filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
                            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                            file.save(file_path)
                            image_path = filename
                            print(f"Saved image: {image_path}")
                        except Exception as e:
                            print(f"Error saving file: {str(e)}")
                            flash(f"Error saving image: {str(e)}", 'warning')
                
                # Create new option
                option = QuestionOption(
                    question_id=question.id,
                    text=option_text,
                    is_correct=is_correct,
                    order=int(order_value) if order_value else option_count,
                    image_path=image_path
                )
                db.session.add(option)
                option_count += 1
                print(f"Added option: {option_text[:20]}...")
            
            # Ensure we have at least one option
            if option_count == 0:
                db.session.rollback()
                flash('Please add at least one option for the multiple choice question.', 'danger')
                # Create basic form for error redisplay
                form = MultipleChoiceQuestionForm()
                form.title.data = title
                form.description.data = description
                form.problem_statement.data = problem_statement
                form.points.data = points
                form.order.data = order
                return render_template('admin/multiple_choice_question_form.html', 
                                    form=form, 
                                    quiz=quiz,
                                    question=question,
                                    title='Edit Multiple Choice Question')
            
            # Commit the transaction
            db.session.commit()
            print(f"Successfully committed changes: {option_count} options added")
            flash('Multiple choice question updated successfully!', 'success')
            return redirect(url_for('admin.edit_quiz', quiz_id=quiz_id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error updating multiple choice question: {str(e)}")
            traceback.print_exc()
            flash(f'Error updating question: {str(e)}', 'danger')
            # Create a basic form in case of error
            form = MultipleChoiceQuestionForm(obj=question)
            return render_template('admin/multiple_choice_question_form.html', 
                                  form=form, 
                                  quiz=quiz,
                                  question=question,
                                  title='Edit Multiple Choice Question')
    
    # For GET requests, create a form and populate it
    form = MultipleChoiceQuestionForm(obj=question)
    
    # Create a list of options for the template to use directly
    options = []
    for option in question.options.order_by(QuestionOption.order).all():
        options.append({
            'id': option.id,
            'text': option.text,
            'is_correct': option.is_correct,
            'order': option.order,
            'image_path': option.image_path
        })
    
    # Pass options directly to the template
    return render_template('admin/multiple_choice_question_form.html', 
                           form=form, 
                           quiz=quiz,
                           question=question,
                           existing_options=options,  # Pass options directly
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
    
    if request.method == 'POST':
        print("\n===== TEST CASE FORM SUBMISSION =====")
        print(f"Form data: {request.form}")
        
        try:
            # Process the form manually to better debug issues
            input_data = request.form.get('input_data', '')
            expected_output = request.form.get('expected_output', '')
            is_hidden = 'is_hidden' in request.form
            order = request.form.get('order', '1')
            
            # Validate required fields
            if not expected_output:
                flash('Expected output is required.', 'danger')
                return render_template('admin/test_case_form.html', 
                                      form=form, 
                                      quiz=quiz,
                                      question=question,
                                      title='Create Test Case')
            
            # Create and save the test case
            test_case = TestCase(
                question_id=question_id,
                input_data=input_data,
                expected_output=expected_output,
                is_hidden=is_hidden,
                order=int(order)
            )
            
            db.session.add(test_case)
            db.session.commit()
            
            flash('Test case created successfully!', 'success')
            return redirect(url_for('admin.edit_question', quiz_id=quiz_id, question_id=question_id))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating test case: {str(e)}")
            traceback.print_exc()
            flash(f'Error creating test case: {str(e)}', 'danger')
    
    # Default value for order
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