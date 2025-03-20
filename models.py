from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.dialects.postgresql import TEXT

db = SQLAlchemy()

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(TEXT, nullable=False)
    answer = db.Column(TEXT, nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)

    # Section marks
    introduction_marks = db.Column(db.Float)
    main_body_marks = db.Column(db.Float)
    conclusion_marks = db.Column(db.Float)
    examples_marks = db.Column(db.Float)
    diagrams_marks = db.Column(db.Float)
    total_marks = db.Column(db.Float)

    # Feedback and analysis
    introduction_feedback = db.Column(TEXT)
    main_body_feedback = db.Column(TEXT)
    conclusion_feedback = db.Column(TEXT)
    examples_feedback = db.Column(TEXT)
    diagrams_feedback = db.Column(TEXT)

    # AI detection and plagiarism
    ai_detection_score = db.Column(db.Float)  # 0-1 score, higher means more likely AI-generated
    plagiarism_score = db.Column(db.Float)    # 0-1 score, higher means more likely plagiarized
    plagiarism_matches = db.Column(TEXT)      # JSON string containing matches

    # Metadata
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    hash_signature = db.Column(db.String(64))  # For quick plagiarism comparison

    def __repr__(self):
        return f'<Submission {self.id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'question': self.question,
            'answer': self.answer,
            'max_marks': self.max_marks,
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
            'plagiarism_score': self.plagiarism_score,
            'submission_date': self.submission_date.isoformat()
        }