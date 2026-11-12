-- ================================================
-- EmpleoIA - Database Setup Script
-- ================================================
-- Este script crea la base de datos y las tablas necesarias
-- Ejecutar como usuario root de MySQL

-- Crear base de datos
CREATE DATABASE IF NOT EXISTS job_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Crear usuario y otorgar permisos
CREATE USER IF NOT EXISTS 'jobtracking'@'localhost' IDENTIFIED BY 'StrongPass!123';
GRANT ALL PRIVILEGES ON job_tracker.* TO 'jobtracking'@'localhost';
FLUSH PRIVILEGES;

-- Usar la base de datos
USE job_tracker;

-- Tabla de aplicaciones
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
    status ENUM('bookmarked', 'applying', 'applied', 'interviewing', 'negotiating', 'accepted', 'rejected') DEFAULT 'applied',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_company (company),
    INDEX idx_status (status),
    INDEX idx_applied_date (applied_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabla de seguimiento de trabajos
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabla de solicitudes de conexión
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

-- Tabla de archivos procesados
CREATE TABLE IF NOT EXISTS processed_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) UNIQUE NOT NULL,
    total_jobs INT DEFAULT 0,
    jobs_applied INT DEFAULT 0,
    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_filename (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Mostrar tablas creadas
SHOW TABLES;

SELECT 'Database setup completed successfully!' AS Status;
