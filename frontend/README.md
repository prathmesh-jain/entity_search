# Entity Research Frontend

A modern React-based web application for entity research with real-time progress tracking and beautiful UI components.

## Features

- **Modern React UI**: Built with React 18 and Vite for fast development
- **Real-time Progress**: Live updates during entity research with phase tracking
- **Beautiful Design**: Tailwind CSS with Framer Motion animations
- **Search History**: Complete search history with filtering and management
- **Responsive Layout**: Mobile-first design that works on all devices
- **Interactive Results**: Tabbed interface for overview, details, entities, clusters, and sources
- **Export Capabilities**: Download research results in multiple formats
- **Error Handling**: Graceful error states and loading indicators

## Prerequisites

- Node.js 16+ 
- npm or yarn
- Backend API running on `http://localhost:8000`

## Installation

1. Navigate to the frontend directory:
   ```bash
   cd ms_pds/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   # or
   yarn install
   ```

## Development

Start the development server:
```bash
npm run dev
# or
yarn dev
```

The application will be available at `http://localhost:5173`

## Build for Production

Create a production build:
```bash
npm run build
# or
yarn build
```

Preview the production build:
```bash
npm run preview
# or
yarn preview
```

## Project Structure

```
src/
├── components/          # Reusable UI components
├── pages/              # Main application pages
│   ├── Search.jsx      # Entity search interface
│   ├── Results.jsx     # Research results display
│   └── History.jsx     # Search history management
├── App.jsx             # Main application component
├── main.jsx           # Application entry point
└── index.css          # Global styles and Tailwind imports
```

## Key Components

### Search Page
- Entity name input with validation
- Optional keywords and custom search queries
- Real-time search initiation

### Results Page
- Live progress tracking with phase indicators
- Tabbed interface for different result views
- Entity information with source attribution
- Cluster analysis and consolidation results

### History Page
- Searchable history with filtering
- Delete functionality for old searches
- Quick access to previous results

## API Integration

The frontend communicates with the backend API at `http://localhost:8000`:

- `POST /research-entity` - Start new research
- `GET /research-status/{id}` - Check research progress
- `GET /search-history` - Retrieve search history
- `DELETE /search-history/{id}` - Delete search record

## Styling

The application uses:
- **Tailwind CSS** for utility-first styling
- **Framer Motion** for smooth animations
- **Heroicons** for consistent iconography
- **Custom gradients** and modern design patterns

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## License

This project is licensed under the MIT License.
