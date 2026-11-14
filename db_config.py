import mysql.connector
import os
from datetime import datetime
import logging
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', '127.0.0.1'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', 'job_tracker'),
            'pool_name': os.getenv('DB_POOL_NAME', 'job_pool_v2'),
            'pool_size': int(os.getenv('DB_POOL_SIZE', '2'))
        }
        
        try:
            self.connection_pool = mysql.connector.pooling.MySQLConnectionPool(**self.db_config)
            logger.info("Database connection pool created successfully")
        except mysql.connector.Error as err:
            logger.error(f"Error creating connection pool: {err}")
            raise

    def get_connection(self):
        """Get a connection from the pool"""
        try:
            return self.connection_pool.get_connection()
        except mysql.connector.Error as err:
            logger.error(f"Error getting connection: {err}")
            raise

    def save_application(self, job_data):
        """Save a job application to the database"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = """
                INSERT INTO applications 
                (title, company, location, job_link, description, salary, 
                 experience_category, job_type, suggested_address, applied_date, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            values = (
                job_data.get('title', 'Not specified'),
                job_data.get('company', 'Not specified'),
                job_data.get('location', 'Not specified'),
                job_data.get('job_link', 'Not specified'),
                job_data.get('description', ''),
                job_data.get('salary', 'Not specified'),
                job_data.get('experience_category', 'Unknown'),
                job_data.get('job_type', 'Not specified'),
                job_data.get('suggested_address', 'Remote/Flexible'),
                job_data.get('applied_date', datetime.now()),
                'applied'
            )
            
            cursor.execute(query, values)
            connection.commit()
            
            return cursor.lastrowid
            
        except mysql.connector.Error as err:
            logger.error(f"Error saving application: {err}")
            if connection:
                connection.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_applications(self, filters=None):
        """Retrieve applications with optional filters"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = "SELECT * FROM applications WHERE 1=1"
            params = []
            
            if filters:
                if filters.get('status'):
                    query += " AND status = %s"
                    params.append(filters['status'])
                if filters.get('company'):
                    query += " AND company LIKE %s"
                    params.append(f"%{filters['company']}%")
                if filters.get('date_from'):
                    query += " AND applied_date >= %s"
                    params.append(filters['date_from'])
                if filters.get('date_to'):
                    query += " AND applied_date <= %s"
                    params.append(filters['date_to'])
            
            query += " ORDER BY applied_date DESC"
            
            cursor.execute(query, params)
            return cursor.fetchall()
            
        except mysql.connector.Error as err:
            logger.error(f"Error retrieving applications: {err}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def save_connection_request(self, company, application_ids=None):
        """Save connection request record"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = """
                INSERT INTO connection_requests 
                (company, sent_date, status, application_ids)
                VALUES (%s, %s, %s, %s)
            """
            
            values = (
                company,
                datetime.now(),
                'sent',
                ','.join(map(str, application_ids)) if application_ids else ''
            )
            
            cursor.execute(query, values)
            connection.commit()
            
            return cursor.lastrowid
            
        except mysql.connector.Error as err:
            logger.error(f"Error saving connection request: {err}")
            if connection:
                connection.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def create_networking_exclusions_table(self):
        """Create table for excluded companies in networking"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = """
            CREATE TABLE IF NOT EXISTS networking_exclusions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                company_name VARCHAR(255) NOT NULL UNIQUE,
                excluded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            cursor.execute(query)
            connection.commit()
            return True
        except mysql.connector.Error as err:
            logger.error(f"Error creating exclusions table: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def exclude_company(self, company_name):
        """Add a company to the exclusion list"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = "INSERT IGNORE INTO networking_exclusions (company_name) VALUES (%s)"
            cursor.execute(query, (company_name,))
            connection.commit()
            return True
        except mysql.connector.Error as err:
            logger.error(f"Error excluding company: {err}")
            return False
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def get_companies_for_connections(self):
        """Get list of companies where user applied, excluding those in exclusion list"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # Ensure exclusion table exists (lazy init)
            self.create_networking_exclusions_table()
            
            query = """
                SELECT DISTINCT a.company, COUNT(*) as application_count
                FROM applications a
                LEFT JOIN networking_exclusions ne
                    ON a.company = ne.company_name COLLATE utf8mb4_unicode_ci
                WHERE a.status = 'applied' AND ne.company_name IS NULL
                GROUP BY a.company
                ORDER BY MAX(a.applied_date) DESC
            """
            
            cursor.execute(query)
            return cursor.fetchall()
            
        except mysql.connector.Error as err:
            logger.error(f"Error getting companies: {err}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def save_processed_file(self, filename, total_jobs, jobs_applied):
        """Save processed file information"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = """
                INSERT INTO processed_files (filename, total_jobs, jobs_applied, processed_date)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    total_jobs = VALUES(total_jobs),
                    jobs_applied = VALUES(jobs_applied),
                    processed_date = VALUES(processed_date)
            """
            
            values = (filename, total_jobs, jobs_applied, datetime.now())
            cursor.execute(query, values)
            connection.commit()
            
            return True
            
        except mysql.connector.Error as err:
            logger.error(f"Error saving processed file: {err}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    # ==== JOB TRACKER METHODS ====
    
    def create_job_tracker_table(self):
        """Create job_tracker table for tracking applications"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = """
            CREATE TABLE IF NOT EXISTS job_tracker (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                company VARCHAR(255) NOT NULL,
                location VARCHAR(255),
                salary VARCHAR(100),
                job_link TEXT,
                status ENUM('bookmarked', 'applying', 'applied', 'interviewing', 'negotiating', 'accepted', 'rejected') DEFAULT 'bookmarked',
                excitement INT DEFAULT 0,
                date_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_applied DATE NULL,
                deadline DATE NULL,
                follow_up DATE NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_company (company),
                INDEX idx_date_saved (date_saved)
            )
            """
            
            cursor.execute(query)
            connection.commit()
            logger.info("Job tracker table created successfully")
            return True
            
        except mysql.connector.Error as err:
            logger.error(f"Error creating job tracker table: {err}")
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def add_job_to_tracker(self, job_data):
        """Add a job to the tracker (with duplicate check)"""
        connection = None
        cursor = None
        try:
            logger.info(f"Attempting to add job to tracker: {job_data.get('title', 'Unknown')} at {job_data.get('company', 'Unknown')}")
            
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # Check for duplicate by title + company OR by job_link
            title = job_data.get('title', 'Not specified')
            company = job_data.get('company', 'Not specified')
            job_link = job_data.get('job_link', '')
            
            check_query = """
            SELECT id FROM applications 
            WHERE (title = %s AND company = %s)
            """
            
            cursor.execute(check_query, (title, company))
            existing = cursor.fetchone()
            
            if existing:
                logger.warning(f"Job already exists in tracker with ID: {existing['id']}")
                return {'exists': True, 'job_id': existing['id'], 'message': 'Job already in tracker'}
            
            # Insert new job
            cursor = connection.cursor()  # Reset to non-dictionary cursor
            
            query = """
            INSERT INTO applications 
            (title, company, location, job_link, description, salary, experience_category, job_type, suggested_address, applied_date, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            values = (
                title,
                company,
                job_data.get('location', 'Not specified'),
                job_link,
                job_data.get('description', ''),
                job_data.get('salary', 'Not specified'),
                job_data.get('experience_category', 'Unknown'),
                job_data.get('job_type', 'Not specified'),
                job_data.get('suggested_address', 'Remote/Flexible'),
                job_data.get('date_applied', datetime.now()),
                job_data.get('status', 'applying')  # Default to 'applying' when adding from tracker
            )
            
            logger.debug(f"Executing query with values: {values}")
            cursor.execute(query, values)
            connection.commit()
            
            job_id = cursor.lastrowid
            logger.info(f"Successfully inserted job with ID: {job_id}")
            
            return job_id
            
        except mysql.connector.Error as err:
            logger.error(f"MySQL Error adding job to tracker: {err}", exc_info=True)
            if connection:
                connection.rollback()
            return None
        except Exception as e:
            logger.error(f"Unexpected error adding job to tracker: {e}", exc_info=True)
            if connection:
                connection.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_all_tracked_jobs(self):
        """Get all jobs from tracker"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT * FROM applications 
            ORDER BY 
                CASE status
                    WHEN 'bookmarked' THEN 1
                    WHEN 'applying' THEN 2
                    WHEN 'applied' THEN 3
                    WHEN 'interviewing' THEN 4
                    WHEN 'negotiating' THEN 5
                    WHEN 'accepted' THEN 6
                    WHEN 'rejected' THEN 7
                END,
                applied_date DESC
            """
            
            cursor.execute(query)
            jobs = cursor.fetchall()
            
            return jobs
            
        except mysql.connector.Error as err:
            logger.error(f"Error getting tracked jobs: {err}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_tracked_job_by_id(self, job_id):
        """Get a specific tracked job"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = "SELECT * FROM applications WHERE id = %s"
            cursor.execute(query, (job_id,))
            job = cursor.fetchone()
            
            return job
            
        except mysql.connector.Error as err:
            logger.error(f"Error getting tracked job: {err}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def update_job_status(self, job_id, new_status):
        """Update job status in tracker"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # If moving to "applied", set date_applied
            if new_status == 'applied':
                query = """
                UPDATE applications 
                SET status = %s, applied_date = CURDATE() 
                WHERE id = %s
                """
            else:
                query = """
                UPDATE applications 
                SET status = %s 
                WHERE id = %s
                """
            
            cursor.execute(query, (new_status, job_id))
            connection.commit()
            
            return True
            
        except mysql.connector.Error as err:
            logger.error(f"Error updating job status: {err}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def delete_tracked_job(self, job_id):
        """Delete a job from tracker"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = "DELETE FROM applications WHERE id = %s"
            cursor.execute(query, (job_id,))
            connection.commit()
            
            return True
            
        except mysql.connector.Error as err:
            logger.error(f"Error deleting tracked job: {err}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _execute(self, query, params):
        """Ejecuta un UPDATE y devuelve True si salió bien."""
        connection = cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute(query, params)
            connection.commit()
            return True
        except mysql.connector.Error as err:
            logger.error(f"Error updating applications: {err}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def update_tracker_dates(self, job_id, follow_up=None, deadline=None, notes=None):
        """Fecha de seguimiento, vencimiento y notas de una postulación (None borra la fecha)."""
        return self._execute(
            "UPDATE applications SET follow_up = %s, deadline = %s, notes = %s WHERE id = %s",
            (follow_up, deadline, notes, job_id),
        )

    def get_followup_candidates(self):
        """Postulaciones enviadas o en entrevista, que son las que admiten seguimiento."""
        connection = cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, title, company, job_link, status, applied_date, follow_up, deadline, last_reminder_at "
                "FROM applications WHERE status IN ('applied', 'interviewing')"
            )
            return cursor.fetchall()
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def mark_reminded(self, job_ids):
        """Registra que ya se avisó hoy por estas postulaciones."""
        if not job_ids:
            return True
        marks = ', '.join(['%s'] * len(job_ids))
        return self._execute(f"UPDATE applications SET last_reminder_at = NOW() WHERE id IN ({marks})", tuple(job_ids))


# Initialize database manager
db_manager = DatabaseManager()
