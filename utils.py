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
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        with Image.open(image_path) as image:
            prompt = """Extract all text from this image.
            Maintain original formatting, structure, and preserve text exactly as shown."""

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
    """Extract text from PDF."""
    try:
        return "PDF extraction is being updated. Please upload images directly for better results."
    except Exception as e:
        logging.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        raise

def analyze_with_gemini(question, answer, max_marks, mode='grade', diagrams_required=False):
    """Analyze text using Gemini AI with improved error handling."""
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        if mode == 'grade':
            scaling_factor = max_marks / 10

            prompt = f"""You are a grading assistant. Your task is to grade an answer and return ONLY a JSON object without any additional text or explanation.

Question: {question}
Student Answer: {answer}
Maximum marks: {max_marks}
Diagrams Required: {"Yes" if diagrams_required else "No"}

Grading Rules:
1. Base scoring (out of 10):
   - Introduction (4 marks max - 40%)
   - Main Body (4 marks max - 40%)
   - Conclusion (2 marks max - 20%)
2. Bonus scoring:
   - Examples: Mark as 0 if none found
   - Diagrams: Mark as 0 if none found
   - Only grade diagrams if they are present in the answer

Return the following JSON structure EXACTLY, with no additional text:
{{
    "introduction": {{
        "marks": <number 0-4>,
        "feedback": "<clear feedback>"
    }},
    "main_body": {{
        "marks": <number 0-4>,
        "feedback": "<clear feedback>"
    }},
    "conclusion": {{
        "marks": <number 0-2>,
        "feedback": "<clear feedback>"
    }},
    "examples": {{
        "marks": <number 0-2>,
        "feedback": "<clear feedback>"
    }},
    "diagrams": {{
        "marks": <number 0-2>,
        "feedback": "<clear feedback>"
    }},
    "ai_detection_score": <number 0-1>
}}"""

            max_retries = 3
            retry_count = 0
            result = None

            while retry_count < max_retries:
                try:
                    response = model.generate_content(prompt)
                    logging.debug(f"Raw API response: {response.text}")

                    if not response or not response.text:
                        raise ValueError("Empty response from Gemini API")

                    # Extract JSON from response
                    text = response.text.strip()
                    start_idx = text.find('{')
                    end_idx = text.rfind('}') + 1

                    if start_idx == -1 or end_idx <= start_idx:
                        raise ValueError("No valid JSON found in response")

                    json_str = text[start_idx:end_idx]
                    logging.debug(f"Extracted JSON string: {json_str}")

                    # Parse and validate JSON structure
                    result = json.loads(json_str)

                    required_fields = ['introduction', 'main_body', 'conclusion', 'examples', 'diagrams']
                    for field in required_fields:
                        if field not in result:
                            raise ValueError(f"Missing required field: {field}")
                        if not isinstance(result[field], dict):
                            result[field] = {'marks': 0, 'feedback': 'No feedback available'}
                        elif 'marks' not in result[field] or 'feedback' not in result[field]:
                            result[field] = {'marks': 0, 'feedback': 'No feedback available'}

                    if 'ai_detection_score' not in result:
                        result['ai_detection_score'] = 0.0

                    break
                except Exception as e:
                    retry_count += 1
                    logging.error(f"Attempt {retry_count}/{max_retries} failed: {str(e)}")
                    if retry_count >= max_retries:
                        raise ValueError(f"Failed to get valid response after {max_retries} attempts")

            # Calculate scaled marks
            scaled_result = {}
            for section in ['introduction', 'main_body', 'conclusion']:
                try:
                    marks = float(result[section]['marks'])
                    section_max = max_marks * (0.4 if section in ['introduction', 'main_body'] else 0.2)
                    scaled_result[section] = {
                        'marks': min(marks * scaling_factor, section_max),
                        'feedback': str(result[section]['feedback'])
                    }
                except (ValueError, TypeError):
                    scaled_result[section] = {
                        'marks': 0,
                        'feedback': 'Error calculating marks'
                    }

            # Handle bonus marks (examples and diagrams)
            for section in ['examples', 'diagrams']:
                try:
                    marks = float(result[section]['marks'])
                    if marks > 0:  # Only if content is present
                        bonus_max = max_marks * (0.2 if (section == 'diagrams' and diagrams_required) else 0.1)
                        scaled_result[section] = {
                            'marks': min(marks * scaling_factor, bonus_max),
                            'feedback': str(result[section]['feedback'])
                        }
                    else:
                        scaled_result[section] = {
                            'marks': 0,
                            'feedback': f"No {section} provided"
                        }
                except (ValueError, TypeError):
                    scaled_result[section] = {
                        'marks': 0,
                        'feedback': 'Error calculating marks'
                    }

            # Calculate total marks
            base_marks = sum(scaled_result[s]['marks'] for s in ['introduction', 'main_body', 'conclusion'])
            bonus_marks = sum(scaled_result[s]['marks'] for s in ['examples', 'diagrams'])
            total_marks = min(base_marks + bonus_marks, max_marks)

            scaled_result['total_marks'] = total_marks
            scaled_result['ai_detection_score'] = float(result.get('ai_detection_score', 0))

            logging.info("Successfully generated grading result")
            logging.debug(f"Final scaled result: {scaled_result}")
            return scaled_result

        elif mode == 'review':
            prompt = f"""Review this answer and provide feedback:
            Question: {question}
            Student's Answer: {answer}

            Focus on strengths, areas for improvement, and specific suggestions."""

            response = model.generate_content(prompt)
            return response.text if response and response.text else "No feedback available"

    except Exception as e:
        logging.error(f"Error in Gemini AI analysis: {str(e)}")
        raise