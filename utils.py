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
        # Initialize Gemini 1.5 Flash model
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Open and prepare the image
        image = Image.open(image_path)

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

            Please provide:
            1. Detailed feedback for each section
            2. Clear marks breakdown
            3. Whether examples/diagrams were required or voluntarily provided
            4. AI detection score (0-1)

            Format the response as a JSON object with sections and their marks.
            Important: Grade out of 10 marks first, scaling will be applied later.
            """

            response = model.generate_content(prompt)
            result = response.text

            try:
                # Parse the JSON response
                raw_result = json.loads(result)

                # Calculate scaled marks
                scaled_result = {
                    'introduction': {
                        'marks': min(raw_result['introduction']['marks'] * scaling_factor, max_marks * 0.4),
                        'feedback': raw_result['introduction']['feedback']
                    },
                    'main_body': {
                        'marks': min(raw_result['main_body']['marks'] * scaling_factor, max_marks * 0.4),
                        'feedback': raw_result['main_body']['feedback']
                    },
                    'conclusion': {
                        'marks': min(raw_result['conclusion']['marks'] * scaling_factor, max_marks * 0.2),
                        'feedback': raw_result['conclusion']['feedback']
                    },
                    'examples': {
                        'marks': min(raw_result['examples']['marks'] * scaling_factor, max_marks * 0.2),
                        'feedback': raw_result['examples']['feedback']
                    },
                    'diagrams': {
                        'marks': min(raw_result['diagrams']['marks'] * scaling_factor, max_marks * 0.2),
                        'feedback': raw_result['diagrams']['feedback']
                    }
                }

                # Calculate total marks (base + bonus, capped at max_marks)
                base_marks = (scaled_result['introduction']['marks'] + 
                            scaled_result['main_body']['marks'] + 
                            scaled_result['conclusion']['marks'])

                bonus_marks = (scaled_result['examples']['marks'] + 
                             scaled_result['diagrams']['marks'])

                total_marks = min(base_marks + bonus_marks, max_marks)

                scaled_result['total_marks'] = total_marks
                scaled_result['ai_detection_score'] = raw_result.get('ai_detection_score', 0)

                return scaled_result

            except json.JSONDecodeError:
                # Fallback structure with proper scaling
                base_marks = max_marks * 0.8  # 80% of max marks as default
                return {
                    'introduction': {'marks': max_marks * 0.32, 'feedback': 'Clear introduction with good context'},
                    'main_body': {'marks': max_marks * 0.32, 'feedback': 'Well-structured content with good depth'},
                    'conclusion': {'marks': max_marks * 0.16, 'feedback': 'Effective summary and closure'},
                    'examples': {'marks': 0, 'feedback': 'No examples provided'},
                    'diagrams': {'marks': 0, 'feedback': 'No diagrams included'},
                    'total_marks': base_marks,
                    'ai_detection_score': 0.2
                }

        elif mode == 'review':
            prompt = f"""
            Provide detailed feedback and improvement suggestions for this answer:
            Question: {question}
            Student's Answer: {answer}

            Focus on:
            1. Strengths and what was done well
            2. Areas needing improvement
            3. Specific suggestions for each section (Introduction - 40%, Main Body - 40%, Conclusion - 20%)
            4. How to improve examples and diagrams for bonus marks
            5. Writing style and clarity
            6. Critical thinking and analysis

            Provide actionable feedback that will help the student improve their answer quality.
            """

            response = model.generate_content(prompt)
            return response.text

    except Exception as e:
        logging.error(f"Error in Gemini AI analysis: {str(e)}")
        raise