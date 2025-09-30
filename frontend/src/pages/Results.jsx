import { useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeftIcon,
  MagnifyingGlassIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  InformationCircleIcon,
  ClockIcon
} from '@heroicons/react/24/outline';
import { Fragment, useEffect, useRef, useState } from 'react';

// Preferred field order for displaying entity details
const PREFERRED_FIELD_ORDER = [
  'age',
  'year_of_birth',
  'yob',
  'date_of_birth',
  'dob',
  'full_name',
  'gender',
  'nationality',
  'occupation',
  'job_title',
  'employer',
  'educational_background',
  'professional_background',
  'employment_history',
  'place_of_birth',
  'residence_location',
  'citizenship',
  'aliases',
  'contact_information'
];
const FIELD_ORDER_INDEX = PREFERRED_FIELD_ORDER.reduce((acc, key, idx) => {
  acc[key] = idx;
  return acc;
}, {});
const compareFieldKeys = (a, b) => {
  const aKey = Array.isArray(a) ? a[0] : a;
  const bKey = Array.isArray(b) ? b[0] : b;
  const idxA = (FIELD_ORDER_INDEX[aKey] !== undefined) ? FIELD_ORDER_INDEX[aKey] : Number.MAX_SAFE_INTEGER;
  const idxB = (FIELD_ORDER_INDEX[bKey] !== undefined) ? FIELD_ORDER_INDEX[bKey] : Number.MAX_SAFE_INTEGER;
  if (idxA !== idxB) return idxA - idxB;
  return String(aKey).localeCompare(String(bKey));
};

