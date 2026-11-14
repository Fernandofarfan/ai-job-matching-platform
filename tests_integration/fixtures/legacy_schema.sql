-- Tablas que creaba setup_database.sql antes de que Alembic manejara todo el esquema.
-- Solo para test_schema.py: comprueba que una base así converge a los modelos.
CREATE TABLE IF NOT EXISTS applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    job_link TEXT,
    description TEXT,
    salary VARCHAR(100),
    experience_category VARCHAR(100),
    job_type VARCHAR(100),
    suggested_address VARCHAR(255),
    applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('applied', 'interviewing', 'rejected', 'accepted') DEFAULT 'applied',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_company (company),
    INDEX idx_status (status),
    INDEX idx_applied_date (applied_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS connection_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    company VARCHAR(255) NOT NULL,
    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('sent', 'accepted', 'declined', 'pending') DEFAULT 'sent',
    application_ids TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_company (company),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS processed_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) UNIQUE NOT NULL,
    total_jobs INT DEFAULT 0,
    jobs_applied INT DEFAULT 0,
    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_filename (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO applications (title, company, status) VALUES ('Backend Dev', 'Acme', 'interviewing');
INSERT INTO connection_requests (company, status, application_ids) VALUES ('Acme', 'declined', '1');
INSERT INTO processed_files (filename, total_jobs) VALUES ('jobs.csv', 3);
