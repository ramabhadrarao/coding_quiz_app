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
    problem_statement = db.Column(db.Text, nullable=False)
    starter_code = db.Column(db.Text)
    language = db.Column(db.String(20), nullable=False)  # python, c, java, etc.
    points = db.Column(db.Integer, default=10)
    order = db.Column(db.Integer, default=0)
    
    test_cases = db.relationship('TestCase', backref='question', lazy='dynamic', cascade='all, delete-orphan')
    submissions = db.relationship('QuestionSubmission', backref='question', lazy='dynamic')
    
    def __repr__(self):
        return f'<Question {self.title}>'

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
    code = db.Column(db.Text)
    language = db.Column(db.String(20))
    score = db.Column(db.Float, default=0)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    test_results = db.relationship('TestResult', backref='question_submission', lazy='dynamic', cascade='all, delete-orphan')
    
    def calculate_score(self):
        total_tests = self.test_results.count()
        if total_tests == 0:
            self.score = 0
            return self.score
            
        passed_tests = self.test_results.filter_by(passed=True).count()
        question_points = self.question.points
        
        self.score = (passed_tests / total_tests) * question_points
        return self.score
    
    def __repr__(self):
        return f'<QuestionSubmission {self.id} for Question {self.question_id}>'

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
