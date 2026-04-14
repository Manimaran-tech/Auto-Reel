# Auto-Reel

Auto-Reel is an AI-powered pipeline to generate marketing reels.

## Prerequisites
- Windows OS (instructions below are for Windows)
- Node.js (for frontend)
- Python 3.10 (for backend)

## Setup and Launch

### 1. Setup Virtual Environment for Backend
A Python virtual environment is required for the backend.
```bash
python -m venv .venv310
```
Activate the virtual environment and install backend dependencies:
```bash
.venv310\Scripts\activate
cd backend
pip install -r requirements.txt
cd ..
```

### 2. Launch the Backend
To start the backend FastAPI server with Uvicorn, run:
```bash
.\.venv310\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
*Note: Make sure your `.env` variables are correctly configured before launching.*

### 3. Launch the Frontend
In a separate terminal, navigate to the frontend directory and start the Vite development server:
```bash
cd frontend
npm install  # if you haven't installed packages yet
npm run dev
```