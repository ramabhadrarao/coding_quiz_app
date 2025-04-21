from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, BooleanField, IntegerField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from models import User

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class QuizForm(FlaskForm):
    title = StringField('Quiz Title', validators=[DataRequired()])
    description = TextAreaField('Description')
    time_limit = IntegerField('Time Limit (minutes)', validators=[DataRequired()])
    is_active = BooleanField('Active')

class QuestionForm(FlaskForm):
    title = StringField('Question Title', validators=[DataRequired()])
    description = TextAreaField('Description')
    problem_statement = TextAreaField('Problem Statement', validators=[DataRequired()])
    starter_code = TextAreaField('Starter Code', validators=[Optional()])
    language = SelectField('Language', validators=[DataRequired()])
    points = IntegerField('Points', validators=[DataRequired()])
    order = IntegerField('Order', validators=[DataRequired()])
    
    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        from config import Config
        self.language.choices = [(lang, details['name']) for lang, details in Config.SUPPORTED_LANGUAGES.items()]

class TestCaseForm(FlaskForm):
    input_data = TextAreaField('Input Data')
    expected_output = TextAreaField('Expected Output', validators=[DataRequired()])
    is_hidden = BooleanField('Hidden Test Case')
    order = IntegerField('Order', validators=[DataRequired()])

class CodeSubmissionForm(FlaskForm):
    code = TextAreaField('Your Code', validators=[DataRequired()])
    language = SelectField('Language', validators=[DataRequired()])
    
    def __init__(self, *args, **kwargs):
        super(CodeSubmissionForm, self).__init__(*args, **kwargs)
        from config import Config
        self.language.choices = [(lang, details['name']) for lang, details in Config.SUPPORTED_LANGUAGES.items()]
