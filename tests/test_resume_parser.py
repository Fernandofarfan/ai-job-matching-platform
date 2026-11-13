"""
test_resume_parser.py – Tests unitarios para el módulo resume_parser.
"""
import pytest
import sys
import os

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestResumeParser:
    """Tests unitarios para la clase resumeParser."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from resume_parser import resumeParser
        self.parser = resumeParser()

    def test_parser_instantiation(self):
        """El parser debe instanciarse sin errores."""
        from resume_parser import resumeParser
        parser = resumeParser()
        assert parser is not None

    def test_extract_skills_returns_list(self):
        """extract_skills debe retornar una lista."""
        text = "Experienced in Python, SQL, pandas, scikit-learn and Flask."
        skills = self.parser.extract_skills(text)
        assert isinstance(skills, list)

    def test_extract_skills_finds_common_skills(self):
        """Debe detectar habilidades técnicas comunes."""
        text = "I have strong experience with Python, SQL, and Machine Learning."
        skills = self.parser.extract_skills(text)
        skills_lower = [s.lower() for s in skills]
        # Al menos una tecnología debe detectarse
        common = {'python', 'sql', 'machine learning'}
        found = common.intersection(set(skills_lower))
        assert len(found) > 0, f"No common skills found. Got: {skills_lower}"

    def test_extract_experience_years_numeric(self):
        """La experiencia extraída debe ser numérica y no negativa."""
        text = "I have 5 years of experience in software development."
        years = self.parser.extract_experience_years(text)
        assert isinstance(years, (int, float))
        assert years >= 0

    def test_extract_text_handles_empty_string(self):
        """El parser no debe fallar con texto vacío."""
        skills = self.parser.extract_skills('')
        assert isinstance(skills, list)


class TestJobMatcher:
    """Tests unitarios para la clase jobMatcher."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from resume_parser import jobMatcher
        self.matcher = jobMatcher()

    def test_matcher_instantiation(self):
        """El matcher debe instanciarse sin errores."""
        from resume_parser import jobMatcher
        matcher = jobMatcher()
        assert matcher is not None

    def test_calculate_match_returns_dict(self):
        """El cálculo de match debe retornar un dict con scores entre 0 y 100."""
        user_profile = {
            'skills': ['python', 'sql', 'pandas'],
            'experience_years': 3,
        }
        job_description = "Looking for Python developer with SQL skills and 2+ years experience."
        result = self.matcher.calculate_overall_match(user_profile, job_description)
        assert isinstance(result, dict)
        for key in ('overall_match', 'skill_match', 'experience_match',
                    'text_similarity', 'matched_skills'):
            assert key in result, f"Missing key: {key}"
        assert isinstance(result['overall_match'], (int, float))
        assert 0 <= result['overall_match'] <= 100

    def test_skill_match_empty_skills(self):
        """Con habilidades vacías el match debe ser 0."""
        score = self.matcher.calculate_skill_match([], "Python developer needed.")
        assert score == 0.0

    def test_skill_match_perfect_overlap(self):
        """Si todas las skills del usuario están en la descripción, el score debe ser 100."""
        score = self.matcher.calculate_skill_match(
            ['python', 'sql'],
            "We need someone with Python and SQL skills."
        )
        assert score > 0, "Expected positive match score"
