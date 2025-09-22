import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { XMarkIcon, MagnifyingGlassIcon, PlusCircleIcon, XCircleIcon } from '@heroicons/react/24/outline';

const Search = () => {
  const [entityName, setEntityName] = useState('');
  const [entityType, setEntityType] = useState('');
  const [keywords, setKeywords] = useState(['']);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const navigate = useNavigate();

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownOpen && !event.target.closest('.dropdown-container')) {
        setDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen]);

  // Animation variants
  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.1
      }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 10 },
    visible: { opacity: 1, y: 0 }
  };

  const handleKeywordChange = (index, value) => {
    const newKeywords = [...keywords];
    newKeywords[index] = value;
    setKeywords(newKeywords);
  };

  const addKeyword = (e) => {
    e?.preventDefault();
    if (keywords.length < 5) {
      setKeywords([...keywords, '']);
      // Focus the new input after it's rendered
      setTimeout(() => {
        const inputs = document.querySelectorAll('input[type="text"]');
        if (inputs.length > 0) {
          inputs[inputs.length - 1].focus();
        }
      }, 0);
    }
  };

  const removeKeyword = (index) => {
    if (keywords.length > 1) {
      const newKeywords = keywords.filter((_, i) => i !== index);
      setKeywords(newKeywords);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Basic validation
    if (!entityName.trim()) {
      setError('Please enter an entity name');
      return;
    }

    if (!entityType) {
      setError('Please select an entity type');
      return;
    }

    // Filter out empty keywords
    const validKeywords = keywords.filter(keyword => keyword.trim() !== '');
    
    if (validKeywords.length === 0) {
      setError('Please add at least one keyword');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      // Call the API
      const response = await fetch('http://localhost:8000/research-entity-async', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          entity_name: entityName.trim(),
          entity_type: entityType,
          keywords: validKeywords,
        }),
      });

      const data = await response.json();
      
      if (!response.ok) {
        // Handle API error responses
        const errorMessage = data.detail || data.message || 'Search failed. Please try again.';
        throw new Error(errorMessage);
      }
      
      if (!data) {
        throw new Error('Invalid response from server');
      }
      
      // Navigate to results page with researchId for polling
      navigate('/results', { 
        state: { 
          researchId: data.research_id
        } 
      });
      
    } catch (err) {
      console.error('Search error:', err);
      const errorMessage = err.message || 'An unexpected error occurred. Please try again.';
      setError(errorMessage);
      
      // Auto-hide error after 5 seconds
      const timer = setTimeout(() => {
        setError('');
      }, 5000);
      
      return () => clearTimeout(timer);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 px-4 sm:px-6 lg:px-8 pt-18">
      <motion.div 
        className="max-w-3xl mx-auto"
        initial="hidden"
        animate="visible"
        variants={containerVariants}
      >
        <motion.div 
          className="text-center mb-5"
          variants={itemVariants}
        >
          <h1 className="text-3xl font-bold text-gray-900">
            Search Entity
          </h1>
          <p className="mt-2 text-base text-gray-600">
            Enter the entity name and related keywords to perform a comprehensive search.
          </p>
        </motion.div>

        <motion.div 
          className={`bg-white p-6 rounded-2xl shadow-xl transition-all duration-300 ${
            isFocused ? 'ring-2 ring-blue-500' : 'shadow-sm'
          }`}
          variants={itemVariants}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
        >
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Entity Name */}
            <motion.div variants={itemVariants}>
              <label htmlFor="entityName" className="block text-sm font-medium text-gray-700 mb-1">
                Entity Name <span className="text-red-500">*</span>
              </label>
              <div className="relative mt-1 rounded-md shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                </div>
                <input
                  type="text"
                  id="entityName"
                  value={entityName}
                  onChange={(e) => setEntityName(e.target.value)}
                  className="focus:ring-blue-500 focus:border-blue-500 block w-full pl-10 sm:text-sm border-gray-300 rounded-lg p-3 border"
                  placeholder="e.g. John Doe or Acme Corp"
                  disabled={isLoading}
                  autoComplete="off"
                />
              </div>
            </motion.div>

            {/* Entity Type */}
            <motion.div variants={itemVariants}>
              <label htmlFor="entityType" className="block text-sm font-medium text-gray-700 mb-2">
                Entity Type <span className="text-red-500">*</span>
              </label>
              <div className="relative dropdown-container">
                <button
                  type="button"
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                  className={`
                    w-full text-left px-4 py-3 pr-10 border border-gray-300 rounded-lg
                    bg-white shadow-sm transition-all duration-200 outline-none
                    focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                    hover:border-blue-400 hover:shadow-md
                    ${entityType ? 'text-gray-900' : 'text-gray-500'}
                    ${isLoading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                  `}
                  disabled={isLoading}
                >
                  {entityType === 'individual' ? 'Individual Person' : 
                   entityType === 'company' ? 'Company / Organization' : 
                   'Choose entity type...'}
                </button>
                
                {/* Dropdown Arrow */}
                <div className="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none">
                  <svg 
                    className={`h-5 w-5 text-blue-500 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>

                {/* Custom Dropdown Options */}
                {dropdownOpen && (
                  <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-xl overflow-hidden">
                    <div 
                      className="px-4 py-3 hover:bg-blue-50 cursor-pointer transition-colors duration-150 border-b border-gray-100"
                      onClick={() => {
                        setEntityType('individual');
                        setDropdownOpen(false);
                      }}
                    >
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                          <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                          </svg>
                        </div>
                        <div>
                          <div className="font-medium text-gray-900">Individual Person</div>
                          <div className="text-sm text-gray-500">Search for people, celebrities, professionals</div>
                        </div>
                      </div>
                    </div>
                    
                    <div 
                      className="px-4 py-3 hover:bg-blue-50 cursor-pointer transition-colors duration-150"
                      onClick={() => {
                        setEntityType('company');
                        setDropdownOpen(false);
                      }}
                    >
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                          <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                          </svg>
                        </div>
                        <div>
                          <div className="font-medium text-gray-900">Company / Organization</div>
                          <div className="text-sm text-gray-500">Search for businesses, startups, organizations</div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              
              <p className="mt-2 text-sm text-gray-600">
                Select the type of entity you want to research for better targeted results.
              </p>
            </motion.div>

            {/* Keywords */}
            <motion.div variants={itemVariants}>
              <div className="flex justify-between items-center mb-2">
                <label className="block text-sm font-medium text-gray-700">
                  Combination Keywords <span className="text-red-500">*</span>
                </label>
                <button
                  type="button"
                  onClick={addKeyword}
                  disabled={keywords.length >= 5 || isLoading}
                  className="inline-flex items-center px-2.5 py-1.5 border border-transparent text-xs font-medium rounded text-blue-700 bg-blue-100 hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <PlusCircleIcon className="h-4 w-4 mr-1" />
                  Add Keyword
                </button>
              </div>
              
              <div className="space-y-3">
                <AnimatePresence>
                  {keywords.map((keyword, index) => (
                    <motion.div 
                      key={index}
                      className="flex space-x-2 items-center"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, x: -10, height: 0, margin: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <div className="relative flex-1">
                        <input
                          type="text"
                          value={keyword}
                          onChange={(e) => handleKeywordChange(index, e.target.value)}
                          className="focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-lg p-2.5 border shadow-sm"
                          placeholder={`Keyword ${index + 1}`}
                          disabled={isLoading}
                          autoComplete="off"
                        />
                        {keywords.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeKeyword(index)}
                            disabled={isLoading}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-red-500 focus:outline-none disabled:opacity-50"
                          >
                            <XMarkIcon className="h-5 w-5" />
                          </button>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
              <p className="mt-2 text-xs text-gray-500">
                Add keywords to refine your search (e.g., "CEO", "New York", "Tech").
              </p>
            </motion.div>

            {/* Error Message */}
            <AnimatePresence>
              {error && (
                <motion.div 
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded flex items-start"
                >
                  <XCircleIcon 
                    className="h-5 w-5 mr-2 mt-0.5 flex-shrink-0 text-red-500 cursor-pointer"
                    onClick={() => setError('')}
                  />
                  <div>
                    <p className="font-medium">Error</p>
                    <p className="text-sm">{error}</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Submit Button */}
            <motion.div 
              className="pt-2"
              variants={itemVariants}
            >
              <button
                type="submit"
                disabled={isLoading}
                className={`w-full flex justify-center items-center py-3 px-4 border border-transparent rounded-xl shadow-sm text-base font-medium text-white bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-700 hover:to-blue-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-200 transform hover:-translate-y-0.5 ${
                  isLoading ? 'opacity-80 cursor-not-allowed' : ''
                }`}
              >
                {isLoading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Searching...
                  </>
                ) : (
                  <>
                    <MagnifyingGlassIcon className="w-5 h-5 mr-2" />
                    Search Now
                  </>
                )}
              </button>
            </motion.div>
          </form>
        </motion.div>

        {/* <motion.div 
          className="mt-8 text-center text-sm text-gray-500"
          variants={itemVariants}
        >
          <p>Need help with your search? <a href="#" className="font-medium text-blue-600 hover:text-blue-500">Contact support</a></p>
        </motion.div> */}
      </motion.div>
    </div>
  );
};

export default Search;
