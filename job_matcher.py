"""Match entre un perfil de CV y una oferta: habilidades, años de experiencia pedidos y similitud de texto."""
import re

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


MAX_REQUIRED_YEARS = 20  # más años que esto en una oferta no es un requisito para la persona


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
            # español y portugués: "3 años de experiencia", "2 anos de experiência", "1 ano de experiência"
            r'(\d+)\+?\s*(?:años|anos?)\s*(?:de\s*)?experi[eê]ncia',
            r'(?:mínimo|minimo|al menos|pelo menos)\s*(?:de\s*)?(\d+)\+?\s*(?:años|anos?)',
        ]
        
        years = []
        text_lower = job_description.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    required_years = int(match)
                except ValueError:
                    continue
                # "empresa con 30 años de experiencia" habla de la empresa, no del puesto
                if required_years <= MAX_REQUIRED_YEARS:
                    years.append(required_years)
        
        
        return min(years) if years else 0
    
    def calculate_text_similarity(self, profile_text, job_description):
        """Similitud 0-100: embeddings si están activos para el idioma del CV, si no (o si fallan) TF-IDF."""
        import embeddings
        semantic = embeddings.similarity(profile_text, job_description)
        if semantic is not None:
            return semantic
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
        
        
        # Perfiles viejos o cargados a mano pueden no tener todos los campos del parser
        skills = profile.get('skills') or []
        skill_score = self.calculate_skill_match(skills, job_description)
        experience_score = self.calculate_experience_match(profile.get('experience_years') or 0, job_description)
        text_similarity_score = self.calculate_text_similarity(profile.get('raw_text') or '', job_description)
        
       
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
            'matched_skills': self._get_matched_skills(skills, job_description)
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
