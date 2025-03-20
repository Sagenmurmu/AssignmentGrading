import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import google.generativeai as genai
from models import db, Submission
from utils import extract_text_from_pdf, extract_text_from_image, analyze_with_gemini

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "your-secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///assignments.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure Gemini AI
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Initialize database
db.init_app(app)

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

with app.app_context():
    db.create_all()

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/extract', methods=['POST'])
def extract_text():
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(url_for('home'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('home'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(filepath)
            else:
                text = extract_text_from_image(filepath)
            
            return {'success': True, 'text': text}
        except Exception as e:
            logging.error(f"Error extracting text: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    return {'success': False, 'error': 'Invalid file type'}

@app.route('/grade', methods=['POST'])
def grade():
    question = request.form.get('question')
    answer = request.form.get('answer')
    max_marks = int(request.form.get('max_marks', 10))

    if not question or not answer:
        flash('Please provide both question and answer')
        return redirect(url_for('home'))

    try:
        grading_result = analyze_with_gemini(question, answer, max_marks)
        
        # Store submission in database
        submission = Submission(
            question=question,
            answer=answer,
            max_marks=max_marks,
            introduction_marks=grading_result['introduction']['marks'],
            main_body_marks=grading_result['main_body']['marks'],
            conclusion_marks=grading_result['conclusion']['marks'],
            examples_marks=grading_result['examples']['marks'],
            diagrams_marks=grading_result['diagrams']['marks'],
            total_marks=grading_result['total_marks'],
            ai_detection_score=grading_result['ai_detection_score']
        )
        db.session.add(submission)
        db.session.commit()

        return render_template('grading.html', 
                            result=grading_result, 
                            submission_id=submission.id,
                            max_marks=max_marks)
    except Exception as e:
        logging.error(f"Error during grading: {str(e)}")
        flash('Error during grading. Please try again.')
        return redirect(url_for('home'))

@app.route('/review/<int:submission_id>')
def review(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    
    try:
        review_feedback = analyze_with_gemini(
            submission.question,
            submission.answer,
            submission.max_marks,
            mode='review'
        )
        return render_template('review.html', feedback=review_feedback)
    except Exception as e:
        logging.error(f"Error generating review: {str(e)}")
        flash('Error generating review. Please try again.')
        return redirect(url_for('home'))
