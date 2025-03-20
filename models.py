
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.dialects.postgresql import TEXT
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(20), nullable=True)  # e.g., "10A", "10B"
    teacher_code = db.Column(db.String(128), nullable=True)  # For teacher verification
    student_code = db.Column(db.String(128), nullable=True)  # For student verification
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def __repr__(self):
        return f'<User {self.username}>'

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    question_text = db.Column(TEXT, nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    requires_examples = db.Column(db.Boolean, default=False)
    requires_diagrams = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    teacher = db.relationship('User', backref='questions')
    submissions = db.relationship('Submission', backref='question', lazy='dynamic')

    def __repr__(self):
        return f'<Question {self.title}>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'question_text': self.question_text,
            'max_marks': self.max_marks,
            'deadline': self.deadline.isoformat(),
            'requires_examples': self.requires_examples,
            'requires_diagrams': self.requires_diagrams
        }

class Submission(db.Model):
    __tablename__ = 'submissions'
    id = db.Column(db.Integer, primary_key=True)
    answer = db.Column(TEXT, nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    student = db.relationship('User', backref='submissions')
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    introduction_marks = db.Column(db.Float)
    main_body_marks = db.Column(db.Float)
    conclusion_marks = db.Column(db.Float)
    examples_marks = db.Column(db.Float)
    diagrams_marks = db.Column(db.Float)
    total_marks = db.Column(db.Float)
    introduction_feedback = db.Column(TEXT)
    main_body_feedback = db.Column(TEXT)
    conclusion_feedback = db.Column(TEXT)
    examples_feedback = db.Column(TEXT)
    diagrams_feedback = db.Column(TEXT)
    ai_detection_score = db.Column(db.Float)
    plagiarism_score = db.Column(db.Float)
    plagiarism_matches = db.Column(TEXT)
    hash_signature = db.Column(db.String(64))
    conclusion_marks = db.Column(db.Float)
    examples_marks = db.Column(db.Float)
    diagrams_marks = db.Column(db.Float)
    total_marks = db.Column(db.Float)
    introduction_feedback = db.Column(TEXT)
    main_body_feedback = db.Column(TEXT)
    conclusion_feedback = db.Column(TEXT)
    examples_feedback = db.Column(TEXT)
    diagrams_feedback = db.Column(TEXT)
    ai_detection_score = db.Column(db.Float)
    plagiarism_score = db.Column(db.Float)
    plagiarism_matches = db.Column(TEXT)
    hash_signature = db.Column(db.String(64))

    def __repr__(self):
        return f'<Submission {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'answer': self.answer,
            'question_id': self.question_id,
            'submission_date': self.submission_date.isoformat(),
            'total_marks': self.total_marks,
            'section_marks': {
                'introduction': self.introduction_marks,
                'main_body': self.main_body_marks,
                'conclusion': self.conclusion_marks,
                'examples': self.examples_marks,
                'diagrams': self.diagrams_marks
            },
            'feedback': {
                'introduction': self.introduction_feedback,
                'main_body': self.main_body_feedback,
                'conclusion': self.conclusion_feedback,
                'examples': self.examples_feedback,
                'diagrams': self.diagrams_feedback
            },
            'ai_detection_score': self.ai_detection_score,
            'plagiarism_score': self.plagiarism_score
        }
