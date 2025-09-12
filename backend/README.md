# Entity Research API Backend

A high-performance FastAPI-based service for comprehensive entity research using multi-engine web search and AI-powered analysis.

## Features

- **Multi-Engine Search**: Parallel searching across Google, Bing, and Yahoo
- **Intelligent Web Crawling**: Playwright-powered content extraction with anti-bot measures
- **AI-Powered Analysis**: Google Gemini integration for structured information extraction
- **Ultra-Strict Name Matching**: 95%+ similarity requirements for accurate entity identification
- **Async Processing**: High-concurrency architecture with real-time progress updates
- **Smart Consolidation**: LLM-based profile merging with conflict resolution
- **Search History**: Complete audit trail with SQLite storage
- **RESTful API**: Background task support with WebSocket-like progress streaming

## Prerequisites

- Python 3.8+
- Playwright browsers (will be installed automatically)
- Google Gemini API key

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ms_pds/backend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install Playwright browsers:
   ```bash
   playwright install
   ```

5. Create a `.env` file and add your Gemini API key:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

## Running the API

Start the FastAPI server with hot-reload:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, you can access:

- Interactive API docs: http://localhost:8000/docs
- Alternative API docs: http://localhost:8000/redoc

## Usage

### 1. Start a Research Task

```http
POST /research-entity
Content-Type: application/json

{
  "entity_name": "Elon Musk",
  "keywords": ["Tesla", "SpaceX", "Twitter"],
  "search_queries": [
    "Elon Musk biography",
    "Elon Musk companies",
    "Elon Musk family"
  ]
}
```

### 2. Check Research Status

```http
GET /research-status/{research_id}
```

### 3. Health Check

```http
GET /health
```

## Response Format

Research results will include structured information about the entity, including:

- Basic information (name, aliases, type)
- Extracted details (date of birth, age, education, etc.)
- Professional background
- Family information
- Location data
- Sources and confidence scores

## Configuration

You can configure the service using environment variables in the `.env` file:

- `GEMINI_API_KEY`: Your Google Gemini API key (required)
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `MAX_SEARCH_RESULTS`: Maximum number of search results to process (default: 10)
- `MAX_CONCURRENT_REQUESTS`: Maximum concurrent HTTP requests (default: 8)
- `LOG_LEVEL`: Logging level (default: INFO)

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
```

### Linting

```bash
flake8
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
