import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
from datetime import datetime
from models import db, User, Question, Submission
from utils import extract_text_from_pdf, extract_text_from_image, analyze_with_gemini

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    # Generate a secure random key if SESSION_SECRET is not set
    import secrets
    app.secret_key = secrets.token_hex(32)

# Configure database
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max file size

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logging.info(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# Configure Gemini AI
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Initialize database
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Load user from database
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form['role']
        password = request.form['password']

        if role == 'teacher':
            code = request.form.get('teacher_code')
            user = User.query.filter_by(teacher_code=code, role='teacher').first()
        else:
            code = request.form.get('student_code')
            user = User.query.filter_by(student_code=code, role='student').first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('home'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        class_name = request.form.get('class') # Get class if applicable

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose another.')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        teacher_code = request.form.get('teacher_code') if role == 'teacher' else None
        student_code = request.form.get('student_code') if role == 'student' else None
        new_user = User(username=username, password_hash=hashed_password, email=request.form['email'], 
                       role=role, class_name=class_name, teacher_code=teacher_code, student_code=student_code)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')


# Teacher routes (updated with login_required)
@app.route('/teacher')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher':
        return redirect(url_for('login'))

    try:
        questions = Question.query.filter_by(teacher_id=current_user.id).order_by(Question.created_at.desc()).all()
        return render_template('teacher/dashboard.html', questions=questions)
    except Exception as e:
        logging.error(f"Error in teacher dashboard: {str(e)}")
        flash('Error loading questions')
        return redirect(url_for('home'))

@app.route('/teacher/question/new', methods=['GET', 'POST'])
@login_required
def create_question():
    if current_user.role != 'teacher':
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            question = Question(
                title=request.form['title'],
                question_text=request.form['question_text'],
                max_marks=int(request.form['max_marks']),
                deadline=datetime.fromisoformat(request.form['deadline']),
                requires_examples=bool(request.form.get('requires_examples')),
                requires_diagrams=bool(request.form.get('requires_diagrams')),
                teacher_id=current_user.id
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


# Student routes (updated with login_required and class filtering)
@app.route('/')
@login_required
def home():
    if current_user.role != 'student':
        return redirect(url_for('login'))

    try:
        questions = Question.query.filter(Question.deadline > datetime.utcnow(), Question.teacher_id.in_([t.id for t in User.query.filter_by(class_name=current_user.class_name, role='teacher').all()])).all()
        return render_template('student/questions.html', questions=questions)
    except Exception as e:
        logging.error(f"Error loading questions: {str(e)}")
        flash('Error loading questions')
        return render_template('student/questions.html', questions=[])

@app.route('/question/<int:question_id>')
@login_required
def view_question(question_id):
    if current_user.role != 'student':
        return redirect(url_for('login'))

    try:
        question = Question.query.get_or_404(question_id)
        if question.teacher.class_name != current_user.class_name:
            flash("You are not authorized to view this question.")
            return redirect(url_for('home'))
        return render_template('student/submit_answer.html', question=question)
    except Exception as e:
        logging.error(f"Error viewing question {question_id}: {str(e)}")
        flash('Question not found')
        return redirect(url_for('home'))

#Extract and Submit routes
@app.route('/extract', methods=['POST'])
def extract_text():
    try:
        logging.debug("Starting text extraction process")
        if 'file' not in request.files:
            logging.warning("No file part in request")
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        file = request.files['file']
        if file.filename == '':
            logging.warning("No selected file")
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            logging.debug(f"Saving file to: {filepath}")
            file.save(filepath)

            try:
                if filename.lower().endswith('.pdf'):
                    logging.debug("Processing PDF file")
                    text = extract_text_from_pdf(filepath)
                else:
                    logging.debug("Processing image file")
                    text = extract_text_from_image(filepath)

                if not text:
                    raise ValueError("No text extracted from file")

                logging.info("Text extraction successful")
                logging.debug(f"Extracted text length: {len(text)}")
                return jsonify({'success': True, 'text': text}), 200

            except Exception as e:
                logging.error(f"Error in text extraction: {str(e)}")
                return jsonify({'success': False, 'error': str(e)}), 500
            finally:
                # Clean up uploaded file
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logging.debug(f"Cleaned up file: {filepath}")

        logging.warning(f"Invalid file type: {file.filename}")
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400

    except Exception as e:
        logging.error(f"Unexpected error in extract_text: {str(e)}")
        return jsonify({'success': False, 'error': 'Server error during text extraction'}), 500

@app.route('/submit/<int:question_id>', methods=['POST'])
@login_required
def submit_answer(question_id):
    try:
        logging.debug(f"Starting submission for question_id: {question_id}")
        question = Question.query.get_or_404(question_id)
        answer = request.form.get('answer')

        if not answer:
            logging.warning("No answer provided in submission")
            flash('Please provide an answer')
            return redirect(url_for('view_question', question_id=question_id))

        # Log input data for debugging
        logging.debug(f"Question text: {question.question_text}")
        logging.debug(f"Answer length: {len(answer)}")
        logging.debug(f"Max marks: {question.max_marks}")

        # Validate Gemini API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logging.error("Gemini API key not found")
            flash('System configuration error. Please contact administrator.')
            return redirect(url_for('view_question', question_id=question_id))

        # Get grading result with error handling
        try:
            logging.debug("Calling analyze_with_gemini")
            grading_result = analyze_with_gemini(question.question_text, answer, question.max_marks)
            logging.debug(f"Received grading result: {grading_result}")

            if not grading_result or not isinstance(grading_result, dict):
                logging.error(f"Invalid grading result format: {grading_result}")
                flash('Error during grading. Please try again.')
                return redirect(url_for('view_question', question_id=question_id))

            # Validate grading result structure
            required_fields = ['introduction', 'main_body', 'conclusion', 'examples', 'diagrams', 'total_marks']
            if not all(field in grading_result for field in required_fields):
                logging.error(f"Missing fields in grading result: {grading_result}")
                flash('Error during grading. Please try again.')
                return redirect(url_for('view_question', question_id=question_id))

        except Exception as e:
            logging.error(f"Error in analyze_with_gemini: {str(e)}")
            flash('Error during grading. Please try again.')
            return redirect(url_for('view_question', question_id=question_id))

        # Create submission with validated data
        try:
            submission = Submission(
                answer=answer,
                question_id=question_id,
                student_id=current_user.id,
                introduction_marks=float(grading_result['introduction']['marks']),
                main_body_marks=float(grading_result['main_body']['marks']),
                conclusion_marks=float(grading_result['conclusion']['marks']),
                examples_marks=float(grading_result['examples']['marks']),
                diagrams_marks=float(grading_result['diagrams']['marks']),
                total_marks=float(grading_result['total_marks']),
                introduction_feedback=str(grading_result['introduction']['feedback']),
                main_body_feedback=str(grading_result['main_body']['feedback']),
                conclusion_feedback=str(grading_result['conclusion']['feedback']),
                examples_feedback=str(grading_result['examples']['feedback']),
                diagrams_feedback=str(grading_result['diagrams']['feedback'])
            )

            db.session.add(submission)
            db.session.commit()
            logging.info(f"Successfully created submission: {submission.id}")

            return render_template('grading.html', 
                                   result=grading_result,
                                   submission_id=submission.id,
                                   max_marks=question.max_marks)

        except Exception as e:
            logging.error(f"Error creating submission: {str(e)}")
            db.session.rollback()
            flash('Error saving submission. Please try again.')
            return redirect(url_for('view_question', question_id=question_id))

    except Exception as e:
        logging.error(f"Error in submit_answer: {str(e)}")
        db.session.rollback()
        flash('Error during grading. Please try again.')
        return redirect(url_for('view_question', question_id=question_id))

@app.route('/review/<int:submission_id>')
@login_required
def review(submission_id):
    try:
        submission = Submission.query.get_or_404(submission_id)
        question = submission.question
        if current_user.role != 'teacher' or question.teacher_id != current_user.id:
            flash("You are not authorized to review this submission.")
            return redirect(url_for('home'))

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

# Database initialization with error handling
with app.app_context():
    try:
        db.create_all()
        db.session.commit()
        logging.info("Database tables created successfully")
    except Exception as e:
        logging.error(f"Error creating database tables: {str(e)}")
        raise

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)