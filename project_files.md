# AI Assignment Grading Platform Files

## Core Application Files

### app.py
```python
# Main Flask application file containing:
- Authentication routes (login, register, logout)
- Student routes (view questions, submit answers)
- Teacher routes (dashboard, create questions)
- File handling and text extraction
- Review and grading functionality
```

### models.py
```python
# Database models including:
- User (students and teachers)
- Question (assignments)
- Submission (student answers and grades)
```

### utils.py
```python
# Utility functions including:
- Text extraction from images and PDFs
- Integration with Google's Gemini AI
- Grading logic and analysis
```

## Templates

### templates/base.html
Base template with common layout and navigation

### templates/student/submit_answer.html
Student interface for:
- Viewing assignment details
- Uploading answers
- Viewing grades and feedback

### templates/student/questions.html
Lists available assignments with:
- Assignment details
- Submission deadlines
- Required components (examples/diagrams)

### templates/grading.html
Displays grading results with:
- Section-wise scores
- Detailed feedback
- AI detection metrics

## Static Files

### static/css/style.css
Custom styling for:
- File upload interface
- Grading sections
- Review display

### static/js/main.js
Client-side functionality for:
- File drag-and-drop
- Text extraction
- Form handling

## Features
1. Student Features:
   - View available assignments
   - Submit answers with file upload
   - Get AI-powered grading
   - Access detailed feedback

2. Teacher Features:
   - Create and manage assignments
   - Set grading criteria
   - Review submissions

3. Grading System:
   - Base score (Introduction, Main Body, Conclusion)
   - Bonus marks (Examples, Diagrams)
   - AI-powered analysis
   - Detailed feedback generation

4. Security:
   - Role-based access control
   - Secure file handling
   - Data validation
