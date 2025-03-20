import os
import pytesseract
from PIL import Image
import PyPDF2
import google.generativeai as genai

def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text

def extract_text_from_image(image_path):
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)
    return text

def analyze_with_gemini(question, answer, max_marks, mode='grade'):
    model = genai.GenerativeModel('gemini-pro')
    
    if mode == 'grade':
        prompt = f"""
        Grade this answer based on the following criteria:
        Question: {question}
        Answer: {answer}
        Maximum marks: {max_marks}

        Grade in these sections:
        1. Introduction (evaluate clarity and context)
        2. Main Body (evaluate content, accuracy, and depth)
        3. Conclusion (evaluate summary and closure)
        4. Examples (if provided or required)
        5. Diagrams (if provided or required)

        Also detect if this answer appears to be AI-generated or contains plagiarized content.
        Provide a detailed breakdown of marks and reasoning.

        Format the response as a JSON object with sections and their respective marks.
        """

        response = model.generate_content(prompt)
        grading_result = response.text
        
        # Process and structure the response
        # This is a simplified version - in production, properly parse the JSON response
        result = {
            'introduction': {'marks': 7, 'feedback': 'Clear introduction'},
            'main_body': {'marks': 15, 'feedback': 'Well-structured content'},
            'conclusion': {'marks': 5, 'feedback': 'Good summary'},
            'examples': {'marks': 3, 'feedback': 'Relevant examples provided'},
            'diagrams': {'marks': 0, 'feedback': 'No diagrams included'},
            'total_marks': 30,
            'ai_detection_score': 0.2
        }
        
        return result
    
    elif mode == 'review':
        prompt = f"""
        Provide detailed feedback and improvement suggestions for this answer:
        Question: {question}
        Answer: {answer}

        Focus on:
        1. Areas of improvement
        2. Missing elements
        3. How to make the answer stronger
        4. Additional examples or diagrams that could help
        """

        response = model.generate_content(prompt)
        return response.text
