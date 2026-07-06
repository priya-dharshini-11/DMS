Title
Dead-Man’s-Switch Digital Vault using Flask, MySQL, and Gmail SMTP

Abstract
This project presents a web-based digital vault that protects important personal information and automatically releases it to trusted nominees after a prolonged period of user inactivity. The system is built using Flask for server-side processing, MySQL for data storage, Bootstrap and JavaScript for the interface, and Gmail SMTP for sending email notifications. It supports authentication, vault storage, nominee management, activity monitoring, reminder emails, and emergency release functionality.
geeksforgeeks
+2

Introduction
A Dead-Man’s-Switch system is designed to ensure that important information is not lost if the owner becomes unavailable. This project demonstrates how that concept can be implemented as a secure academic web application. It focuses on practical features such as login, secure storage, background activity tracking, and automated email delivery.
gist.github
+1

Objectives
To create a secure digital vault for confidential data.

To monitor user activity and detect inactivity.

To send reminder emails before release.

To automatically notify trusted nominees when the trigger condition is met.

To demonstrate a complete full-stack web application for academic evaluation.

System Design
The system is divided into modules: authentication, vault management, nominee management, document upload, activity monitoring, notification engine, and admin panel. Flask handles the application logic, MySQL stores persistent data, and APScheduler runs background checks.
dev
+1

Database Design
The main tables are users, vault_data, nominees, documents, activity_logs, notifications, and releases. These tables store user accounts, confidential records, trusted contacts, file metadata, activity timestamps, notification history, and release events.

Security Features
The project uses hashed passwords, server-side sessions, input validation, restricted file types, and environment-based credentials. These features reduce common risks such as password exposure, unauthorized access, and unsafe uploads.
hackerone
+1

Testing
The application was tested for login, registration, CRUD operations, upload validation, inactivity detection, reminder generation, and notification flow. Each feature was verified with sample input to confirm correct database updates and UI behavior.

Result
The final system provides a functional digital vault that supports emergency information sharing and automated nominee notification. It demonstrates how a Flask web application can combine security, scheduling, and database-driven workflows into one project.
github
+1

Conclusion
The Dead-Man’s-Switch Digital Vault is a practical and meaningful project for BCA-level study because it combines web development, database management, background scheduling, and secure email notifications. It is easy to explain in a viva and can be expanded later with encryption, OTP, and cloud storage.