CREATE DATABASE IF NOT EXISTS dms_vault;
USE dms_vault;

-- =========================================================
-- USERS
-- =========================================================

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_verified TINYINT(1) DEFAULT 0,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    deletion_requested_at DATETIME NULL,
    deletion_scheduled_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- VAULT
-- =========================================================

CREATE TABLE vault_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(150) NOT NULL,
    item_type VARCHAR(20) NOT NULL DEFAULT 'text',
    content TEXT NULL,
    file_name VARCHAR(255) NULL,
    original_file_name VARCHAR(255) NULL,
    file_path VARCHAR(500) NULL,
    file_type VARCHAR(100) NULL,
    release_enabled TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- NOMINEES
-- =========================================================

CREATE TABLE nominees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    relation VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- ACTIVITY LOG
-- =========================================================

CREATE TABLE activity_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dms_state VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    warning_started_at TIMESTAMP NULL,
    grace_started_at TIMESTAMP NULL,
    release_deadline TIMESTAMP NULL,
    released_at TIMESTAMP NULL,
    next_checkin_at TIMESTAMP NULL,
    checkin_reminder_sent_at TIMESTAMP NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- CHECK-IN TOKENS
-- =========================================================

CREATE TABLE dms_checkin_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- ACTIVITY HISTORY
-- =========================================================

CREATE TABLE activity_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(255) NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- RELEASES
-- =========================================================

CREATE TABLE releases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    release_reason VARCHAR(100) NOT NULL,
    released_at TIMESTAMP NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- RELEASE DELIVERIES
-- =========================================================

CREATE TABLE release_deliveries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    release_id INT NOT NULL,
    nominee_id INT NOT NULL,
    vault_item_id INT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    sent_at TIMESTAMP NULL,
    error_message VARCHAR(255) NULL,

    FOREIGN KEY (release_id)
        REFERENCES releases(id)
        ON DELETE CASCADE,

    FOREIGN KEY (nominee_id)
        REFERENCES nominees(id)
        ON DELETE CASCADE,

    FOREIGN KEY (vault_item_id)
        REFERENCES vault_data(id)
        ON DELETE CASCADE,

    UNIQUE KEY unique_release_delivery
        (release_id, nominee_id, vault_item_id)
);

-- =========================================================
-- EMAIL VERIFICATION
-- =========================================================

CREATE TABLE email_verification_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    used_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_email_verification_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- PASSWORD RESET
-- =========================================================

CREATE TABLE password_reset_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    used_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_password_reset_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- SUPPORT QUERIES
-- =========================================================

CREATE TABLE support_queries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    subject VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'OPEN',
    admin_reply TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_support_user (user_id),
    INDEX idx_support_status (status),

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================================
-- SUPPORT QUERY AUDIT
-- =========================================================

CREATE TABLE support_query_audit (
    id INT AUTO_INCREMENT PRIMARY KEY,
    query_id INT NOT NULL,
    user_id INT NULL,
    user_name VARCHAR(100) NULL,
    user_email VARCHAR(120) NULL,
    subject VARCHAR(150) NULL,
    category VARCHAR(50) NULL,
    message TEXT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(255) NULL,

    INDEX idx_support_audit_query (query_id),
    INDEX idx_support_audit_user (user_id),
    INDEX idx_support_audit_event (event_type),
    INDEX idx_support_audit_time (event_time)
);

-- =========================================================
-- PUBLIC SUPPORT
-- =========================================================

CREATE TABLE public_support_queries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    subject VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    admin_reply TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_public_support_email (email),
    INDEX idx_public_support_status (status),
    INDEX idx_public_support_created (created_at)
);

-- =========================================================
-- ACCOUNT DELETION AUDIT
-- =========================================================

CREATE TABLE account_deletion_audit (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    user_name VARCHAR(100) NULL,
    user_email VARCHAR(120) NULL,
    event_type VARCHAR(50) NOT NULL,
    event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(255) NULL
);
