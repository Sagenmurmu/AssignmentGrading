import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import google.generativeai as genai
from datetime import datetime
from models import db, Question, Submission
from utils import extract_text_from_pdf, extract_text_from_image, analyze_with_gemini

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default-secret-key")  # Set default secret key
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure Gemini AI
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Initialize database
db.init_app(app)

# Drop and recreate all tables
with app.app_context():
    db.drop_all()
    db.create_all()
    logging.info("Database tables recreated successfully")

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Initialize database tables with error logging
with app.app_context():
    try:
        db.create_all()
        logging.info("Database tables created successfully")
    except Exception as e:
        logging.error(f"Error creating database tables: {str(e)}")
        raise

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Teacher routes
@app.route('/teacher')
def teacher_dashboard():
    try:
        questions = Question.query.order_by(Question.created_at.desc()).all()
        return render_template('teacher/dashboard.html', questions=questions)
    except Exception as e:
        logging.error(f"Error in teacher dashboard: {str(e)}")
        flash('Error loading questions')
        return redirect(url_for('home'))

@app.route('/teacher/question/new', methods=['GET', 'POST'])
def create_question():
    if request.method == 'POST':
        try:
            question = Question(
                title=request.form['title'],
                question_text=request.form['question_text'],
                max_marks=int(request.form['max_marks']),
                deadline=datetime.fromisoformat(request.form['deadline']),
                requires_examples=bool(request.form.get('requires_examples')),
                requires_diagrams=bool(request.form.get('requires_diagrams'))
            )
            db.session.add(question)
            db.session.commit()
            flash('Question created successfully!')
            return redirect(url_for('teacher_dashboard'))
        except Exception as e:
            logging.error(f"Error creating question: {str(e)}")
            flash('Error creating question')
            return redirect(url_for('create_question'))
    return render_template('teacher/create_question.html')

# Student routes
@app.route('/')
def home():
    try:
        questions = Question.query.filter(Question.deadline > datetime.utcnow()).all()
        return render_template('student/questions.html', questions=questions)
    except Exception as e:
        logging.error(f"Error loading questions: {str(e)}")
        flash('Error loading questions')
        return render_template('student/questions.html', questions=[])

@app.route('/question/<int:question_id>')
def view_question(question_id):
    try:
        question = Question.query.get_or_404(question_id)
        return render_template('student/submit_answer.html', question=question)
    except Exception as e:
        logging.error(f"Error viewing question {question_id}: {str(e)}")
        flash('Question not found')
        return redirect(url_for('home'))

@app.route('/extract', methods=['POST'])
def extract_text():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file selected'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(filepath)
            else:
                text = extract_text_from_image(filepath)

            return jsonify({'success': True, 'text': text})
        except Exception as e:
            logging.error(f"Error extracting text: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})
        finally:
            # Clean up the uploaded file
            if os.path.exists(filepath):
                os.remove(filepath)

    return jsonify({'success': False, 'error': 'Invalid file type'})

@app.route('/submit/<int:question_id>', methods=['POST'])
def submit_answer(question_id):
    try:
        question = Question.query.get_or_404(question_id)
        answer = request.form.get('answer')

        if not answer:
            flash('Please provide an answer')
            return redirect(url_for('view_question', question_id=question_id))

        grading_result = analyze_with_gemini(question.question_text, answer, question.max_marks)

        submission = Submission(
            answer=answer,
            question_id=question_id,
            introduction_marks=grading_result['introduction']['marks'],
            main_body_marks=grading_result['main_body']['marks'],
            conclusion_marks=grading_result['conclusion']['marks'],
            examples_marks=grading_result['examples']['marks'],
            diagrams_marks=grading_result['diagrams']['marks'],
            total_marks=grading_result['total_marks'],
            ai_detection_score=grading_result['ai_detection_score'],
            introduction_feedback=grading_result['introduction']['feedback'],
            main_body_feedback=grading_result['main_body']['feedback'],
            conclusion_feedback=grading_result['conclusion']['feedback'],
            examples_feedback=grading_result['examples']['feedback'],
            diagrams_feedback=grading_result['diagrams']['feedback']
        )
        db.session.add(submission)
        db.session.commit()

        return render_template('grading.html', 
                           result=grading_result, 
                           submission_id=submission.id,
                           max_marks=question.max_marks)
    except Exception as e:
        logging.error(f"Error submitting answer: {str(e)}")
        flash('Error during grading. Please try again.')
        return redirect(url_for('view_question', question_id=question_id))

@app.route('/review/<int:submission_id>')
def review(submission_id):
    try:
        submission = Submission.query.get_or_404(submission_id)
        question = submission.question

        review_feedback = analyze_with_gemini(
            question.question_text,
            submission.answer,
            question.max_marks,
            mode='review'
        )
        return render_template('review.html', feedback=review_feedback)
    except Exception as e:
        logging.error(f"Error generating review: {str(e)}")
        flash('Error generating review. Please try again.')
        return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)