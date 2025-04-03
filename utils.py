import os
import logging
import json
import re
from PIL import Image
import google.generativeai as genai


logging.basicConfig(level=logging.DEBUG)

def clean_text(text):
    
    try:

        text = re.sub(r'\s+', ' ', text)
        
        text = re.sub(r'[\r\n]+', '\n', text)
        return text.strip()
    except Exception as e:
        logging.error(f"Error cleaning text: {str(e)}")
        return text if text else ""

def extract_text_from_image(image_path):
    
    try:
        api_key = "your gemini api key"

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

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
    
    try:
        return "PDF extraction is being updated. Please upload images directly for better results."
    except Exception as e:
        logging.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        raise

def analyze_with_gemini(question, answer, max_marks, mode='grade', diagrams_required=False):
    
    try:
        api_key = "your gemini api key"

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

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
   - Diagrams: IMPORTANT - Mark as 0 unless explicit diagrams are present. Text descriptions without actual diagrams should get 0 marks.
   - Only award marks for diagrams if there are actual diagrams or visual elements in the answer, not just text descriptions.

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

                    
                    text = response.text.strip()
                    start_idx = text.find('{')
                    end_idx = text.rfind('}') + 1

                    if start_idx == -1 or end_idx <= start_idx:
                        raise ValueError("No valid JSON found in response")

                    json_str = text[start_idx:end_idx]
                    logging.debug(f"Extracted JSON string: {json_str}")

                    
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

            
            for section in ['examples', 'diagrams']:
                try:
                    marks = float(result[section]['marks'])
                    
                    
                    if section == 'diagrams':
                        diagram_feedback = str(result[section]['feedback']).lower()
                        diagram_indicators = ['diagram', 'figure', 'chart', 'graph', 'illustration', 'visual']
                        has_diagram_content = any(indicator in diagram_feedback for indicator in diagram_indicators)
                        
                        
                        if not has_diagram_content:
                            marks = 0
                            result[section]['feedback'] = "No diagrams provided in the submission"
                    
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