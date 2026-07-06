# Dead-Man's-Switch Digital Vault

A Flask + MySQL project that stores confidential digital information and automatically notifies trusted nominees after user inactivity.

## Features
- User registration and login
- Vault data management
- Nominee management
- Activity tracking
- Gmail SMTP notifications
- Emergency release flow
- Admin monitoring panel

## Tech Stack
- HTML, CSS, Bootstrap, JavaScript
- Python Flask
- MySQL
- Gmail SMTP

## Setup
1. Create the MySQL database.
2. Import `schema.sql`.
3. Create a `.env` file using `.env.example`.
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the app:
   ```bash
   python app.py
   ```

## Gmail SMTP
Use a Gmail app password if 2-step verification is enabled.