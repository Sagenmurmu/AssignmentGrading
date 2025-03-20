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
    try:
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Normalize line breaks
        text = re.sub(r'[\r\n]+', '\n', text)
        return text.strip()
    except Exception as e:
        logging.error(f"Error cleaning text: {str(e)}")
        return text if text else ""

def extract_text_from_image(image_path):
    """Extract text from image using Gemini AI's vision capabilities."""
    try:
        # Initialize Gemini 1.5 Flash model
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Open and prepare the image
        with Image.open(image_path) as image:
            # Create a prompt for text extraction
            prompt = """
            Extract all text from this image.
            Requirements:
            1. Maintain original formatting and structure
            2. Preserve all text exactly as shown
            3. Keep paragraphs separate
            4. Include any headers or titles
            5. Maintain any bullet points or numbering
            """

            # Generate content from image
            response = model.generate_content([prompt, image])
            if not response or not response.text:
                raise ValueError("Empty response from Gemini API")

            extracted_text = response.text
            cleaned_text = clean_text(extracted_text)

            if not cleaned_text:
                raise ValueError("No text was extracted from the image")

            logging.info(f"Successfully extracted text from image: {image_path}")
            return cleaned_text

    except Exception as e:
        logging.error(f"Error extracting text from image {image_path}: {str(e)}")
        raise

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF by converting pages to images and using Gemini Vision."""
    try:
        # For now, return a message suggesting direct image upload
        return "PDF extraction is being updated. Please upload images directly for better results."
    except Exception as e:
        logging.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        raise

def analyze_with_gemini(question, answer, max_marks, mode='grade'):
    """Analyze text using Gemini AI with improved error handling."""
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        if mode == 'grade':
            # Calculate scaling factor
            scaling_factor = max_marks / 10

            prompt = f"""
            Grade this answer based on the following criteria:
            Question: {question}
            Student's Answer: {answer}
            Maximum marks: 10 (Will be scaled to {max_marks})

            Base Marking Distribution (Total 10 marks):
            - Introduction (4 marks - 40%): Evaluate clarity, context setting, and thesis statement
            - Main Body (4 marks - 40%): Evaluate content accuracy, depth of understanding, and logical flow
            - Conclusion (2 marks - 20%): Evaluate summary, closure, and connection to introduction

            Bonus Marks (Beyond base total):
            - Examples: Award up to 2 marks (20%) if explicitly required, or 1 mark (10%) if provided voluntarily
            - Diagrams: Award up to 2 marks (20%) if explicitly required, or 1 mark (10%) if provided voluntarily

            Provide the response in the following JSON format:
            {
                "introduction": {"marks": 0, "feedback": ""},
                "main_body": {"marks": 0, "feedback": ""},
                "conclusion": {"marks": 0, "feedback": ""},
                "examples": {"marks": 0, "feedback": ""},
                "diagrams": {"marks": 0, "feedback": ""},
                "ai_detection_score": 0
            }
            """

            # Add retry mechanism for API calls
            max_retries = 3
            retry_count = 0
            result = None

            while retry_count < max_retries:
                try:
                    response = model.generate_content(prompt)
                    if not response or not response.text:
                        raise ValueError("Empty response from Gemini API")

                    # Try to parse the response as JSON
                    try:
                        result = json.loads(response.text)
                        # Validate the response structure
                        required_fields = ['introduction', 'main_body', 'conclusion', 'examples', 'diagrams']
                        if all(field in result for field in required_fields):
                            break
                        else:
                            raise ValueError("Invalid response structure")
                    except json.JSONDecodeError:
                        raise ValueError("Invalid JSON response")

                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        logging.error(f"Failed to get valid response after {max_retries} attempts: {str(e)}")
                        raise
                    logging.warning(f"Retry {retry_count}/{max_retries} for Gemini API call")

            # Calculate scaled marks with validation
            scaled_result = {}
            for section in ['introduction', 'main_body', 'conclusion', 'examples', 'diagrams']:
                if not isinstance(result[section], dict):
                    result[section] = {'marks': 0, 'feedback': 'No feedback available'}

                section_max = max_marks * (0.4 if section in ['introduction', 'main_body'] else 0.2)
                scaled_result[section] = {
                    'marks': min(float(result[section].get('marks', 0)) * scaling_factor, section_max),
                    'feedback': str(result[section].get('feedback', 'No feedback available'))
                }

            # Calculate total marks
            base_marks = (scaled_result['introduction']['marks'] + 
                        scaled_result['main_body']['marks'] + 
                        scaled_result['conclusion']['marks'])

            bonus_marks = (scaled_result['examples']['marks'] + 
                         scaled_result['diagrams']['marks'])

            total_marks = min(base_marks + bonus_marks, max_marks)

            scaled_result['total_marks'] = total_marks
            scaled_result['ai_detection_score'] = float(result.get('ai_detection_score', 0))

            return scaled_result

        elif mode == 'review':
            prompt = f"""
            Provide detailed feedback and improvement suggestions for this answer:
            Question: {question}
            Student's Answer: {answer}

            Focus on:
            1. Strengths and what was done well
            2. Areas needing improvement
            3. Specific suggestions for each section
            4. How to improve examples and diagrams
            5. Writing style and clarity
            6. Critical thinking and analysis

            Provide actionable feedback that will help the student improve their answer quality.
            """

            response = model.generate_content(prompt)
            return response.text if response and response.text else "No feedback available"

    except Exception as e:
        logging.error(f"Error in Gemini AI analysis: {str(e)}")
        raise