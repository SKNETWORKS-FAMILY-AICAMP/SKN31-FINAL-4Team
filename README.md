# FEEDIT Backend

FEEDIT의 Django 기반 백엔드 프로젝트입니다.

현재 단계에서는 프론트엔드 연동 없이 Django, AWS RDS, S3, Git 기반의 백엔드 및 데이터 인프라를 구성합니다.

## Tech Stack

- Python
- Django
- PostgreSQL
- AWS RDS
- AWS EC2
- AWS S3
- DBeaver
- psycopg
- python-dotenv
- boto3

## Project Structure

```text
SKN31-FINAL-4Team/
├─ .venv/
├─ Backend/
│  ├─ config/
│  │  ├─ settings.py
│  │  ├─ urls.py
│  │  ├─ asgi.py
│  │  └─ wsgi.py
│  └─ manage.py
├─ .env
├─ .gitignore
├─ requirements.txt
└─ README.md

