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
        class_name = request.form.get('class_name')

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose another.')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
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
        
@app.route('/teacher/question/delete/<int:question_id>')
@login_required
def delete_question(question_id):
    if current_user.role != 'teacher':
        return redirect(url_for('login'))
        
    try:
        question = Question.query.get_or_404(question_id)
        
        # Verify that the current teacher is the owner of this question
        if question.teacher_id != current_user.id:
            flash("You are not authorized to delete this question")
            return redirect(url_for('teacher_dashboard'))
            
        # Delete all associated submissions first
        Submission.query.filter_by(question_id=question_id).delete()
        
        # Then delete the question
        db.session.delete(question)
        db.session.commit()
        
        flash("Question and all associated submissions have been deleted")
        return redirect(url_for('teacher_dashboard'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting question {question_id}: {str(e)}")
        flash("An error occurred while trying to delete the question")
        return redirect(url_for('teacher_dashboard'))

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
        # If the student has a class name, filter questions by teachers in the same class
        if current_user.class_name:
            teacher_ids = [t.id for t in User.query.filter_by(class_name=current_user.class_name, role='teacher').all()]
        else:
            # If the student doesn't have a class name, show questions from all teachers
            teacher_ids = [t.id for t in User.query.filter_by(role='teacher').all()]
            
        # Debug log the teacher IDs
        logging.debug(f"Filtering questions for teachers: {teacher_ids}")
        
        # Get questions that haven't expired
        questions = Question.query.filter(
            Question.deadline > datetime.utcnow(),
            Question.teacher_id.in_(teacher_ids)
        ).all()
        
        logging.debug(f"Found {len(questions)} questions for student {current_user.id}")
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
        
        # Allow access if either:
        # 1. Both teacher and student have matching class_name (not empty), OR
        # 2. At least one of them has an empty class_name
        if question.teacher.class_name and current_user.class_name and question.teacher.class_name != current_user.class_name:
            flash("You are not authorized to view this question.")
            return redirect(url_for('home'))
            
        logging.debug(f"Student {current_user.id} with class '{current_user.class_name}' accessing question from teacher with class '{question.teacher.class_name}'")

        # Get all student submissions for this question
        all_submissions = Submission.query.filter_by(
            question_id=question_id,
            student_id=current_user.id
        ).order_by(Submission.version.desc()).all()
        
        # Get the best submission for display
        best_submission = Submission.query.filter_by(
            question_id=question_id,
            student_id=current_user.id,
            is_best_submission=True
        ).first()
        
        # Log submission status for debugging
        if best_submission:
            logging.debug(f"Found best submission (id: {best_submission.id}, version: {best_submission.version}) for student {current_user.id}")
        else:
            logging.debug(f"No submission found for student {current_user.id}, question {question_id}")
            
        # Get submission history for display
        submission_history = []
        for submission in all_submissions:
            submission_history.append({
                'id': submission.id,
                'version': submission.version,
                'date': submission.submission_date,
                'score': submission.total_marks,
                'is_best': submission.is_best_submission
            })
            
        logging.debug(f"Submission history: {submission_history}")

        return render_template('student/submit_answer.html', 
                             question=question,
                             submission=best_submission,
                             submission_history=submission_history)
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
    """Initial submission of an answer to a question."""
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
        logging.debug(f"Diagrams required: {question.requires_diagrams}")

        # Validate Gemini API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logging.error("Gemini API key not found")
            flash('System configuration error. Please contact administrator.')
            return redirect(url_for('view_question', question_id=question_id))

        # Get grading result with error handling
        try:
            logging.debug("Calling analyze_with_gemini")
            grading_result = analyze_with_gemini(
                question.question_text,
                answer,
                question.max_marks,
                diagrams_required=question.requires_diagrams
            )
            logging.debug(f"Received grading result: {grading_result}")

            if not grading_result or not isinstance(grading_result, dict):
                logging.error(f"Invalid grading result format: {grading_result}")
                flash('Error during grading. Please try again.')
                return redirect(url_for('view_question', question_id=question_id))

            # Validate required fields
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
            # First check if this is the student's first submission
            existing_submission = Submission.query.filter_by(
                student_id=current_user.id,
                question_id=question_id
            ).first()
            
            # If this is the first submission, version is 1, otherwise track as later version
            version = 1
            
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
                diagrams_feedback=str(grading_result['diagrams']['feedback']),
                version=version,
                is_best_submission=True  # First submission is always the best by default
            )

            db.session.add(submission)
            db.session.commit()
            logging.info(f"Successfully created submission: {submission.id}, version: {version}")

            # First show the grading result
            flash('Your submission has been graded successfully. You can now view the detailed review.')
            
            # Add question_id to the grading result for navigation
            grading_result['question_id'] = question_id
            
            # Then redirect back to the question page to see the review button
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

@app.route('/resubmit/<int:question_id>', methods=['POST'])
@login_required
def resubmit_answer(question_id):
    """Handle resubmission of an answer to a question with version tracking."""
    try:
        logging.debug(f"Starting resubmission for question_id: {question_id}")
        
        # Authorization check
        if current_user.role != 'student':
            logging.warning(f"Non-student user {current_user.id} attempted to resubmit")
            flash('Only students can submit answers')
            return redirect(url_for('home'))
            
        question = Question.query.get_or_404(question_id)
        answer = request.form.get('answer')

        if not answer:
            logging.warning("No answer provided in resubmission")
            flash('Please provide an answer')
            return redirect(url_for('view_question', question_id=question_id))
            
        # Get the current version number
        latest_submission = Submission.query.filter_by(
            student_id=current_user.id, 
            question_id=question_id
        ).order_by(Submission.version.desc()).first()
        
        new_version = 1
        if latest_submission:
            new_version = latest_submission.version + 1
            logging.debug(f"Creating new submission version {new_version}")

        # Validate Gemini API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logging.error("Gemini API key not found")
            flash('System configuration error. Please contact administrator.')
            return redirect(url_for('view_question', question_id=question_id))

        # Get grading result with error handling
        try:
            logging.debug("Calling analyze_with_gemini for resubmission")
            grading_result = analyze_with_gemini(
                question.question_text,
                answer,
                question.max_marks,
                diagrams_required=question.requires_diagrams
            )
            logging.debug(f"Received grading result: {grading_result}")

            if not grading_result or not isinstance(grading_result, dict):
                logging.error(f"Invalid grading result format: {grading_result}")
                flash('Error during grading. Please try again.')
                return redirect(url_for('view_question', question_id=question_id))

            # Validate required fields
            required_fields = ['introduction', 'main_body', 'conclusion', 'examples', 'diagrams', 'total_marks']
            if not all(field in grading_result for field in required_fields):
                logging.error(f"Missing fields in grading result: {grading_result}")
                flash('Error during grading. Please try again.')
                return redirect(url_for('view_question', question_id=question_id))

        except Exception as e:
            logging.error(f"Error in analyze_with_gemini during resubmission: {str(e)}")
            flash('Error during grading. Please try again.')
            return redirect(url_for('view_question', question_id=question_id))

        # Create new submission with version tracking
        try:
            new_submission = Submission(
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
                diagrams_feedback=str(grading_result['diagrams']['feedback']),
                version=new_version
            )

            # Check if this is a better score than previous versions
            if latest_submission and new_submission.total_marks > latest_submission.total_marks:
                # This is now the best submission
                # Update all other submissions to not be the best
                Submission.query.filter_by(
                    student_id=current_user.id, 
                    question_id=question_id
                ).update({Submission.is_best_submission: False})
                new_submission.is_best_submission = True
                logging.info(f"New submission {new_version} is better than previous versions")
            elif latest_submission and new_submission.total_marks <= latest_submission.total_marks:
                # The previous submission was better
                new_submission.is_best_submission = False
                logging.info(f"Previous submission remains the best")
            else:
                # This is the first submission
                new_submission.is_best_submission = True
                logging.info(f"First submission is automatically the best")

            db.session.add(new_submission)
            db.session.commit()
            logging.info(f"Successfully created resubmission: {new_submission.id}, version: {new_version}")

            # First show the grading result
            flash(f'Your resubmission (version {new_version}) has been graded successfully.')
            
            # Add question_id to the grading result for navigation
            grading_result['question_id'] = question_id
            
            # Then show the grading page
            return render_template('grading.html', 
                                result=grading_result,
                                submission_id=new_submission.id,
                                max_marks=question.max_marks)

        except Exception as e:
            logging.error(f"Error creating resubmission: {str(e)}")
            db.session.rollback()
            flash('Error saving resubmission. Please try again.')
            return redirect(url_for('view_question', question_id=question_id))

    except Exception as e:
        logging.error(f"Error in resubmit_answer: {str(e)}")
        db.session.rollback()
        flash('Error during resubmission. Please try again.')
        return redirect(url_for('view_question', question_id=question_id))

@app.route('/review/<int:submission_id>')
@login_required
def review(submission_id):
    try:
        submission = Submission.query.get_or_404(submission_id)
        question = submission.question

        # Debug logs to identify authorization issues
        logging.debug(f"Review requested for submission {submission_id}")
        logging.debug(f"Current user: {current_user.id}, role: {current_user.role}")
        logging.debug(f"Submission student_id: {submission.student_id}")
        logging.debug(f"Question teacher_id: {question.teacher_id}")

        # Allow both teachers and students who own the submission to view it
        is_teacher_owner = current_user.role == 'teacher' and question.teacher_id == current_user.id
        is_student_owner = current_user.role == 'student' and submission.student_id == current_user.id
        
        if is_teacher_owner or is_student_owner:
            logging.debug(f"Authorization granted: teacher_owner={is_teacher_owner}, student_owner={is_student_owner}")
            
            try:
                review_feedback = analyze_with_gemini(
                    question.question_text,
                    submission.answer,
                    question.max_marks,
                    mode='review'
                )
                return render_template('review.html', 
                                    feedback=review_feedback,
                                    submission=submission,
                                    question=question)
            except Exception as e:
                logging.error(f"Error generating AI review: {str(e)}")
                # Provide a basic review if AI fails
                return render_template('review.html', 
                                    feedback="AI review generation failed. Please try again later.",
                                    submission=submission,
                                    question=question)
        else:
            logging.warning(f"Unauthorized review attempt: user_id={current_user.id}, submission_id={submission_id}")
            flash("You are not authorized to review this submission.")
            return redirect(url_for('home'))
    except Exception as e:
        logging.error(f"Error accessing submission for review: {str(e)}")
        flash('Error generating review. Please try again.')
        return redirect(url_for('home'))

@app.route('/teacher/question/<int:question_id>/submissions')
@login_required
def view_submissions(question_id):
    """View all best submissions for a question (teacher only)."""
    try:
        # Authorization check
        if current_user.role != 'teacher':
            logging.warning(f"Non-teacher user {current_user.id} attempted to view submissions")
            flash('Only teachers can view all submissions')
            return redirect(url_for('home'))
            
        # Get the question
        question = Question.query.get_or_404(question_id)
        
        # Verify that the current teacher is the owner of this question
        if question.teacher_id != current_user.id:
            logging.warning(f"Teacher {current_user.id} tried to access question {question_id} owned by teacher {question.teacher_id}")
            flash("You are not authorized to view these submissions")
            return redirect(url_for('teacher_dashboard'))
            
        # Get only the best submission from each student
        best_submissions = Submission.query.filter_by(
            question_id=question_id,
            is_best_submission=True
        ).order_by(Submission.total_marks.desc()).all()
        
        logging.debug(f"Found {len(best_submissions)} best submissions for question {question_id}")
        
        return render_template(
            'teacher/submissions.html', 
            question=question, 
            submissions=best_submissions
        )
    
    except Exception as e:
        logging.error(f"Error viewing submissions for question {question_id}: {str(e)}")
        flash('Error loading submissions')
        return redirect(url_for('teacher_dashboard'))
        
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