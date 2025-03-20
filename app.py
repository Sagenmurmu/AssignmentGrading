import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
from datetime import datetime
from models import db, User, Question, Submission # Updated import to include User model
from utils import extract_text_from_pdf, extract_text_from_image, analyze_with_gemini

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default-secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Configure Gemini AI
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Initialize database
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect to login page if not logged in

# Load user from database
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Database initialization with error handling (unchanged)
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


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard')) # Redirect to appropriate dashboard
        else:
            flash('Invalid username or password')
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

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password, role=role, class_name=class_name)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')


# Teacher routes (updated with login_required)
@app.route('/teacher')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher':
        return redirect(url_for('login')) #or unauthorized page

    try:
        questions = Question.query.filter_by(teacher_id=current_user.id).order_by(Question.created_at.desc()).all() #Filter questions by teacher
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
                teacher_id=current_user.id # Add teacher ID to question
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
        # Add check to ensure student is in the correct class
        if question.teacher.class_name != current_user.class_name:
            flash("You are not authorized to view this question.")
            return redirect(url_for('home'))
        return render_template('student/submit_answer.html', question=question)
    except Exception as e:
        logging.error(f"Error viewing question {question_id}: {str(e)}")
        flash('Question not found')
        return redirect(url_for('home'))

#Extract and Submit routes (unchanged)
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
            if os.path.exists(filepath):
                os.remove(filepath)

    return jsonify({'success': False, 'error': 'Invalid file type'})

@app.route('/submit/<int:question_id>', methods=['POST'])
@login_required
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
            student_id=current_user.id, # Add student ID to submission
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
@login_required
def review(submission_id):
    try:
        submission = Submission.query.get_or_404(submission_id)
        question = submission.question
        # Add authorization check for teachers only
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)