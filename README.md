# hotel_system

A simple Flask-based hotel booking app with login/register, room browsing, and booking management.

## Setup

1. Create a Python virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set a secret key for session security (recommended):
   - Windows PowerShell:
     ```powershell
     $env:SECRET_KEY = "your-secret-key"
     ```
   - macOS/Linux:
     ```bash
     export SECRET_KEY="your-secret-key"
     ```
4. Run the app:
   ```bash
   python app.py
   ```

## Notes

- `hotel.db` is created automatically when the app starts.
- If `SECRET_KEY` is not provided, the app falls back to a default development value.
