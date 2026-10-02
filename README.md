# Dead-Man's-Switch Digital Vault

A Flask + MySQL web application that securely stores important digital information and releases selected vault items to trusted nominees when the user becomes inactive.

## Features

- User registration, login and email verification
- Dead Man's Switch inactivity and check-in system
- Secure digital vault for text and files
- Per-item release control
- Trusted nominee management
- Automated release and email/file delivery
- Account recovery, deletion and restoration
- Admin monitoring and management
- Help and support system
- Scheduled background processing with APScheduler

## Tech Stack

- **Backend:** Python, Flask
- **Database:** MySQL
- **Frontend:** HTML, CSS, Bootstrap, JavaScript, Jinja2
- **Email:** Gmail SMTP
- **Scheduler:** APScheduler

## Setup

### 1. Clone the repository

    git clone https://github.com/priya-dharshini-11/DMS.git
    cd DMS

### 2. Create a virtual environment

    python3 -m venv .venv
    source .venv/bin/activate

### 3. Install dependencies

    pip install -r requirements.txt

### 4. Configure MySQL

Create the database:

    CREATE DATABASE dms_vault;

Import the project schema:

    mysql -u DMS -p dms_vault < schema.sql

### 5. Configure environment variables

Create the local environment file:

    cp .env.example .env

Then edit `.env` and configure:

    SECRET_KEY
    MYSQL_HOST
    MYSQL_USER
    MYSQL_PASSWORD
    MYSQL_DB
    MAIL_USERNAME
    MAIL_PASSWORD
    ADMIN_REGISTRATION_KEY

For Gmail, use a Gmail App Password instead of your normal Gmail password.

### 6. Run the application

    python app.py

## Security

- Never commit the real `.env` file.
- Never expose database or email credentials.
- Use strong secret keys and passwords.
- Uploaded vault files are excluded from Git.

## Project Status

DMS v2 is in the final testing and deployment stage.

## License

Academic project developed as part of a Bachelors degree.
