
import re
import os
import pandas as pd
import docx
import PyPDF2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
try:
    import spacy
    _SPACY_AVAILABLE = True
except (ImportError, Exception):
    spacy = None
    _SPACY_AVAILABLE = False
from collections import Counter
import json
from datetime import datetime

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except (ImportError, Exception) as e:
    genai = None
    _GENAI_AVAILABLE = False
    print(f"Warning: google.generativeai not available: {e}")
from dotenv import load_dotenv

load_dotenv()

class resumeParser:
    def __init__(self):
        
        try:
            if _SPACY_AVAILABLE:
                self.nlp = spacy.load("en_core_web_sm")
            else:
                self.nlp = None
        except OSError:
            print("Warning: spaCy model not found. Install with: python -m spacy download en_core_web_sm")
            self.nlp = None
            
        self.configure_genai()
        
        self.technical_skills = {
            'programming_languages': [
                'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'php', 'ruby', 
                'go', 'rust', 'kotlin', 'swift', 'scala', 'r', 'matlab', 'sql', 'html', 
                'css', 'bash', 'powershell', 'perl', 'vba', 'pl/sql', 'plsql'
            ],
            'frameworks': [
                'react', 'angular', 'vue', 'django', 'flask', 'spring', 'express', 
                'laravel', 'rails', 'asp.net', 'bootstrap', 'jquery', 'node.js', 
                'next.js', 'nuxt.js', 'svelte', 'fastapi'
            ],
            'databases': [
                'mysql', 'postgresql', 'postgres', 'mongodb', 'redis', 'elasticsearch', 'sqlite', 
                'oracle', 'sql server', 'cassandra', 'dynamodb', 'firebase', 'snowflake', 'redshift'
            ],
            'cloud_platforms': [
                'aws', 'azure', 'google cloud', 'gcp', 'heroku', 'digitalocean', 
                'linode', 'cloudflare', 'glue', 's3'
            ],
            'tools': [
                'git', 'docker', 'kubernetes', 'jenkins', 'terraform', 'ansible', 
                'vagrant', 'webpack', 'gulp', 'grunt', 'npm', 'yarn', 'maven', 
                'gradle', 'jira', 'confluence', 'slack', 'trello', 'airflow', 'kafka',
                'spark', 'apache spark', 'apache flink', 'flink', 'selenium'
            ],
            'data_science': [
                'pandas', 'numpy', 'scikit-learn', 'sklearn', 'tensorflow', 'pytorch', 'keras', 
                'matplotlib', 'seaborn', 'plotly', 'jupyter', 'tableau', 'power bi', 'powerbi',
                'excel', 'regression', 'hypothesis testing', 'a/b testing', 'outlier detection'
            ]
        }
        
        self.all_technical_skills = []
        for category in self.technical_skills.values():
            self.all_technical_skills.extend(category)

    def configure_genai(self):
        if not getattr(self, '__module__', None) and not globals().get('_GENAI_AVAILABLE', False):
            self.use_ai = False
            print("Warning: AI API not available (import failed). Using regex-based parsing.")
            return

        api_key = os.getenv("GEMINI_API_KEY")  # Internal: Google Gemini
        if api_key:
            try:
                if 'genai' in globals() and genai is not None:
                    genai.configure(api_key=api_key)
                    self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
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

    def extract_text_from_file(self, file_path):
        
        text = ""
        file_extension = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_extension == '.pdf':
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
            
            elif file_extension == '.docx':
                doc = docx.Document(file_path)
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
            
            elif file_extension == '.txt':
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            
            return text.strip()
        except Exception as e:
            print(f"Error extracting text from {file_path}: {str(e)}")
            return ""

    def extract_skills(self, text):

        text_lower = text.lower()
        found_skills = []

        for skill in self.all_technical_skills:

            pattern = r'\b' + re.escape(skill.lower()) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.append(skill)
        

        return list(set(found_skills))

    def parse_date_range(self, date_string):
       
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
                            start_month, start_year, end_month, end_year = groups
                            start_date = datetime(int(start_year), int(start_month), 1)
                            end_date = datetime(int(end_year), int(end_month), 1)
                        
                        elif pattern_type == 'mm_yyyy_present':
                            start_month, start_year = groups
                            start_date = datetime(int(start_year), int(start_month), 1)
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
                        print(f"Error parsing date components: {str(e)}")
                        continue
            
            return 0
        except Exception as e:
            print(f"Error parsing date range '{date_string}': {str(e)}")
            return 0

    def extract_experience_years(self, text):
        """Extract years of experience from text using multiple methods"""
        text_lower = text.lower()
        years = []
        
       
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

    def calculate_work_experience(self, text):
        """Calculate total work experience from job date ranges, excluding internships"""
        total_years = 0
        lines = text.split('\n')
        
        # Track if we're in experience section (helpful but not required)
        in_experience_section = False
        in_education_section = False
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detect section markers
            if re.match(r'^experience\s*$', line.lower()) or ('professional' in line.lower() and 'experience' in line.lower()):
                in_experience_section = True
                in_education_section = False
                i += 1
                continue
            
            if re.match(r'^education\s*$', line.lower()) or re.match(r'^projects?\s*$', line.lower()):
                in_education_section = True
                in_experience_section = False
            
            # Skip lines in education section
            if in_education_section:
                i += 1
                continue
            
            if line:
                # Get next few lines for context
                next_lines = []
                for j in range(1, min(4, len(lines) - i)):
                    if i + j < len(lines):
                        next_lines.append(lines[i + j].strip())
                
                # Look for date patterns in current line or next lines
                all_context = [line] + next_lines
                
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
                            if not should_skip or (has_job_title and not 'intern' in job_context.lower()):
                                years_for_job = self.parse_date_range(date_range)
                                if years_for_job > 0:  # Only count positive years
                                    total_years += years_for_job
                                    print(f"Found work experience: {line} - {date_range} = {years_for_job:.1f} years")
                            else:
                                print(f"Skipping non-work experience: {job_context[:50]}... - {date_range}")
                            
                            break  # Move to next line once we found a date
                    else:
                        continue
                    break  # Move to next line once we found a date
            
            i += 1
        
        # Cap at realistic maximum
        return min(total_years, 20) 

    def extract_education(self, text):
        """Extract education information, excluding internship locations"""
        education_keywords = [
            'bachelor', 'master', 'phd', 'doctorate', 'degree', 'university', 
            'college', 'institute', 'b.s.', 'b.a.', 'm.s.', 'm.a.', 'mba',
            'b.sc', 'b.tech', 'm.tech', 'mca', 'bca'
        ]
        
        education_info = []
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

    def parse_with_ai(self, text):
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
            response = self.model.generate_content(prompt)
            json_str = response.text.strip()
            # Clean up potential markdown code blocks
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            
            return json.loads(json_str.strip())
        except Exception as e:
            print(f"Error parsing with AI: {e}")
            return None

    def parse_resume(self, file_path):
       
        text = self.extract_text_from_file(file_path)
        
        if not text:
            return None
        
        print("Parsing resume...")
        print(f"Text length: {len(text)} characters")
        
        profile = {
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



class jobMatcher:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            ngram_range=(1, 2),
            max_features=1000
        )
    
    


    def calculate_experience_match(self, profile_years, job_description):
        
        required_years = self._extract_required_experience(job_description)
        
        if required_years == 0:
            return 100.0 
        
        if profile_years >= required_years:
            return 100.0
        elif profile_years >= required_years * 0.8: 
            return 80.0
        elif profile_years >= required_years * 0.6: 
            return 60.0
        else:
            return max(20.0, (profile_years / required_years) * 100)
    
    def _extract_required_experience(self, job_description):
        
        patterns = [
            r'(\d+)\+?\s*years?\s*(?:of\s*)?experience',
            r'(\d+)\+?\s*years?\s*in',
            r'minimum\s*(?:of\s*)?(\d+)\+?\s*years?',
            r'at least\s*(\d+)\+?\s*years?',
        ]
        
        years = []
        text_lower = job_description.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    years.append(int(match))
                except ValueError:
                    continue
        
        
        return min(years) if years else 0
    
    def calculate_text_similarity(self, profile_text, job_description):
       
        try:
           
            texts = [profile_text, job_description]
            
           
            tfidf_matrix = self.vectorizer.fit_transform(texts)
            
            
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            
            return similarity * 100  
        except Exception as e:
            print(f"Error calculating text similarity: {str(e)}")
            return 0.0
    
    def calculate_overall_match(self, profile, job_description, weights=None):
        
        if weights is None:
            weights = {
                'skills': 0.4,
                'experience': 0.3,
                'text_similarity': 0.3
            }
        
        
        skill_score = self.calculate_skill_match(profile['skills'], job_description)
        experience_score = self.calculate_experience_match(profile['experience_years'], job_description)
        text_similarity_score = self.calculate_text_similarity(profile['raw_text'], job_description)
        
       
        overall_score = (
            skill_score * weights['skills'] +
            experience_score * weights['experience'] +
            text_similarity_score * weights['text_similarity']
        )
        
        return {
            'overall_match': round(overall_score, 1),
            'skill_match': round(skill_score, 1),
            'experience_match': round(experience_score, 1),
            'text_similarity': round(text_similarity_score, 1),
            'matched_skills': self._get_matched_skills(profile['skills'], job_description)
        }
    
    def calculate_skill_match(self, profile_skills, job_description):
       
        if not profile_skills:
            return 0.0
        
        job_description_lower = job_description.lower()
        matched_skills = []
        
        
        expanded_skills = []
        
        for skill in profile_skills:
            skill_lower = skill.lower().strip()
            expanded_skills.append(skill_lower)
            
            
            if 'apache spark' in skill_lower or skill_lower == 'spark':
                expanded_skills.extend(['spark', 'apache spark', 'pyspark', 'spark sql', 'databricks'])
            elif 'power bi' in skill_lower:
                expanded_skills.extend(['powerbi', 'power-bi', 'microsoft bi'])
            elif 'postgresql' in skill_lower:
                expanded_skills.extend(['postgres', 'psql'])
            elif skill_lower == 'python':
                expanded_skills.extend(['python3', 'py'])
            elif 'javascript' in skill_lower:
                expanded_skills.extend(['js', 'node.js', 'nodejs'])
            elif 'etl' in skill_lower or 'data pipeline' in skill_lower:
                expanded_skills.extend(['etl', 'elt', 'data pipeline', 'data integration', 'extract transform load'])
            elif 'aws' in skill_lower:
                expanded_skills.extend(['amazon web services', 'aws glue', 'redshift', 's3', 'lambda', 'kinesis'])
            elif 'azure' in skill_lower:
                expanded_skills.extend(['microsoft azure', 'azure data factory', 'adf'])
            elif 'machine learning' in skill_lower:
                expanded_skills.extend(['ml', 'predictive modeling', 'classification'])
            elif 'data visualization' in skill_lower or 'visualization' in skill_lower:
                expanded_skills.extend(['dashboards', 'reporting', 'charts'])
            elif 'statistical analysis' in skill_lower or 'statistics' in skill_lower:
                expanded_skills.extend(['hypothesis testing', 'regression', 'statistical'])
            elif 'snowflake' in skill_lower:
                expanded_skills.extend(['snowflake cloud'])
            elif 'tableau' in skill_lower:
                expanded_skills.extend(['tableau desktop', 'tableau server'])
            elif 'excel' in skill_lower:
                expanded_skills.extend(['microsoft excel', 'pivot tables', 'vlookup'])
            elif 'git' in skill_lower:
                expanded_skills.extend(['github', 'version control', 'gitlab'])
            elif 'docker' in skill_lower:
                expanded_skills.extend(['containerization', 'containers'])
            elif 'airflow' in skill_lower:
                expanded_skills.extend(['apache airflow', 'workflow orchestration'])
            elif 'selenium' in skill_lower:
                expanded_skills.extend(['web scraping', 'automated testing'])
            elif 'pandas' in skill_lower:
                expanded_skills.extend(['python pandas', 'dataframe'])
            elif 'numpy' in skill_lower:
                expanded_skills.extend(['numerical python'])
            elif skill_lower == 'sql':
                expanded_skills.extend(['mysql', 'postgresql', 'database queries', 'query'])
            elif 'nosql' in skill_lower or 'mongodb' in skill_lower:
                expanded_skills.extend(['document database', 'non-relational'])
            elif 'api' in skill_lower or 'rest' in skill_lower:
                expanded_skills.extend(['rest api', 'api', 'restful', 'web services'])
            elif 'ci/cd' in skill_lower:
                expanded_skills.extend(['continuous integration', 'jenkins', 'devops'])
        
        expanded_skills = list(set(expanded_skills))
        
       
        for skill in expanded_skills:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, job_description_lower):
                matched_skills.append(skill)
        
       
        match_percentage = (len(matched_skills) / len(profile_skills)) * 100
        return min(match_percentage, 100.0)


    def _get_matched_skills(self, profile_skills, job_description):
       
        if not profile_skills:
            return []
        
        job_description_lower = job_description.lower()
        matched_skills = []
        
        
        skill_variations = {
            'apache spark': ['spark', 'apache spark', 'pyspark', 'spark sql', 'databricks'],
            'power bi': ['power bi', 'powerbi', 'power-bi', 'microsoft bi'],
            'postgresql': ['postgresql', 'postgres', 'psql'],
            'python': ['python', 'py', 'python3'],
            'javascript': ['javascript', 'js', 'node.js', 'nodejs'],
            'etl': ['etl', 'elt', 'data pipeline', 'data integration', 'extract transform load'],
            'aws': ['aws', 'amazon web services', 'aws glue', 'redshift', 's3', 'lambda', 'kinesis'],
            'azure': ['azure', 'microsoft azure', 'azure data factory', 'adf'],
            'machine learning': ['machine learning', 'ml', 'predictive modeling', 'classification'],
            'data visualization': ['data visualization', 'dashboards', 'reporting', 'charts'],
            'statistical analysis': ['statistical analysis', 'statistics', 'hypothesis testing', 'regression'],
            'snowflake': ['snowflake', 'snowflake cloud'],
            'tableau': ['tableau', 'tableau desktop', 'tableau server'],
            'excel': ['excel', 'microsoft excel', 'pivot tables', 'vlookup'],
            'git': ['git', 'github', 'version control', 'gitlab'],
            'docker': ['docker', 'containerization', 'containers'],
            'airflow': ['airflow', 'apache airflow', 'workflow orchestration'],
            'selenium': ['selenium', 'web scraping', 'automated testing'],
            'pandas': ['pandas', 'python pandas', 'dataframe'],
            'numpy': ['numpy', 'numerical python'],
            'sql': ['sql', 'mysql', 'postgresql', 'database queries', 'query'],
            'nosql': ['nosql', 'mongodb', 'document database', 'non-relational'],
            'rest api': ['rest api', 'api', 'rest', 'restful', 'web services'],
            'ci/cd': ['ci/cd', 'continuous integration', 'jenkins', 'devops']
        }
        
        for skill in profile_skills:
            skill_lower = skill.lower().strip()
            skill_found = False
            
            
            pattern = r'\b' + re.escape(skill_lower) + r'\b'
            if re.search(pattern, job_description_lower):
                matched_skills.append(skill)
                skill_found = True
            else:
                
                for base_skill, variations in skill_variations.items():
                    if skill_lower in [v.lower() for v in variations]:
                        for variation in variations:
                            variation_pattern = r'\b' + re.escape(variation.lower()) + r'\b'
                            if re.search(variation_pattern, job_description_lower):
                                matched_skills.append(skill)
                                skill_found = True
                                break
                        if skill_found:
                            break
                
                
                if not skill_found and len(skill_lower) > 4:
                    if skill_lower in job_description_lower:
                        matched_skills.append(skill)
        
        return matched_skills

    def process_job_dataframe(self, df, profile, job_description_column='Description'):
        """Process entire job dataframe and add match scores"""
        results = []
        
        for index, row in df.iterrows():
            job_description = str(row.get(job_description_column, ''))
            
            if job_description and job_description != 'nan':
                match_results = self.calculate_overall_match(profile, job_description)
                
               
                job_result = row.to_dict()
                job_result.update(match_results)
                results.append(job_result)
            else:
                
                job_result = row.to_dict()
                job_result.update({
                    'overall_match': 0.0,
                    'skill_match': 0.0,
                    'experience_match': 0.0,
                    'text_similarity': 0.0,
                    'matched_skills': []
                })
                results.append(job_result)
        
        
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('overall_match', ascending=False)
        
        return results_df


