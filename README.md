# Edura
A web-based study management platform for teachers and students, built with Flask and Tailwind CSS.

[Check it out](https://caelang.pythonanywhere.com/)

### Features
- Secure registration and login for teachers and students
- Multi-factor authentication (MFA) support
- Create, update, and delete classes (teachers)
- Join classes via code or invitation (students)
- Track study sessions with descriptions and durations
- Assign, edit, and complete tasks (teachers and students)
- Dashboard with study time visualization and recent activity
- Rate limiting and secure session management

### Tech Stack
- Backend: Python, Flask
- Database: SQLite
- Frontend: HTML, Tailwind CSS
- Authentication: Werkzeug, pyotp, qrcode
- Security: Flask-Limiter, Bleach

### Security Notes
- Passwords are hashed and validated for strength
- MFA available for both user types
- All user input sanitized
- Rate limiting enforced on login and sensitive routes

### License
MIT License