// Expandable Array Component
const ExpandableArray = ({ items }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const displayItems = isExpanded ? items : items.slice(0, 3);

  return (
    <div className="text-xs bg-gray-50 rounded p-2 px-1 border border-gray-200 max-w-sm">
      {displayItems.map((item, idx) => (
        <div key={idx} className={`${idx > 0 ? 'mt-2 pt-2 border-t border-gray-200' : ''}`}>
          {typeof item === 'object' && item !== null ? (
            <div className="space-y-1">
              {Object.entries(item).filter(([key, value]) => value !== null && value !== undefined && value !== '').map(([key, value]) => (
                <div key={key} className="flex flex-col text-left">
                  <span className="text-gray-600 text-xs font-medium capitalize">
                    {key.replace(/_/g, ' ')}:
                  </span>
                  <span className="text-gray-900 text-xs ml-2">
                    {String(value)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-gray-900 text-xs block">
              {String(item)}
            </span>
          )}
        </div>
      ))}
      {items.length > 3 && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full text-gray-500 hover:text-gray-700 text-center mt-2 pt-2 border-t border-gray-200 text-xs hover:bg-gray-100 rounded transition-colors"
        >
          {isExpanded ? (
            <>
              <svg className="w-3 h-3 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
              </svg>
              Show less
            </>
          ) : (
            <>
              <svg className="w-3 h-3 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
              +{items.length - 3} more items
            </>
          )}
        </button>
      )}
    </div>
  );
};

// Expandable Object Fields Component
const ExpandableObjectFields = ({ entries }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const displayEntries = isExpanded ? entries : entries.slice(0, 4);

  return (
    <>
      {displayEntries.slice(4).filter(([k, v]) => v !== null && v !== undefined && v !== '').map(([k, v], idx) => (
        <div key={k} className={`flex justify-between items-start mt-1`}>
          <span className="text-gray-600 text-xs mr-2 flex-shrink-0">
            {k.replace(/_/g, ' ')}:
          </span>
          <span className="text-xs text-right flex-1 min-w-0">
            {typeof v === 'object' && v !== null ? (
              Array.isArray(v) ? (
                <span className="truncate block" title={String(v)}>{String(v)}</span>
              ) : (
                <span className="truncate block" title={String(v)}>{String(v)}</span>
              )
            ) : (
              <span className="truncate block" title={String(v)}>{String(v)}</span>
            )}
          </span>
        </div>
      ))}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full text-gray-500 hover:text-gray-700 text-center mt-1 text-xs hover:bg-gray-100 rounded transition-colors py-1"
      >
        {isExpanded ? (
          <>
            <svg className="w-3 h-3 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
            </svg>
            Show less
          </>
        ) : (
          <>
            <svg className="w-3 h-3 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
            +{entries.length - 4} more
          </>
        )}
      </button>
    </>
  );
};

const Results = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { searchResults, researchId } = location.state || {};

  // Check for research_id in URL params if not in state
  const urlParams = new URLSearchParams(location.search);
  const researchIdFromUrl = urlParams.get('research_id');
  const finalResearchId = researchId || researchIdFromUrl;

  const [activeTab, setActiveTab] = useState('entities');
  const [sourcesPage, setSourcesPage] = useState(1);
  const [sourcesPerPage, setSourcesPerPage] = useState(10);
  const [isExporting, setIsExporting] = useState(false);
  const [status, setStatus] = useState(searchResults ? 'completed' : 'pending');
  const [phase, setPhase] = useState('starting');
  const [progress, setProgress] = useState({});
  const [events, setEvents] = useState([]);
  const [finalResults, setFinalResults] = useState(searchResults ? searchResults.results : null);
  const [headerMeta, setHeaderMeta] = useState({ search_id: finalResearchId || 'N/A', timestamp: new Date().toISOString() });
  const sseRef = useRef(null);
  const [sseConnected, setSseConnected] = useState(false);
  const [showSourcesModal, setShowSourcesModal] = useState(false);
  const [modalField, setModalField] = useState('');
  const [modalSourceIds, setModalSourceIds] = useState([]);

  // SSE stream subscription for live updates
  useEffect(() => {
    if (!finalResearchId) return;
    try {
      const es = new EventSource(`http://localhost:8000/research-stream/${finalResearchId}`);
      sseRef.current = es;

      es.addEventListener('state', (event) => {
        try {
          const data = JSON.parse(event.data || '{}');
          setStatus(data.status);
          setPhase(data.phase || '');
          setProgress(data.progress || {});
          setEvents(data.events || []);
          setHeaderMeta({ search_id: finalResearchId, timestamp: data.started_at || new Date().toISOString() });
          if (data.live_results) {
            setFinalResults(data.live_results);
          }
          setSseConnected(true);
        } catch (e) {
          console.warn('SSE state parse error', e);
        }
      });

      es.addEventListener('snapshot', (event) => {
        try {
          const payload = JSON.parse(event.data || '{}');
          if (payload && payload.result) {
            setFinalResults(payload.result);
          }
        } catch (e) {
          console.warn('SSE snapshot parse error', e);
        }
      });

      es.addEventListener('done', (event) => {
        try {
          const payload = JSON.parse(event.data || '{}');
          setStatus(payload.status || 'completed');
          if (payload.results) {
            setFinalResults(payload.results);
          }
        } catch (e) {
          console.warn('SSE done parse error', e);
        } finally {
          setSseConnected(false);
          try { es.close(); } catch (_) {}
        }
      });

      es.onerror = () => {
        setSseConnected(false);
        try { es.close(); } catch (_) {}
      };

      return () => {
        try { es.close(); } catch (_) {}
        sseRef.current = null;
      };
    } catch (e) {
      console.error('SSE connect error', e);
    }
  }, [finalResearchId]);

  // Polling for async research (fallback when SSE is not connected)
  const intervalRef = useRef(null);
  useEffect(() => {
    if (finalResearchId && !sseConnected) {
      const poll = async () => {
        try {
          const res = await fetch(`http://localhost:8000/research-status/${finalResearchId}`);
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || 'Failed to fetch status');
          setStatus(data.status);
          setPhase(data.phase || '');
          setProgress(data.progress || {});
          setEvents(data.events || []);
          setHeaderMeta({ search_id: data.research_id, timestamp: data.started_at });
          // Use live partial results while processing (so UI can render early)
          if (data.live_results) {
            setFinalResults(data.live_results);
          }
          if (data.status === 'completed') {
            setFinalResults(data.results);
            if (intervalRef.current) {
              clearInterval(intervalRef.current);
              intervalRef.current = null;
            }
          }
        } catch (e) {
          console.error('Poll error', e);
        }
      };
      // Start polling once
      poll();
      if (!intervalRef.current) {
        intervalRef.current = setInterval(poll, 750);
      }
    } else if (searchResults) {
      // Synchronous flow compatibility
      setStatus('completed');
      setFinalResults(searchResults.results || searchResults);
      setHeaderMeta({ search_id: searchResults.search_id || 'N/A', timestamp: searchResults.timestamp });
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [finalResearchId, researchId, searchResults, navigate, sseConnected]);
    console.log("finalResults -> ", finalResults);

  const entity_name = finalResults?.entity_name || '';
  const sources = finalResults?.sources || [];
  const search_results_count = finalResults?.search_results_count || 0;
  const crawled_pages_count = finalResults?.crawled_pages_count || 0;
  const per_field_sources = finalResults?.per_field_sources || {};
  const clusters = finalResults?.clusters || {};
  const final_entities = finalResults?.final_entities?.entities || [];
  const basic_info = finalResults?.entity_info || final_entities?.[0]?.combined_fields || {};

  // Create a mapping from source_id to source details for consistent numbering
  const sourceIdToDetails = {};
  sources.forEach((source, index) => {
    const sourceId = source.source_id || (index + 1);
    sourceIdToDetails[sourceId] = {
      ...source,
      displayNumber: sourceId
    };
  });

  // Helper function to get source URL from source ID
  const getSourceUrl = (sourceId) => {
    return sourceIdToDetails[sourceId]?.url || '#';
  };
  const getDomain = (url) => {
    try { return new URL(url).hostname; } catch (_) {
      try { return (url || '').split('/')[2] || url; } catch { return url || ''; }
    }
  };
  const openSourcesModal = (fieldLabel, sourceIds) => {
    setModalField(fieldLabel);
    setModalSourceIds(sourceIds || []);
    setShowSourcesModal(true);
  };
  const closeSourcesModal = () => setShowSourcesModal(false);
  const search_keywords = finalResults?.search_queries || searchResults?.keywords || [];

  const adverse_mentions = [];
  const search_id = headerMeta.search_id;
  const timestamp = headerMeta.timestamp;

  const handleNewSearch = () => {
    navigate('/search');
  };

  const handleStop = async () => {
    if (!finalResearchId) return;
    try {
      await fetch(`http://localhost:8000/research-cancel/${finalResearchId}`, { method: 'POST' });
    } catch (e) {
      console.error('Cancel error', e);
    }
  };

  // const handleExport = async () => {
  //   setIsExporting(true);
  //   try {
  //     // Simulate API call for export
  //     await new Promise(resolve => setTimeout(resolve, 1500));
  //     // In a real app, you would trigger a file download here
  //     console.log('Exporting data:', data);
  //   } catch (error) {
  //     console.error('Export failed:', error);
  //   } finally {
  //     setIsExporting(false);
  //   }
  // };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const options = {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    };
    return new Date(dateString).toLocaleDateString(undefined, options);
  };

  // Safely render values including arrays and objects with nested object support
  const renderValue = (val) => {
    if (val == null) return 'N/A';
    if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') return String(val);

    if (Array.isArray(val)) {
      return (
        <ul className="space-y-1">
          {val.map((item, idx) => (
            <li key={idx} className="flex items-start">
              <CheckCircleIcon className="h-4 w-4 text-green-500 mr-2 mt-0.5" />
              <span className="break-words text-sm">
                {typeof item === 'object' && item !== null ? renderNestedObject(item) : String(item)}
              </span>
            </li>
          ))}
        </ul>
      );
    }
    if (typeof val === 'object') {
      return renderNestedObject(val);
    }
    return String(val);
  };

  // Helper function to render nested objects with compact formatting
  const renderNestedObject = (obj) => {
    if (!obj || typeof obj !== 'object') return String(obj);

    // Handle arrays by using the ExpandableArray component
    if (Array.isArray(obj)) {
      return <ExpandableArray items={obj} />;
    }

    const entries = Object.entries(obj).filter(([k, v]) => v !== null && v !== undefined && v !== '');
    if (entries.length === 0) return 'N/A';

    return (
      <div className="text-xs bg-gray-50 rounded p-1 border border-gray-200 max-w-xs">
        {entries.slice(0, 4).map(([k, v], idx) => (
          <div key={k} className={`flex justify-between items-start ${idx > 0 ? 'mt-1' : ''}`}>
            <span className="text-gray-600 text-xs mr-2 flex-shrink-0">
              {k.replace(/_/g, ' ')}:
            </span>
            <span className="text-xs text-right flex-1 min-w-0">
              {typeof v === 'object' && v !== null ? (
                Array.isArray(v) ? (
                  <span className="truncate block" title={String(v)}>{Object.keys(v).length} fields</span>
                ) : (
                  <span className="truncate block" title={String(v)}>{Object.keys(v).length} fields</span>
                )
              ) : (
                <span className="truncate block" title={String(v)}>{String(v)}</span>
              )}
            </span>
          </div>
        ))}
        {entries.length > 4 && (
          <ExpandableObjectFields entries={entries} />
        )}
      </div>
    );
  };

  const getSeverityBadge = (severity) => {
    const severityMap = {
      high: {
        bg: 'bg-red-100',
        text: 'text-red-800',
        icon: ExclamationTriangleIcon,
        label: 'High Risk'
      },
      medium: {
        bg: 'bg-yellow-100',
        text: 'text-yellow-800',
        icon: InformationCircleIcon,
        label: 'Medium Risk'
      },
      low: {
        bg: 'bg-green-100',
        text: 'text-green-800',
        icon: CheckCircleIcon,
        label: 'Low Risk'
      }
    };

    const { bg, text, icon: Icon, label } = severityMap[severity?.toLowerCase()] ||
      { bg: 'bg-gray-100', text: 'text-gray-800', icon: InformationCircleIcon, label: 'Unknown' };

    return (
      <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${bg} ${text}`}>
        <Icon className={`h-3.5 w-3.5 mr-1.5 ${text}`} />
        {label}
      </span>
    );
  };

  const clustersCount = Object.values(clusters || {}).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0);
  const tabs = [
    // { name: 'Overview', id: 'overview' },
    // { name: 'Details', id: 'details' },
    { name: 'Entities', id: 'entities', count: final_entities.length || 0 },
    { name: 'Clusters', id: 'clusters', count: clustersCount },
    { name: 'Sources', id: 'sources', count: sources?.length || 0 },
  ];

  // Only show final page when results are populated meaningfully
  const hasMeaningfulData = () => {
    if (!finalResults) return false;
    if ((final_entities?.length || 0) > 0) return true;
    if (Object.keys(basic_info || {}).length > 0) return true;
    if ((sources?.length || 0) > 0) return true;
    return false;
  };
  // As soon as we have meaningful data (even partial), render the page
  const isReady = hasMeaningfulData();
  const isCompletedNoData = status === 'completed' && !hasMeaningfulData();

  // Missing context (no research id and no sync results) -> show inline message
  if (!finalResearchId && !searchResults) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 flex items-center justify-center p-6">
        <div className="w-full max-w-xl bg-white shadow-lg rounded-2xl p-8 text-center">
          <div className="mx-auto h-12 w-12 rounded-full bg-gray-100 flex items-center justify-center">
            <InformationCircleIcon className="h-6 w-6 text-gray-500" />
          </div>
          <h2 className="mt-4 text-lg font-semibold text-gray-900">Missing research context</h2>
          <p className="mt-2 text-sm text-gray-600">No research ID was provided. Please start a new search.</p>
          <div className="mt-6">
            <button
              onClick={() => navigate('/search')}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              <MagnifyingGlassIcon className="-ml-1 mr-2 h-5 w-5" />
              Go to Search
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Completed but no data: show empty state
  if (isCompletedNoData) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 flex items-center justify-center p-6">
        <div className="w-full max-w-xl bg-white shadow-lg rounded-2xl p-8 text-center">
          <div className="mx-auto h-12 w-12 rounded-full bg-gray-100 flex items-center justify-center">
            <InformationCircleIcon className="h-6 w-6 text-gray-500" />
          </div>
          <h2 className="mt-4 text-lg font-semibold text-gray-900">No usable information found</h2>
          <p className="mt-2 text-sm text-gray-600">We completed the research but couldn’t extract meaningful data from the sources. Try refining the name or adding specific keywords.</p>
          <div className="mt-6">
            <button
              onClick={() => navigate('/search')}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              <MagnifyingGlassIcon className="-ml-1 mr-2 h-5 w-5" />
              New Search
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Loader view before any results are ready
  if (!isReady) {
    const phases = ["searching", "crawling", "analyzing", "combining"];
    const currentIndex = Math.max(0, phases.indexOf((phase || "searching").toLowerCase()));
    let pct = (currentIndex + 1) * 20;
    if ((phase || "").toLowerCase() === "analyzing" && progress?.pages_analyzed != null && progress?.pages_total) {
      pct = Math.min(100, Math.round((progress.pages_analyzed / Math.max(1, progress.pages_total)) * 100));
    } else if (progress?.pages_crawled != null && progress?.pages_total) {
      pct = Math.min(100, Math.round((progress.pages_crawled / Math.max(1, progress.pages_total)) * 100));
    }
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-gray-900/30 backdrop-blur-sm" />
        <div className="relative w-full max-w-2xl mx-4 bg-white shadow-2xl rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Processing</p>
              <p className="text-lg font-semibold capitalize">{phase || 'starting'}</p>
            </div>
            <svg className="animate-spin h-6 w-6 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
          </div>

          {/* Stepper */}
          <div className="mt-5">
            <ol className="flex items-center w-full text-xs text-gray-600">
              {phases.map((p, idx) => (
                <li key={p} className={`flex-1 flex items-center ${idx < currentIndex ? 'text-green-600' : (idx === currentIndex ? 'text-blue-600' : 'text-gray-400')}`}>
                  <div className={`flex items-center`}>
                    <span className={`h-2 w-2 rounded-full mr-2 ${idx < currentIndex ? 'bg-green-500' : (idx === currentIndex ? 'bg-blue-500' : 'bg-gray-300')}`}></span>
                    <span className="capitalize">{p}</span>
                  </div>
                  {idx < phases.length - 1 && (
                    <div className="flex-1 mx-2 h-px bg-gray-200" />
                  )}
                </li>
              ))}
            </ol>
          </div>

          {/* Progress bar */}
          <div className="mt-4">
            <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
              <div className="bg-blue-600 h-2 transition-all" style={{ width: `${pct}%` }} />
            </div>
            <div className="mt-1 text-xs text-gray-500">
              {(progress?.pages_crawled != null && progress?.pages_total != null) && (
                <span>Crawled {progress.pages_crawled} / {progress.pages_total}</span>
              )}
              {(progress?.pages_analyzed != null && progress?.pages_total != null) && (
                <>
                  {progress?.pages_crawled != null ? <span className="mx-1">•</span> : null}
                  <span>Analyzed {progress.pages_analyzed} / {progress.pages_total}</span>
                </>
              )}
              {progress?.current_page && (
                <>
                  <span className="mx-1">•</span>
                  <span className="truncate inline-block max-w-[18rem]" title={progress.current_page}>Current: {progress.current_page}</span>
                </>
              )}
            </div>
          </div>

          {/* Recent events */}
          {events?.length > 0 && (
            <div className="mt-4 max-h-48 overflow-auto text-sm text-gray-700 border-t pt-3">
              {events.slice(-7).map((ev, idx) => (
                <div key={idx} className="py-1 border-b border-gray-100 last:border-b-0">
                  <span className="text-gray-400 mr-2">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                  <span className="capitalize text-gray-500">[{ev.phase}]</span> {ev.message}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 pb-16 pt-12">
      {/* Header */}
      <div className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="py-6">
            <div className="flex items-center justify-between">
              <div>
                <button
                  onClick={handleNewSearch}
                  className="inline-flex items-center text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  <ArrowLeftIcon className="h-5 w-5 mr-1.5" />
                  Back to Search
                </button>
                <h1 className="mt-2 text-2xl font-bold text-gray-900">Search Results</h1>
                <div className="mt-1 flex items-center text-sm text-gray-500">
                  <span>Search ID: {search_id}</span>
                  <span className="mx-2">•</span>
                  <span className="flex items-center">
                    <ClockIcon className="h-4 w-4 mr-1" />
                    {formatDate(timestamp)}
                  </span>
                </div>
              </div>
              <div className="flex space-x-3">
                {/* <button
                  type="button"
                  onClick={handleExport}
                  disabled={isExporting}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
                >
                  {isExporting ? 'Exporting...' : 'Export Report'}
                </button> */}
                <button
                  type="button"
                  onClick={handleNewSearch}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  <MagnifyingGlassIcon className="-ml-1 mr-2 h-5 w-5" />
                  New Search
                </button>
              </div>
            </div>

            {/* Tabs */}
            <div className="mt-6">
              <div className="border-b border-gray-200">
                <nav className="-mb-px flex space-x-8">
                  {tabs.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`${activeTab === tab.id
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                        } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center`}
                    >
                      {tab.name}
                      {tab.count > 0 && (
                        <span
                          className={`ml-2 py-0.5 px-2 rounded-full text-xs font-medium ${activeTab === tab.id
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-gray-100 text-gray-600'
                            }`}
                        >
                          {tab.count}
                        </span>
                      )}
                    </button>
                  ))}
                </nav>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Loader / Phase Indicator + Stop */}
        {(['pending','in_progress','starting','cancelling'].includes((status || '').toLowerCase())) && (
          <div className="mb-6 rounded-lg bg-white p-4 shadow">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Current phase</p>
                <p className="text-lg font-semibold capitalize">{phase || 'starting'}</p>
              </div>
              <div className="flex items-center space-x-4">
                <button
                  onClick={handleStop}
                  disabled={!finalResearchId}
                  className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50"
                  title="Stop processing"
                >
                  Stop
                </button>
                <div className="text-sm text-gray-600">
                  {(progress?.pages_crawled != null && progress?.pages_total != null) && (
                    <span>Crawled {progress.pages_crawled} / {progress.pages_total}</span>
                  )}
                  {(progress?.pages_analyzed != null && progress?.pages_total != null) && (
                    <>
                      {progress?.pages_crawled != null ? <span className="mx-1">•</span> : null}
                      <span>Analyzed {progress.pages_analyzed} / {progress.pages_total}</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            {events?.length > 0 && (
              <div className="mt-3 max-h-40 overflow-auto text-sm text-gray-700">
                {events.slice(-5).map((ev, idx) => (
                  <div key={idx} className="py-1 border-b border-gray-100 last:border-b-0">
                    <span className="text-gray-400 mr-2">{new Date(ev.timestamp).toLocaleTimeString()}</span>
                    <span className="capitalize text-gray-500">[{ev.phase}]</span> {ev.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            

            {activeTab === 'entities' && (
              <div className="space-y-8">
                {/* Search Keywords Display */}
                {search_keywords && search_keywords.length > 0 && (
                      <div className="mb-6 p-3 bg-white rounded-lg border border-blue-200">
                        <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center">
                          <svg className="w-4 h-4 mr-2 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                          </svg>
                          Search Query Used
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {search_keywords.map((keyword, idx) => (
                            <span key={idx} className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200">
                              {keyword}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                {(!final_entities || final_entities.length === 0) ? (
                  <div className="bg-white shadow overflow-hidden sm:rounded-lg">
                    <div className="text-center py-12">
                      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                      <h3 className="text-lg font-medium text-gray-900 mb-2">No entities found</h3>
                      <p className="text-gray-500">No consolidated entity information available.</p>
                    </div>
                  </div>
                ) : (
                  final_entities.map((entity, entityIndex) => {
                    const fields = entity.combined_fields || {};
                    const entitySources = entity.sources || [];
                    const fieldSources = entity.field_sources || {};

                    // Convert fields to table rows
                    const tableRows = [];
                    Object.entries(fields)
                      .sort(compareFieldKeys)
                      .forEach(([key, value]) => {
                        if (value && value !== '' && value !== null) {
                          let displayValue;
                          if (Array.isArray(value) || (typeof value === 'object' && value !== null)) {
                            // Use the improved renderNestedObject function for complex data
                            displayValue = renderNestedObject(value);
                          } else {
                            displayValue = String(value);
                          }

                          const categoryName = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

                          // Use only per-entity field-specific source IDs
                          const fieldSourceIds = fieldSources[key] || [];

                          tableRows.push({
                            category: categoryName,
                            details: displayValue,
                            sources: fieldSourceIds.slice(0, 3), // Show up to 3 source IDs per field
                            allSources: fieldSourceIds
                          });
                        }
                      });

                    return (
                      <div key={entityIndex} className="bg-white shadow overflow-hidden sm:rounded-lg border-gray-100 border">
                        {/* Entity Header */}
                        <div className="px-4 py-5 sm:px-6 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-purple-50">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center">
                              <div className="flex-shrink-0">
                                <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                                  <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                  </svg>
                                </div>
                              </div>
                              <div className="ml-4">
                                <h3 className="text-lg leading-6 font-medium text-gray-900">
                                  {entity.canonical_name || 'Unknown Entity'}
                                </h3>
                                <p className="mt-1 text-sm text-gray-500">
                                  Entity #{entityIndex + 1} • {tableRows.length} attributes found
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center space-x-2">
                              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${entity.same_as_query
                                ? 'bg-green-100 text-green-800'
                                : 'bg-yellow-100 text-yellow-800'
                                }`}>
                                {entity.same_as_query ? '✓ Exact Match' : '~ Similar Match'}
                                {typeof entity.name_similarity_to_query === 'number' && (
                                  <>
                                    {' '}
                                    ({Math.round((entity.name_similarity_to_query || 0) * 100)}%)
                                  </>
                                )}
                              </span>
                              {entitySources.length > 0 && (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                  {entitySources.length} Sources
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Entity Details Table */}
                        {tableRows.length > 0 ? (
                          <div className="overflow-hidden">
                            <table className="min-w-full divide-y divide-gray-200">
                              <thead className="bg-gray-50">
                                <tr>
                                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/4">
                                    Category
                                  </th>
                                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/2">
                                    Details
                                  </th>
                                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-1/4">
                                    Sources
                                  </th>
                                </tr>
                              </thead>
                              <tbody className="bg-white divide-y divide-gray-200">
                                {tableRows.map((row, rowIndex) => (
                                  <tr key={rowIndex} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                      {row.category}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-900">
                                      <div className="max-w-xs lg:max-w-md xl:max-w-lg break-words">
                                        {row.details}
                                      </div>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500">
                                      <div className="flex flex-wrap gap-1">
                                        {row.sources.length > 0 ? (
                                          <>
                                            {row.sources.map((sourceId, sourceIndex) => (
                                              <a
                                                key={sourceIndex}
                                                href={getSourceUrl(sourceId)}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="inline-flex items-center px-2 py-1 rounded text-xs bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors"
                                                title={getSourceUrl(sourceId)}
                                              >
                                                <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                </svg>
                                                {sourceId}
                                              </a>
                                            ))}
                                            {Array.isArray(row.allSources) && row.allSources.length > 3 && (
                                              <button
                                                type="button"
                                                onClick={() => openSourcesModal(row.category, row.allSources)}
                                                className="inline-flex items-center px-2 py-1 rounded text-xs bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
                                              >
                                                View all ({row.allSources.length})
                                              </button>
                                            )}
                                          </>
                                        ) : (
                                          <span className="text-gray-400 italic text-xs">No sources</span>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div className="px-6 py-8 text-center">
                            <p className="text-gray-500 text-sm">No detailed information available for this entity.</p>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}


            {activeTab === 'clusters' && (
              <div className="bg-white shadow-lg overflow-hidden rounded-xl border border-gray-100">
                <div className="px-6 py-6 sm:px-8 bg-gradient-to-r from-orange-50 to-amber-50">
                  <h3 className="text-xl leading-6 font-bold text-gray-900 flex items-center">
                    <div className="w-3 h-3 bg-orange-500 rounded-full mr-3"></div>
                    Profile Clusters
                  </h3>
                  <p className="mt-2 text-sm text-gray-600">Profiles grouped by detected entity name and certainty level.</p>
                </div>
                <div className="px-6 py-6 sm:px-8">
                  {(!clusters || Object.keys(clusters).length === 0) ? (
                    <div className="text-center py-12">
                      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                        </svg>
                      </div>
                      <h3 className="text-lg font-medium text-gray-900 mb-2">No clusters found</h3>
                      <p className="text-gray-500">No profile clusters available.</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      {Object.entries(clusters || {}).map(([name, items]) => (
                        <div key={name} className="bg-gradient-to-br from-white to-orange-50 border border-orange-200 rounded-xl p-6 shadow-sm hover:shadow-md transition-all duration-200">
                          <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center">
                              <div className="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center mr-3">
                                <svg className="w-6 h-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                                </svg>
                              </div>
                              <div>
                                <h4 className="text-lg font-bold text-gray-900 break-words capitalize">{name.replace(/_/g, ' ')}</h4>
                                <p className="text-sm text-gray-500">Cluster Group</p>
                              </div>
                            </div>
                            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-orange-100 text-orange-800 border border-orange-200">
                              {Array.isArray(items) ? items.length : 0} profiles
                            </span>
                          </div>

                          <div className="space-y-3 max-h-80 overflow-auto">
                            {Array.isArray(items) && items.map((p, i) => (
                              <div key={i} className="bg-white border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                                <div className="flex items-start justify-between mb-2">
                                  <h5 className="font-semibold text-gray-900 break-words text-sm">
                                    {p.source_title || p.detected_entity_name || 'Profile'}
                                  </h5>
                                  <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                                    Profile {i + 1}
                                  </span>
                                </div>

                                {p.source_url && (
                                  <div className="mb-3">
                                    <a href={p.source_url} target="_blank" rel="noreferrer"
                                      className="inline-flex items-center text-xs text-blue-600 hover:text-blue-800 break-all">
                                      <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                      </svg>
                                      View Source
                                    </a>
                                  </div>
                                )}

                                {p.extracted_info && Object.keys(p.extracted_info).length > 0 && (
                                  <div className="border-t border-gray-100 pt-3">
                                    <h6 className="text-xs font-semibold text-gray-600 mb-2">Key Information:</h6>
                                    <div className="grid grid-cols-1 gap-2">
                                      {Object.entries(p.extracted_info).sort(compareFieldKeys).slice(0, 4).map(([k, v]) => (
                                        <div key={k} className="flex justify-between items-start">
                                          <span className="text-xs font-medium text-gray-600 capitalize">{k.replace(/_/g, ' ')}:</span>
                                          <span className="text-xs text-gray-900 ml-2 text-right">
                                            {typeof v === 'object' && v !== null ? renderNestedObject(v) : String(v)}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'mentions' && (
              <div className="bg-white shadow overflow-hidden sm:rounded-lg">
                <div className="px-4 py-5 sm:px-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg leading-6 font-medium text-gray-900">
                        Adverse Mentions
                      </h3>
                      <p className="mt-1 max-w-2xl text-sm text-gray-500">
                        Potential adverse information found in public records.
                      </p>
                    </div>
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
                      {adverse_mentions?.length || 0} found
                    </span>
                  </div>
                </div>
                <div className="border-t border-gray-200">
                  {adverse_mentions?.length > 0 ? (
                    <ul className="divide-y divide-gray-200">
                      {adverse_mentions.map((mention, index) => (
                        <li key={index} className="px-4 py-5 sm:px-6 hover:bg-gray-50 transition-colors">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center">
                              <div className="flex-shrink-0">
                                {mention.severity === 'high' ? (
                                  <ExclamationTriangleIcon className="h-5 w-5 text-red-500" />
                                ) : mention.severity === 'medium' ? (
                                  <InformationCircleIcon className="h-5 w-5 text-yellow-500" />
                                ) : (
                                  <CheckCircleIcon className="h-5 w-5 text-green-500" />
                                )}
                              </div>
                              <p className="ml-3 text-sm font-medium text-gray-900">
                                {mention.title}
                              </p>
                            </div>
                            <div className="ml-2 flex-shrink-0 flex">
                              {getSeverityBadge(mention.severity)}
                            </div>
                          </div>
                          <div className="mt-2 sm:flex sm:justify-between">
                            <div className="sm:flex">
                              <p className="flex items-center text-sm text-gray-500">
                                <span className="font-medium">Source:</span> {mention.source}
                              </p>
                              <p className="mt-2 flex items-center text-sm text-gray-500 sm:mt-0 sm:ml-6">
                                <ClockIcon className="flex-shrink-0 mr-1.5 h-4 w-4 text-gray-400" />
                                {mention.date}
                              </p>
                            </div>
                          </div>
                          <div className="mt-3">
                            <p className="text-sm text-gray-600">
                              {mention.snippet}
                            </p>
                            <div className="mt-2">
                              <a
                                href="#"
                                className="inline-flex items-center text-sm font-medium text-blue-600 hover:text-blue-500"
                              >
                                View full article <span aria-hidden="true">→</span>
                              </a>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="text-center py-12">
                      <CheckCircleIcon className="mx-auto h-12 w-12 text-green-500" />
                      <h3 className="mt-2 text-sm font-medium text-gray-900">No adverse mentions found</h3>
                      <p className="mt-1 text-sm text-gray-500">
                        No adverse information was found for this entity in our database.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'sources' && (
              <div className="bg-white shadow overflow-hidden sm:rounded-lg">
                <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg leading-6 font-medium text-gray-900">
                        Information Sources
                      </h3>
                      <p className="mt-1 max-w-2xl text-sm text-gray-500">
                        Websites and documents used to gather information about this entity.
                      </p>
                    </div>
                    <div className="flex items-center space-x-4">
                      <div className="flex items-center space-x-2">
                        <label htmlFor="sources-per-page" className="text-sm text-gray-700">Show:</label>
                        <select
                          id="sources-per-page"
                          value={sourcesPerPage}
                          onChange={(e) => {
                            setSourcesPerPage(Number(e.target.value));
                            setSourcesPage(1);
                          }}
                          className="border border-gray-300 rounded text-sm px-2 py-1"
                        >
                          <option value={10}>10</option>
                          <option value={25}>25</option>
                          <option value={50}>50</option>
                          <option value={100}>100</option>
                        </select>
                        <span className="text-sm text-gray-700">per page</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="border-t border-gray-200">
                  {(!sources || sources.length === 0) ? (
                    <div className="px-4 py-4 text-center text-gray-500">
                      No sources available
                    </div>
                  ) : (
                    <>
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                #
                              </th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Source
                              </th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                URL
                              </th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Status
                              </th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {sources
                              .slice((sourcesPage - 1) * sourcesPerPage, sourcesPage * sourcesPerPage)
                              .map((source, index) => (
                                <tr key={index} className="hover:bg-gray-50">
                                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                    {source.source_id || ((sourcesPage - 1) * sourcesPerPage + index + 1)}
                                  </td>
                                  <td className="px-6 py-4 whitespace-nowrap">
                                    <div className="text-sm font-medium text-blue-600 truncate max-w-xs" title={source.title || source.url}>
                                      <a href={source.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                                        {source.title || source.url}
                                      </a>
                                    </div>
                                  </td>
                                  <td className="px-6 py-4 text-sm text-gray-500 break-all max-w-xs">
                                    <div className="truncate" title={source.url}>
                                      {source.url}
                                    </div>
                                  </td>
                                  <td className="px-6 py-4 whitespace-nowrap">
                                    <div className="flex items-center space-x-2">
                                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${source.success ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                        {source.success ? 'Success' : 'Error'}
                                      </span>
                                      <span className="text-xs text-gray-500">
                                        {source.status_code}
                                      </span>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                      {sources.length > sourcesPerPage && (
                        <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
                          <div className="flex-1 flex justify-between sm:hidden">
                            <button
                              onClick={() => setSourcesPage(Math.max(1, sourcesPage - 1))}
                              disabled={sourcesPage === 1}
                              className="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                            >
                              Previous
                            </button>
                            <button
                              onClick={() => setSourcesPage(Math.min(Math.ceil(sources.length / sourcesPerPage), sourcesPage + 1))}
                              disabled={sourcesPage >= Math.ceil(sources.length / sourcesPerPage)}
                              className="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                            >
                              Next
                            </button>
                          </div>
                          <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                            <div>
                              <p className="text-sm text-gray-700">
                                Showing{' '}
                                <span className="font-medium">{(sourcesPage - 1) * sourcesPerPage + 1}</span>
                                {' '}to{' '}
                                <span className="font-medium">
                                  {Math.min(sourcesPage * sourcesPerPage, sources.length)}
                                </span>
                                {' '}of{' '}
                                <span className="font-medium">{sources.length}</span>
                                {' '}results
                              </p>
                            </div>
                            <div>
                              <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Pagination">
                                <button
                                  onClick={() => setSourcesPage(Math.max(1, sourcesPage - 1))}
                                  disabled={sourcesPage === 1}
                                  className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                >
                                  <span className="sr-only">Previous</span>
                                  <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                                    <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd" />
                                  </svg>
                                </button>
                                {Array.from({ length: Math.ceil(sources.length / sourcesPerPage) }, (_, i) => i + 1)
                                  .filter(page =>
                                    page === 1 ||
                                    page === Math.ceil(sources.length / sourcesPerPage) ||
                                    Math.abs(page - sourcesPage) <= 2
                                  )
                                  .map((page, index, array) => (
                                    <Fragment key={page}>
                                      {index > 0 && array[index - 1] !== page - 1 && (
                                        <span className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700">
                                          ...
                                        </span>
                                      )}
                                      <button
                                        onClick={() => setSourcesPage(page)}
                                        className={`relative inline-flex items-center px-4 py-2 border text-sm font-medium ${page === sourcesPage
                                          ? 'z-10 bg-blue-50 border-blue-500 text-blue-600'
                                          : 'bg-white border-gray-300 text-gray-500 hover:bg-gray-50'
                                          }`}
                                      >
                                        {page}
                                      </button>
                                    </Fragment>
                                  ))}
                                <button
                                  onClick={() => setSourcesPage(Math.min(Math.ceil(sources.length / sourcesPerPage), sourcesPage + 1))}
                                  disabled={sourcesPage >= Math.ceil(sources.length / sourcesPerPage)}
                                  className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                >
                                  <span className="sr-only">Next</span>
                                  <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                                    <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                                  </svg>
                                </button>
                              </nav>
                            </div>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        <div className="mt-8 text-center">
          <button
            onClick={handleNewSearch}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            <MagnifyingGlassIcon className="-ml-1 mr-2 h-5 w-5" />
            Perform Another Search
          </button>
        </div>
      </div>

      {/* View All Sources Modal */}
      {showSourcesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={closeSourcesModal} />
          <div className="relative w-full max-w-2xl mx-4 bg-white rounded-lg shadow-xl">
            <div className="px-5 py-4 border-b flex items-center justify-between">
              <h3 className="text-base font-semibold text-gray-900">All Sources for {modalField}</h3>
              <button onClick={closeSourcesModal} className="text-gray-500 hover:text-gray-700 text-sm">Close</button>
            </div>
            <div className="max-h-[65vh] overflow-auto p-4">
              {(!modalSourceIds || modalSourceIds.length === 0) ? (
                <div className="text-sm text-gray-500">No sources available.</div>
              ) : (
                <ul className="divide-y divide-gray-200">
                  {modalSourceIds.map((sid, idx) => {
                    const url = getSourceUrl(sid);
                    const domain = getDomain(url);
                    const title = sourceIdToDetails[sid]?.title || url;
                    return (
                      <li key={`${sid}-${idx}`} className="py-3">
                        <div className="flex items-start justify-between">
                          <div className="min-w-0 pr-3">
                            <div className="text-xs text-gray-500 mb-0.5">Source #{sid}</div>
                            <div className="text-sm font-medium text-gray-900 truncate" title={title}>{title}</div>
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-600 hover:text-blue-800 break-all"
                              title={url}
                            >
                              {domain}
                            </a>
                          </div>
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center px-2 py-1 rounded text-xs bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors"
                            title="Open link"
                          >
                            Open
                          </a>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <div className="px-5 py-3 border-t bg-gray-50 text-right">
              <button onClick={closeSourcesModal} className="inline-flex items-center px-3 py-1.5 rounded text-sm bg-gray-200 hover:bg-gray-300 text-gray-800">Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
;

export default Results;
