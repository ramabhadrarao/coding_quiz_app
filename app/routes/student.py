from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import or_

from models import db, Quiz, Question, Submission, QuestionSubmission, TestResult, QuestionOption, SelectedOption
from forms import (CodeSubmissionForm, MultipleChoiceSubmissionForm, TrueFalseSubmissionForm)
from utils import PistonAPI, format_time_remaining

student_bp = Blueprint('student', __name__, url_prefix='/student')

@student_bp.route('/dashboard')
@login_required
def dashboard():
    active_quizzes = Quiz.query.filter_by(is_active=True).all()
    my_submissions = Submission.query.filter_by(user_id=current_user.id).order_by(Submission.started_at.desc()).all()
    
    # Group submissions by quiz
    completed_quiz_ids = [s.quiz_id for s in my_submissions if s.is_completed]
    
    return render_template('student/dashboard.html',
                          active_quizzes=active_quizzes,
                          my_submissions=my_submissions,
                          completed_quiz_ids=completed_quiz_ids,
                          title='Student Dashboard')

@student_bp.route('/quizzes/<int:quiz_id>/start', methods=['GET', 'POST'])
@login_required
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    if not quiz.is_active:
        flash('This quiz is not active.', 'danger')
        return redirect(url_for('student.dashboard'))
    
    # Check if the user already started but not completed the quiz
    existing_submission = Submission.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz_id,
        is_completed=False
    ).first()
    
    if existing_submission:
        # Continue existing submission
        return redirect(url_for('student.take_quiz', quiz_id=quiz_id, submission_id=existing_submission.id))
    
    # Check if the user already completed the quiz
    completed_submission = Submission.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz_id,
        is_completed=True
    ).first()
    
    if completed_submission:
        flash('You have already completed this quiz.', 'info')
        return redirect(url_for('student.view_submission', submission_id=completed_submission.id))
    
    # Create new submission
    submission = Submission(
        user_id=current_user.id,
        quiz_id=quiz_id,
        started_at=datetime.utcnow()
    )
    db.session.add(submission)
    db.session.commit()
    
    return redirect(url_for('student.take_quiz', quiz_id=quiz_id, submission_id=submission.id))

@student_bp.route('/quizzes/<int:quiz_id>/submissions/<int:submission_id>', methods=['GET', 'POST'])
@login_required
def take_quiz(quiz_id, submission_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    submission = Submission.query.get_or_404(submission_id)
    
    if submission.user_id != current_user.id:
        abort(403)
    
    if submission.is_completed:
        return redirect(url_for('student.view_submission', submission_id=submission.id))
    
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
        return redirect(url_for('student.view_submission', submission_id=submission.id))
    
    # Get all questions for this quiz
    questions = quiz.questions.order_by(Question.order).all()
    
    if not questions:
        flash('This quiz has no questions yet.', 'warning')
        return redirect(url_for('student.dashboard'))
    
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
                    return redirect(url_for('student.take_quiz', quiz_id=quiz_id, submission_id=submission.id, question_id=next_question.id))
                else:
                    flash('Your answer has been saved.', 'success')
                    return redirect(url_for('student.take_quiz', quiz_id=quiz_id, submission_id=submission.id))
        
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
                    return redirect(url_for('student.take_quiz', quiz_id=quiz_id, submission_id=submission.id, question_id=next_question.id))
        
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
                    return redirect(url_for('student.take_quiz', quiz_id=quiz_id, submission_id=submission.id, question_id=next_question.id))
        
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

@student_bp.route('/quizzes/<int:quiz_id>/submissions/<int:submission_id>/submit', methods=['POST'])
@login_required
def submit_quiz(quiz_id, submission_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    submission = Submission.query.get_or_404(submission_id)
    
    if submission.user_id != current_user.id:
        abort(403)
    
    if submission.is_completed:
        flash('This quiz has already been submitted.', 'info')
        return redirect(url_for('student.view_submission', submission_id=submission.id))
    
    # Mark as completed
    submission.is_completed = True
    submission.completed_at = datetime.utcnow()
    submission.calculate_score()
    db.session.commit()
    
    flash('Quiz submitted successfully!', 'success')
    return redirect(url_for('student.view_submission', submission_id=submission.id))

@student_bp.route('/submissions/<int:submission_id>')
@login_required
def view_submission(submission_id):
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

@student_bp.route('/results')
@login_required
def results():
    submissions = Submission.query.filter_by(
        user_id=current_user.id,
        is_completed=True
    ).order_by(Submission.completed_at.desc()).all()
    
    return render_template('student/results.html',
                          submissions=submissions,
                          title='My Results')
