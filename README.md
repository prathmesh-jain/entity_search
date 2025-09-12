# Entity Search - Public Domain Search Using Multiple Search Engines

A comprehensive full-stack application for intelligent entity research using multi-engine web search, AI-powered analysis, and ultra-strict name matching for accurate person and company identification.

## 🚀 Features

### Backend (FastAPI + AI)

- **Multi-Engine Search**: Parallel searching across Google, Bing, and Yahoo
- **AI-Powered Extraction**: Google Gemini integration for structured data extraction
- **Ultra-Strict Matching**: 95%+ similarity requirements for accurate entity identification
- **High-Performance Crawling**: Playwright-based web scraping with anti-bot measures
- **Smart Consolidation**: LLM-based profile merging with conflict resolution
- **Real-time Progress**: Async processing with live status updates
- **Search History**: Complete audit trail with SQLite storage

### Frontend (React + Modern UI)

- **Real-time Dashboard**: Live progress tracking with phase indicators
- **Beautiful Interface**: Tailwind CSS with Framer Motion animations
- **Comprehensive Results**: Tabbed views for overview, entities, clusters, and sources
- **Search Management**: History browsing, filtering, and deletion
- **Responsive Design**: Mobile-first approach for all devices
- **Error Handling**: Graceful loading states and error recovery

## Prerequisites

- Node.js (v16 or higher)
- Python (3.8 or higher)
- npm or yarn
- pip (Python package manager)

## Getting Started

### Backend Setup

1. Navigate to the backend directory:

   ```bash
   cd backend
   ```
2. Create and activate a virtual environment (recommended):

   ```bash
   # On Windows
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI server:

   ```bash
   uvicorn main:app --reload
   ```

   The backend server will be available at `http://localhost:8000`

   - API documentation: `http://localhost:8000/docs`
   - Health check: `http://localhost:8000/health`

### Frontend Setup

1. In a new terminal, navigate to the frontend directory:

   ```bash
   cd frontend
   ```
2. Install Node.js dependencies:

   ```bash
   npm install
   ```
3. Start the development server:

   ```bash
   npm run dev
   ```

   The frontend will be available at `http://localhost:5173`

## Project Structure

```
ms_pds/
├── backend/               # FastAPI backend
│   ├── main.py           # Main FastAPI application
│   └── requirements.txt  # Python dependencies
└── frontend/             # React frontend
    ├── public/           # Static assets
    └── src/              # Source code
        ├── components/   # Reusable components
        ├── pages/        # Page components
        ├── App.jsx       # Main App component
        └── main.jsx      # Entry point
```

## API Endpoints

- `POST /search-entity`: Search for entity information
  - Request body: `{ "entity_name": "string", "keywords": ["string"] }`
  - Response: Entity information in JSON format

## Development

### Backend

- The backend is built with FastAPI and provides a RESTful API
- API documentation is automatically generated at `/docs`
- The server automatically reloads when code changes are detected

### Frontend

- Built with React and TailwindCSS
- Uses React Router for client-side routing
- Responsive design that works on mobile and desktop

## License

This project is licensed under the MIT License.
