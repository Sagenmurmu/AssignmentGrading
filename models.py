from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    introduction_marks = db.Column(db.Float)
    main_body_marks = db.Column(db.Float)
    conclusion_marks = db.Column(db.Float)
    examples_marks = db.Column(db.Float)
    diagrams_marks = db.Column(db.Float)
    total_marks = db.Column(db.Float)
    ai_detection_score = db.Column(db.Float)
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Submission {self.id}>'
