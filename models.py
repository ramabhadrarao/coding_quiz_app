from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    quizzes = db.relationship('Quiz', backref='author', lazy='dynamic')
    submissions = db.relationship('Submission', backref='student', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    time_limit = db.Column(db.Integer, default=30)  # minutes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    questions = db.relationship('Question', backref='quiz', lazy='dynamic', cascade='all, delete-orphan')
    submissions = db.relationship('Submission', backref='quiz', lazy='dynamic')
    
    def __repr__(self):
        return f'<Quiz {self.title}>'

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    question_type = db.Column(db.String(20), nullable=False)  # 'multiple_choice', 'true_false', 'code'
    problem_statement = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, default=10)
    order = db.Column(db.Integer, default=0)
    
    # Fields for code questions
    starter_code = db.Column(db.Text)  # Initial code provided to students
    language = db.Column(db.String(20))  # python, c, java, etc.
    
    # Fields for multiple-choice questions
    options = db.relationship('QuestionOption', backref='question', lazy='dynamic', cascade='all, delete-orphan')
    
    # Common relationships
    test_cases = db.relationship('TestCase', backref='question', lazy='dynamic', cascade='all, delete-orphan')
    submissions = db.relationship('QuestionSubmission', backref='question', lazy='dynamic')
    
    def __repr__(self):
        return f'<Question {self.title}>'

class QuestionOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    text = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, default=0)
    image_path = db.Column(db.String(255))  # Optional path to an image
    
    def __repr__(self):
        return f'<Option {self.id} for Question {self.question_id}>'

class TestCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    input_data = db.Column(db.Text)
    expected_output = db.Column(db.Text, nullable=False)
    is_hidden = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<TestCase {self.id} for Question {self.question_id}>'

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    is_completed = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float)
    total_points = db.Column(db.Integer)
    
    question_submissions = db.relationship('QuestionSubmission', backref='submission', lazy='dynamic', cascade='all, delete-orphan')
    
    def calculate_score(self):
        total_points = sum([q.points for q in self.quiz.questions])
        earned_points = sum([qs.score for qs in self.question_submissions])
        
        self.score = earned_points
        self.total_points = total_points
        return self.score, self.total_points
    
    def __repr__(self):
        return f'<Submission {self.id} by User {self.user_id} for Quiz {self.quiz_id}>'

class QuestionSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submission.id'))
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    
    # For code questions
    code = db.Column(db.Text)
    language = db.Column(db.String(20))
    
    # For multiple choice and true/false questions
    selected_options = db.relationship('SelectedOption', backref='question_submission', lazy='dynamic', cascade='all, delete-orphan')
    
    score = db.Column(db.Float, default=0)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    test_results = db.relationship('TestResult', backref='question_submission', lazy='dynamic', cascade='all, delete-orphan')
    
    def calculate_score(self):
        # Calculate score based on question type
        question = self.question
        if question.question_type == 'code':
            # For code questions, score is based on passed test cases
            total_tests = self.test_results.count()
            if total_tests == 0:
                self.score = 0
                return self.score
                
            passed_tests = self.test_results.filter_by(passed=True).count()
            self.score = (passed_tests / total_tests) * question.points
            
        elif question.question_type == 'multiple_choice':
            # For multiple choice questions, score is based on selected options
            correct_options = [opt.id for opt in question.options.filter_by(is_correct=True)]
            selected_options = [opt.option_id for opt in self.selected_options]
            
            # All correct options must be selected and no incorrect options
            if set(selected_options) == set(correct_options):
                self.score = question.points
            else:
                self.score = 0
                
        elif question.question_type == 'true_false':
            # For true/false questions, score is based on the selected option
            correct_option = question.options.filter_by(is_correct=True).first()
            selected_option = self.selected_options.first()
            
            if selected_option and selected_option.option_id == correct_option.id:
                self.score = question.points
            else:
                self.score = 0
        
        return self.score
    
    def __repr__(self):
        return f'<QuestionSubmission {self.id} for Question {self.question_id}>'

class SelectedOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_submission_id = db.Column(db.Integer, db.ForeignKey('question_submission.id'))
    option_id = db.Column(db.Integer, db.ForeignKey('question_option.id'))
    
    option = db.relationship('QuestionOption')
    
    def __repr__(self):
        return f'<SelectedOption {self.id} for Submission {self.question_submission_id}>'

class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_submission_id = db.Column(db.Integer, db.ForeignKey('question_submission.id'))
    test_case_id = db.Column(db.Integer, db.ForeignKey('test_case.id'))
    passed = db.Column(db.Boolean, default=False)
    output = db.Column(db.Text)
    error = db.Column(db.Text)
    execution_time = db.Column(db.Float)  # in seconds
    
    test_case = db.relationship('TestCase')
    
    def __repr__(self):
        return f'<TestResult {self.id} for Test Case {self.test_case_id}>'