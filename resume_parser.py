"""Lectura de CVs (PDF, DOCX, TXT): texto, habilidades, años de experiencia y estudios, con Gemini si hay permiso."""
import json
import os
import re
from datetime import datetime
from typing import Any, cast

import docx
import pypdf

import skill_catalog

try:
    from google import genai
    _GENAI_AVAILABLE = True
except (ImportError, Exception) as e:
    genai = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False
    print(f"Warning: google-genai not available: {e}")
from dotenv import load_dotenv

load_dotenv()

class resumeParser:
    def __init__(self) -> None:
        self.configure_genai()

        self.technical_skills = {k: list(v) for k, v in skill_catalog.TECHNICAL_SKILLS.items()}

        self.all_technical_skills = []
        for category in self.technical_skills.values():
            self.all_technical_skills.extend(category)

    def configure_genai(self) -> None:
        if not getattr(self, '__module__', None) and not globals().get('_GENAI_AVAILABLE', False):
            self.use_ai = False
            print("Warning: AI API not available (import failed). Using regex-based parsing.")
            return

        api_key = os.getenv("GEMINI_API_KEY")  # Internal: Google Gemini
        if api_key:
            try:
                if 'genai' in globals() and genai is not None:
                    self.client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
                    self.model_name = os.getenv('GEMINI_PARSER_MODEL', 'gemini-2.5-flash-lite')
                    self.use_ai = True
                    print("✅ AI parser configured successfully")
                else:
                    self.use_ai = False
            except Exception as e:
                print(f"Error configuring AI parser: {e}")
                self.use_ai = False
        else:
            self.use_ai = False
            print("Warning: AI API key not found. Using regex-based parsing.")

    def extract_text_from_file(self, file_path: str) -> str:

        text = ""
        file_extension = os.path.splitext(file_path)[1].lower()

        try:
            if file_extension == '.pdf':
                with open(file_path, 'rb') as file:
                    pdf_reader = pypdf.PdfReader(file)
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"

            elif file_extension == '.docx':
                doc = docx.Document(file_path)
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"

            elif file_extension == '.txt':
                with open(file_path, encoding='utf-8') as file:
                    text = file.read()

            return text.strip()
        except Exception as e:
            print(f"Error extracting text from {file_path}: {e!s}")
            return ""

    def extract_skills(self, text: str) -> list[str]:

        text_lower = text.lower()
        found_skills: list[str] = []

        for skill in self.all_technical_skills:

            pattern = r'\b' + re.escape(skill.lower()) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.append(skill)


        return list(set(found_skills))

    def parse_date_range(self, date_string: str) -> float:

        try:
            # Normalize separators
            date_string = date_string.replace('–', '-').replace('—', '-').replace(' - ', '-')

            # Month name mapping
            month_map = {
                'jan': 1, 'january': 1,
                'feb': 2, 'february': 2,
                'mar': 3, 'march': 3,
                'apr': 4, 'april': 4,
                'may': 5,
                'jun': 6, 'june': 6,
                'jul': 7, 'july': 7,
                'aug': 8, 'august': 8,
                'sep': 9, 'sept': 9, 'september': 9,
                'oct': 10, 'october': 10,
                'nov': 11, 'november': 11,
                'dec': 12, 'december': 12
            }

            # Enhanced date patterns with month names
            date_patterns = [
                (r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s,]+(\d{4})\s*-\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s,]+(\d{4})', 'month_year'),
                (r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s,]+(\d{4})\s*-\s*(?:present|current|today|now)', 'month_year_present'),
                (r'(\d{1,2})/(\d{4})\s*-\s*(\d{1,2})/(\d{4})', 'mm_yyyy'),
                (r'(\d{1,2})/(\d{4})\s*-\s*(?:present|current|today|now)', 'mm_yyyy_present'),
                (r'(\d{4})\s*-\s*(\d{4})', 'yyyy'),
                (r'(\d{4})\s*-\s*(?:present|current|today|now)', 'yyyy_present'),
            ]

            for pattern, pattern_type in date_patterns:
                match = re.search(pattern, date_string, re.IGNORECASE)
                if match:
                    groups = match.groups()

                    try:
                        if pattern_type == 'month_year':
                            start_month_str, start_year, end_month_str, end_year = groups
                            start_month = month_map.get(start_month_str.lower()[:3], 1)
                            end_month = month_map.get(end_month_str.lower()[:3], 12)
                            start_date = datetime(int(start_year), start_month, 1)
                            end_date = datetime(int(end_year), end_month, 1)

                        elif pattern_type == 'month_year_present':
                            start_month_str, start_year = groups
                            start_month = month_map.get(start_month_str.lower()[:3], 1)
                            start_date = datetime(int(start_year), start_month, 1)
                            end_date = datetime.now()

                        elif pattern_type == 'mm_yyyy':
                            start_mm, start_year, end_mm, end_year = groups
                            start_date = datetime(int(start_year), int(start_mm), 1)
                            end_date = datetime(int(end_year), int(end_mm), 1)

                        elif pattern_type == 'mm_yyyy_present':
                            start_mm, start_year = groups
                            start_date = datetime(int(start_year), int(start_mm), 1)
                            end_date = datetime.now()

                        elif pattern_type == 'yyyy':
                            start_year, end_year = groups
                            start_date = datetime(int(start_year), 1, 1)
                            end_date = datetime(int(end_year), 12, 31)

                        elif pattern_type == 'yyyy_present':
                            start_year = groups[0]
                            start_date = datetime(int(start_year), 1, 1)
                            end_date = datetime.now()

                        years_diff = (end_date - start_date).days / 365.25
                        return max(years_diff, 0)

                    except (ValueError, IndexError) as e:
                        print(f"Error parsing date components: {e!s}")
                        continue

            return 0
        except Exception as e:
            print(f"Error parsing date range '{date_string}': {e!s}")
            return 0

    def extract_experience_years(self, text: str) -> float:
        """Extract years of experience from text using multiple methods"""
        text_lower = text.lower()
        years: list[float] = []


        explicit_patterns = [
            r'(\d+)\+?\s*years?\s*(?:of\s*)?experience',
            r'(\d+)\+?\s*years?\s*in\s+(?:software|development|programming|it|tech|data|analytics|engineering)',
            r'experience\s*:?\s*(\d+)\+?\s*years?',
            r'(\d+)\+?\s*years?\s*(?:working|developing|programming)',
            r'over\s+(\d+)\s*years?',
            r'more\s+than\s+(\d+)\s*years?',
        ]

        for pattern in explicit_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    years.append(int(match))
                except ValueError:
                    continue


        work_experience_years = self.calculate_work_experience(text)
        if work_experience_years > 0:
            years.append(work_experience_years)


        return max(years) if years else 0

    def calculate_work_experience(self, text: str) -> float:
        """Calculate total work experience from job date ranges, excluding internships"""
        total_years: float = 0
        lines = text.split('\n')
        # cada línea con fechas cuenta una sola vez, aunque la vean como contexto las 3 líneas anteriores
        seen_dates = set()
        # fechas descartadas por estar junto a estudios: solo las cuenta una línea con un puesto
        skipped_dates = set()

        # Track if we're in experience section (helpful but not required)
        in_education_section = False
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Detect section markers
            if re.match(r'^experience\s*$', line.lower()) or ('professional' in line.lower() and 'experience' in line.lower()):
                in_education_section = False
                i += 1
                continue

            if re.match(r'^education\s*$', line.lower()) or re.match(r'^projects?\s*$', line.lower()):
                in_education_section = True

            # Skip lines in education section
            if in_education_section:
                i += 1
                continue

            if line:
                # Get next few lines for context
                next_lines = [lines[i + j].strip() for j in range(1, min(4, len(lines) - i)) if i + j < len(lines)]

                # Look for date patterns in current line or next lines
                all_context = [line, *next_lines]

                for context_index, context_line in enumerate(all_context):
                    # Enhanced date patterns to catch more formats
                    date_patterns = [
                        r'\d{1,2}/\d{4}\s*[–—-]\s*\d{1,2}/\d{4}',  # MM/YYYY – MM/YYYY
                        r'\d{1,2}/\d{4}\s*[–—-]\s*(?:present|current|today|now)',  # MM/YYYY – Present
                        r'\d{4}\s*[–—-]\s*\d{4}',  # YYYY – YYYY
                        r'\d{4}\s*[–—-]\s*(?:present|current|today|now)',  # YYYY – Present
                        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,]+\d{4}\s*[–—-]\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,]+\d{4}',  # Month YYYY - Month YYYY
                        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,]+\d{4}\s*[–—-]\s*(?:present|current)',  # Month YYYY - Present
                    ]

                    for pattern in date_patterns:
                        match = re.search(pattern, context_line, re.IGNORECASE)
                        if match:
                            date_range = match.group()
                            date_index = i + context_index
                            if date_index in seen_dates:
                                break

                            # Build job context from current line and matched line
                            job_context = line
                            if context_index > 0:
                                job_context += " " + context_line

                            # Skip if it's an internship or education
                            skip_keywords = [
                                'intern', 'internship', 'student', 'university',
                                'college', 'degree', 'bachelor', 'master', 'phd',
                                'education', 'course', 'certification'
                            ]

                            should_skip = any(keyword in job_context.lower() for keyword in skip_keywords)

                            # Prioritize lines with job-related keywords
                            job_keywords = [
                                'engineer', 'developer', 'analyst', 'manager', 'specialist',
                                'administrator', 'consultant', 'architect', 'lead', 'senior',
                                'junior', 'associate', 'coordinator', 'director', 'technician'
                            ]

                            has_job_title = any(keyword in job_context.lower() for keyword in job_keywords)

                            # Only count if it looks like work experience
                            counts = not should_skip or (has_job_title and 'intern' not in job_context.lower())
                            if date_index in skipped_dates and not has_job_title:
                                counts = False
                            if counts:
                                seen_dates.add(date_index)
                                years_for_job = self.parse_date_range(date_range)
                                if years_for_job > 0:  # Only count positive years
                                    total_years += years_for_job
                                    print(f"Found work experience: {line} - {date_range} = {years_for_job:.1f} years")
                            else:
                                skipped_dates.add(date_index)
                                print(f"Skipping non-work experience: {job_context[:50]}... - {date_range}")

                            break  # Move to next line once we found a date
                    else:
                        continue
                    break  # Move to next line once we found a date

            i += 1

        # Cap at realistic maximum
        return min(total_years, 20)

    def extract_education(self, text: str) -> list[str]:
        """Extract education information, excluding internship locations"""
        education_keywords = [
            'bachelor', 'master', 'phd', 'doctorate', 'degree', 'university',
            'college', 'institute', 'b.s.', 'b.a.', 'm.s.', 'm.a.', 'mba',
            'b.sc', 'b.tech', 'm.tech', 'mca', 'bca'
        ]

        education_info: list[str] = []
        lines = text.split('\n')


        in_education_section = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            line_lower = line_stripped.lower()


            if re.match(r'^education\s*$', line_lower):
                in_education_section = True
                continue


            if in_education_section and re.match(r'^(experience|projects?|skills|summary)\s*$', line_lower):
                break


            if in_education_section or any(keyword in line_lower for keyword in education_keywords):

                internship_indicators = ['intern', 'internship', 'remote', 'iit bombay', 'inc', 'llc', 'corp']
                if any(indicator in line_lower for indicator in internship_indicators):
                    continue


                if any(keyword in line_lower for keyword in education_keywords):
                    cleaned_line = line_stripped
                    if len(cleaned_line) > 10:
                        education_info.append(cleaned_line)

        return education_info

    def parse_with_ai(self, text: str) -> dict[str, Any] | None:
        if not self.use_ai:
            return None

        prompt = f"""
        You are an expert Resume Parser. Extract the following information from the resume text below.
        Return ONLY a valid JSON object with no markdown formatting.

        JSON Structure:
        {{
            "skills": ["skill1", "skill2", ...],
            "experience_years": <number (float)>,
            "education": ["degree 1", "degree 2", ...],
            "summary": "<brief professional summary>"
        }}

        Rules:
        1. experience_years: Calculate the TOTAL years of PROFESSIONAL work experience.
           - EXCLUDE internships, volunteer work, and education periods unless they were full-time professional roles.
           - If there are overlapping roles, count the time only once.
           - Round to 1 decimal place.
        2. skills: Extract technical skills, programming languages, tools, and frameworks.
        3. education: Extract degrees and universities.

        Resume Text:
        {text}
        """

        try:
            import accounts
            import ai_usage
            if accounts.ai_consent_missing():
                print("La cuenta no dio permiso para usar la IA; el CV se parsea sin IA")
                return None
            if ai_usage.budget_exceeded():
                print("Límite mensual de tokens de IA alcanzado; el CV se parsea sin IA")
                return None
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
            usage = getattr(response, 'usage_metadata', None)
            ai_usage.record(
                getattr(usage, 'prompt_token_count', 0) or 0,
                (getattr(usage, 'candidates_token_count', 0) or 0) + (getattr(usage, 'thoughts_token_count', 0) or 0),
            )
            json_str = (response.text or '').strip()
            # Clean up potential markdown code blocks
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]

            return cast(dict[str, Any], json.loads(json_str.strip()))
        except Exception as e:
            print(f"Error parsing with AI: {e}")
            return None

    def parse_resume(self, file_path: str) -> dict[str, Any] | None:

        text = self.extract_text_from_file(file_path)

        if not text:
            return None

        print("Parsing resume...")
        print(f"Text length: {len(text)} characters")

        profile: dict[str, Any] = {
            'raw_text': text,
            'skills': [],
            'experience_years': 0,
            'education': []
        }

        # Try AI parsing first
        ai_result = self.parse_with_ai(text)

        if ai_result:
            print("✅ Successfully parsed resume with AI")
            profile['skills'] = ai_result.get('skills', [])
            profile['experience_years'] = ai_result.get('experience_years', 0)
            profile['education'] = ai_result.get('education', [])

            # Fallback for empty skills if AI fails to extract them but gets other things
            if not profile['skills']:
                 profile['skills'] = self.extract_skills(text)
        else:
            print("⚠️ AI parsing failed or disabled. Falling back to regex parsing")
            profile['skills'] = self.extract_skills(text)
            profile['experience_years'] = self.extract_experience_years(text)
            profile['education'] = self.extract_education(text)

        print(f"Found {len(profile['skills'])} skills")
        print(f"Calculated {profile['experience_years']} years of experience")
        print(f"Found {len(profile['education'])} education entries")

        return profile


