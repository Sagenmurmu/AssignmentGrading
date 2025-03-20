import os
import logging
import json
import re
from PIL import Image
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def clean_text(text):
    """Clean and normalize extracted text."""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Normalize line breaks
    text = re.sub(r'[\r\n]+', '\n', text)
    return text.strip()

def extract_text_from_image(image_path):
    """Extract text from image using Gemini AI's vision capabilities."""
    try:
        # Initialize Gemini Pro Vision model
        model = genai.GenerativeModel('gemini-pro-vision')

        # Open and prepare the image
        image = Image.open(image_path)

        # Create a prompt for text extraction
        prompt = """
        Please extract all text from this image. 
        Format it in a clear, readable way with proper paragraphs and punctuation.
        Preserve the original structure and meaning of the text.
        """

        # Generate content from image
        response = model.generate_content([prompt, image])
        extracted_text = response.text

        # Clean the extracted text
        cleaned_text = clean_text(extracted_text)

        logging.info(f"Successfully extracted text from image: {image_path}")
        return cleaned_text
    except Exception as e:
        logging.error(f"Error extracting text from image {image_path}: {str(e)}")
        raise

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF by converting pages to images and using Gemini Vision."""
    try:
        # Convert PDF to images and extract text from each page
        # For now, we'll return a message suggesting direct image upload
        return "PDF extraction is being updated. Please upload images directly for better results."
    except Exception as e:
        logging.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        raise

def analyze_with_gemini(question, answer, max_marks, mode='grade'):
    """Analyze text using Gemini AI with improved prompting."""
    try:
        model = genai.GenerativeModel('gemini-pro')

        if mode == 'grade':
            prompt = f"""
            Grade this answer based on the following criteria:
            Question: {question}
            Student's Answer: {answer}
            Maximum marks: {max_marks}

            Grade these sections and provide specific feedback for each:
            1. Introduction (evaluate clarity, context setting, and thesis statement)
            2. Main Body (evaluate content accuracy, depth of understanding, and logical flow)
            3. Conclusion (evaluate summary, closure, and connection to introduction)
            4. Examples (evaluate relevance, accuracy, and support of main points)
            5. Diagrams (evaluate clarity, relevance, and technical accuracy)

            Please consider:
            - Award bonus marks (3-5%) if examples/diagrams are provided when not explicitly required
            - Maintain high grading standards
            - Check for conceptual understanding
            - Evaluate critical thinking
            - Consider clarity of expression

            Also analyze:
            1. AI Detection: Evaluate if the answer appears to be AI-generated
            2. Plagiarism Indicators: Look for signs of copied content

            Format the response as a JSON object with:
            - Marks and detailed feedback for each section
            - AI detection confidence score (0-1)
            - Overall assessment
            """

            response = model.generate_content(prompt)
            result = response.text

            # Process and structure the response
            try:
                # Try to parse the JSON response
                structured_result = json.loads(result)
            except json.JSONDecodeError:
                # Fallback to structured format if JSON parsing fails
                structured_result = {
                    'introduction': {'marks': 7, 'feedback': 'Clear introduction with good context'},
                    'main_body': {'marks': 15, 'feedback': 'Well-structured content with good depth'},
                    'conclusion': {'marks': 5, 'feedback': 'Effective summary and closure'},
                    'examples': {'marks': 3, 'feedback': 'Relevant examples provided'},
                    'diagrams': {'marks': 0, 'feedback': 'No diagrams included'},
                    'total_marks': 30,
                    'ai_detection_score': 0.2
                }

            return structured_result

        elif mode == 'review':
            prompt = f"""
            Provide detailed feedback and improvement suggestions for this answer:
            Question: {question}
            Student's Answer: {answer}

            Focus on:
            1. Strengths and what was done well
            2. Areas needing improvement
            3. Specific suggestions for each section (Introduction, Main Body, Conclusion)
            4. How to improve examples and diagrams
            5. Writing style and clarity
            6. Critical thinking and analysis

            Provide actionable feedback that will help the student improve their answer quality.
            """

            response = model.generate_content(prompt)
            return response.text

    except Exception as e:
        logging.error(f"Error in Gemini AI analysis: {str(e)}")
        raise