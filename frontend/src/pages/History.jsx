import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DeleteModal from '../components/DeleteModal';

const History = () => {
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchFilter, setSearchFilter] = useState('');
  const [pagination, setPagination] = useState({ limit: 10, offset: 0, has_more: false, total: 0, current_page: 1, total_pages: 1 });
  const [deleteModal, setDeleteModal] = useState({ isOpen: false, searchItem: null });
  const [isDeleting, setIsDeleting] = useState(false);
  const navigate = useNavigate();

  const fetchHistory = async (offset = 0, entityFilter = '') => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        limit: pagination.limit.toString(),
        offset: offset.toString()
      });

      if (entityFilter.trim()) {
        params.append('entity_name', entityFilter.trim());
      }

      const response = await fetch(`http://localhost:8000/history?${params}`);
      if (!response.ok) {
        throw new Error('Failed to fetch history');
      }

      const data = await response.json();
      setHistory(data.history || []);
      setStats(data.stats || {});
      setPagination(data.pagination || { limit: 10, offset: 0, has_more: false, total: 0, current_page: 1, total_pages: 1 });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleSearch = () => {
    setPagination(prev => ({ ...prev, offset: 0 }));
    fetchHistory(0, searchFilter);
  };

  const handlePageChange = (newPage) => {
    const newOffset = (newPage - 1) * pagination.limit;
    fetchHistory(newOffset, searchFilter);
  };

  const handleLoadMore = () => {
    const newOffset = pagination.offset + pagination.limit;
    fetchHistory(newOffset, searchFilter);
  };

  const handleDeleteSearch = (searchItem) => {
    setDeleteModal({ isOpen: true, searchItem });
  };

  const confirmDelete = async () => {
    if (!deleteModal.searchItem) return;

    try {
      setIsDeleting(true);
      const response = await fetch(`http://localhost:8000/history/${deleteModal.searchItem.research_id}`, {
        method: 'DELETE'
      });

      if (!response.ok) {
        throw new Error('Failed to delete search');
      }

      // Refresh the history
      await fetchHistory(pagination.offset, searchFilter);

      // Close modal
      setDeleteModal({ isOpen: false, searchItem: null });
    } catch (err) {
      alert(`Error deleting search: ${err.message}`);
    } finally {
      setIsDeleting(false);
    }
  };

  const closeDeleteModal = () => {
    if (!isDeleting) {
      setDeleteModal({ isOpen: false, searchItem: null });
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  const formatDate = (isoString) => {
    if (!isoString) return 'N/A';
    return new Date(isoString).toLocaleString();
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-100';
      case 'failed': return 'text-red-600 bg-red-100';
      case 'in_progress': return 'text-blue-600 bg-blue-100';
      case 'pending': return 'text-yellow-600 bg-yellow-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  if (loading && history.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading search history...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Search History</h1>
              <p className="mt-1 text-gray-600">View and manage your entity research history</p>
            </div>
            <button
              onClick={() => navigate('/')}
              className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              Back to Search
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Statistics Cards */}
        {Object.keys(stats).length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                    <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </div>
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Total Searches</p>
                  <p className="text-2xl font-semibold text-gray-900">{stats.total_searches || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                    <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Completed</p>
                  <p className="text-2xl font-semibold text-gray-900">{stats.completed_searches || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-yellow-100 rounded-full flex items-center justify-center">
                    <svg className="w-4 h-4 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Avg Duration</p>
                  <p className="text-2xl font-semibold text-gray-900">{formatDuration(stats.avg_duration_seconds)}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center">
                    <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500">Avg Sources</p>
                  <p className="text-2xl font-semibold text-gray-900">{Math.round(stats.avg_sources || 0)}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Search Filter */}
        <div className="bg-white rounded-lg shadow mb-6 p-6">
          <div className="flex flex-col sm:flex-row sm:items-end space-y-4 sm:space-y-0 sm:space-x-4">
            <div className="flex-1">
              <label htmlFor="search" className="block text-sm font-medium text-gray-700 mb-2">
                Filter by Entity Name
              </label>
              <input
                type="text"
                id="search"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Enter entity name to filter..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <div className="flex space-x-2 flex-shrink-0">
              <button
                onClick={handleSearch}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
              >
                Search
              </button>
              <button
                onClick={() => {
                  setSearchFilter('');
                  fetchHistory(0, '');
                }}
                className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 transition-colors"
              >
                Clear
              </button>
            </div>
          </div>
        </div>

        {/* History List */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          {error ? (
            <div className="p-6 text-center">
              <div className="text-red-600 mb-2">
                <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-gray-900 font-medium">Error loading history</p>
              <p className="text-gray-600">{error}</p>
              <button
                onClick={() => fetchHistory()}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Retry
              </button>
            </div>
          ) : history.length === 0 ? (
            <div className="p-6 text-center">
              <div className="text-gray-400 mb-4">
                <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-gray-900 font-medium">No search history found</p>
              <p className="text-gray-600">Start researching entities to see your search history here.</p>
              <button
                onClick={() => navigate('/')}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Start New Search
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Entity Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Started At
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Duration
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Results
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {history.map((search) => (
                    <tr key={search.research_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-wrap">
                        <div className="flex items-center">
                          <div className="flex-shrink-0 h-10 w-10">
                            <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center">
                              <span className="text-sm font-medium text-blue-600">
                                {search.entity_name.charAt(0).toUpperCase()}
                              </span>
                            </div>
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-gray-900">{search.entity_name}</div>
                            {search.keywords && search.keywords.length > 0 && (
                              <div className="text-sm text-gray-500">
                                Keywords: {search.keywords.join(', ')}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(search.status)}`}>
                          {search.status}
                        </span>
                        {/* {search.phase && search.phase !== search.status && (
                          <div className="text-xs text-gray-500 mt-1">{search.phase}</div>
                        )} */}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {formatDate(search.started_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {formatDuration(search.duration_seconds)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        <div className="space-y-1">
                          <div>Sources: {search.total_sources || 0}</div>
                          <div>Entities: {search.entities_found || 0}</div>
                          {/* <div>Pages: {search.crawled_pages || 0}</div> */}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-3">
                        {search.status === 'completed' && (
                          <button
                            onClick={() => navigate(`/results?research_id=${search.research_id}`)}
                            className="text-blue-600 hover:text-blue-900"
                            title="View Results"
                          >
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              width={16}
                              height={16}
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                              <circle cx="12" cy="12" r="3"></circle>
                            </svg>
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteSearch(search)}
                          className="text-red-600 hover:text-red-900"
                          title="Delete Result"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            width={16}
                            height={16}
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            <line x1="10" y1="11" x2="10" y2="17"></line>
                            <line x1="14" y1="11" x2="14" y2="17"></line>
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {pagination.total_pages > 1 && (
            <div className="px-6 py-4 border-t border-gray-200">
              <div className="flex items-center justify-between">
                <div className="flex-1 flex justify-between sm:hidden">
                  <button
                    onClick={() => handlePageChange(pagination.current_page - 1)}
                    disabled={pagination.current_page <= 1 || loading}
                    className="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => handlePageChange(pagination.current_page + 1)}
                    disabled={pagination.current_page >= pagination.total_pages || loading}
                    className="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
                <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm text-gray-700">
                      Showing{' '}
                      <span className="font-medium">{pagination.offset + 1}</span>
                      {' '}to{' '}
                      <span className="font-medium">
                        {Math.min(pagination.offset + pagination.limit, pagination.total)}
                      </span>
                      {' '}of{' '}
                      <span className="font-medium">{pagination.total}</span>
                      {' '}results
                    </p>
                  </div>
                  <div>
                    <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Pagination">
                      <button
                        onClick={() => handlePageChange(pagination.current_page - 1)}
                        disabled={pagination.current_page <= 1 || loading}
                        className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <span className="sr-only">Previous</span>
                        <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                          <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      </button>
                      
                      {/* Page Numbers */}
                      {(() => {
                        const pages = [];
                        const currentPage = pagination.current_page;
                        const totalPages = pagination.total_pages;
                        
                        // Always show first page
                        if (currentPage > 3) {
                          pages.push(
                            <button
                              key={1}
                              onClick={() => handlePageChange(1)}
                              className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50"
                            >
                              1
                            </button>
                          );
                          if (currentPage > 4) {
                            pages.push(
                              <span key="ellipsis1" className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700">
                                ...
                              </span>
                            );
                          }
                        }
                        
                        // Show pages around current page
                        for (let i = Math.max(1, currentPage - 2); i <= Math.min(totalPages, currentPage + 2); i++) {
                          pages.push(
                            <button
                              key={i}
                              onClick={() => handlePageChange(i)}
                              disabled={loading}
                              className={`relative inline-flex items-center px-4 py-2 border text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed ${
                                i === currentPage
                                  ? 'z-10 bg-blue-50 border-blue-500 text-blue-600'
                                  : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                              }`}
                            >
                              {i}
                            </button>
                          );
                        }
                        
                        // Always show last page
                        if (currentPage < totalPages - 2) {
                          if (currentPage < totalPages - 3) {
                            pages.push(
                              <span key="ellipsis2" className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700">
                                ...
                              </span>
                            );
                          }
                          pages.push(
                            <button
                              key={totalPages}
                              onClick={() => handlePageChange(totalPages)}
                              className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50"
                            >
                              {totalPages}
                            </button>
                          );
                        }
                        
                        return pages;
                      })()}
                      
                      <button
                        onClick={() => handlePageChange(pagination.current_page + 1)}
                        disabled={pagination.current_page >= pagination.total_pages || loading}
                        className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <span className="sr-only">Next</span>
                        <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                          <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                        </svg>
                      </button>
                    </nav>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* Load More Button (fallback for when pagination data is incomplete) */}
          {!pagination.total_pages && pagination.has_more && (
            <div className="px-6 py-4 border-t border-gray-200 text-center">
              <button
                onClick={handleLoadMore}
                disabled={loading}
                className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                    Loading...
                  </>
                ) : (
                  'Load More'
                )}
              </button>
            </div>
          )}
        </div>

        {/* Delete Confirmation Modal */}
        <DeleteModal
          isOpen={deleteModal.isOpen}
          onClose={closeDeleteModal}
          onConfirm={confirmDelete}
          entityName={deleteModal.searchItem?.entity_name || ''}
          isLoading={isDeleting}
        />
      </div>
    </div>
  );
};

export default History;
