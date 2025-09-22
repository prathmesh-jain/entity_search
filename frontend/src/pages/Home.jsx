import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  MagnifyingGlassIcon,
  ChartBarIcon,
  ShieldCheckIcon,
  DocumentMagnifyingGlassIcon,
  ArrowRightIcon,
  BoltIcon,
  ScaleIcon,
  GlobeAltIcon
} from '@heroicons/react/24/outline';

const features = [
  {
    name: 'Multi-Engine Search',
    description: 'Simultaneously search Google, Bing, and Yahoo to ensure no relevant information is missed.',
    icon: MagnifyingGlassIcon,
    color: 'bg-blue-100 text-blue-600'
  },
  {
    name: 'AI Data Extraction',
    description: 'Advanced AI extracts 25+ structured data points including personal details, business info, and more.',
    icon: ChartBarIcon,
    color: 'bg-purple-100 text-purple-600'
  },
  {
    name: 'Smart Entity Matching',
    description: 'Intelligent algorithms ensure accurate entity identification and consolidation across sources.',
    icon: ShieldCheckIcon,
    color: 'bg-green-100 text-green-600'
  },
  {
    name: 'Comprehensive Analysis',
    description: 'Get detailed profiles with source attribution and confidence scoring for reliable insights.',
    icon: DocumentMagnifyingGlassIcon,
    color: 'bg-amber-100 text-amber-600'
  },
];

const stats = [
  { id: 1, name: 'Major Search Engines', value: 'All 3', icon: GlobeAltIcon },
  { id: 2, name: 'Data Points Extracted', value: '25+', icon: ChartBarIcon },
  { id: 3, name: 'AI-Powered Analysis', value: 'Advanced', icon: ScaleIcon },
  { id: 4, name: 'Processing Time', value: '~2 min', icon: BoltIcon },
];

const Home = () => {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white pt-10">
      {/* Hero Section */}
      <div className="relative overflow-hidden pt-24 pb-20">
        <div className="relative
          before:absolute before:top-0 before:left-1/2 before:bg-[radial-gradient(circle_800px_at_100%_200px,#3b82f6,transparent)] before:no-underline before:absolute before:-translate-x-1/2 before:rounded-full before:blur-3xl before:w-[120%] before:h-48 before:opacity-30
          after:absolute after:top-0 after:left-1/2 after:bg-[radial-gradient(circle_400px_at_50%_300px,#3b82f6,transparent)] after:no-underline after:absolute after:-translate-x-1/2 after:rounded-full after:blur-3xl after:w-[100%] after:h-32 after:opacity-30
        ">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
            <div className="text-center">
              <motion.h1 
                className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl "
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
              >
                Advanced <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-blue-400">Entity Search</span> & Verification
              </motion.h1>
              <motion.p 
                className="mt-6 max-w-2xl mx-auto text-xl text-gray-600"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.1 }}
              >
Comprehensive entity research using multiple search engines with AI-powered data extraction and analysis.
              </motion.p>
              <motion.div 
                className="mt-10 flex items-center justify-center gap-x-6"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.2 }}
              >
                <Link
                  to="/search"
                  className="group relative inline-flex items-center px-6 py-3.5 text-base font-medium text-white bg-gradient-to-r from-blue-600 to-blue-500 rounded-lg shadow-lg hover:from-blue-700 hover:to-blue-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-200 transform hover:-translate-y-0.5"
                >
                  Start Searching
                  <ArrowRightIcon className="ml-2 -mr-1 h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </Link>
                <a
                  href="#features"
                  className="text-base font-medium text-blue-600 hover:text-blue-500"
                >
                  Learn more <span aria-hidden="true">→</span>
                </a>
              </motion.div>
            </div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="bg-white py-12 sm:py-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <dl className="grid grid-cols-1 gap-x-8 gap-y-16 text-center lg:grid-cols-4">
            {stats.map((stat) => (
              <div key={stat.id} className="mx-auto flex max-w-xs flex-col gap-y-4">
                <dt className="text-base leading-7 text-gray-600">{stat.name}</dt>
                <div className="order-first text-3xl font-semibold tracking-tight text-gray-900 sm:text-4xl">
                  {stat.value}
                </div>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {/* Features Section */}
      <div id="features" className="py-16 bg-gradient-to-b from-white to-gray-50 sm:py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="lg:text-center">
            <h2 className="text-base font-semibold text-blue-600 tracking-wide uppercase">Features</h2>
            <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
Powerful tools for comprehensive entity research
            </p>
            <p className="mt-4 max-w-2xl text-xl text-gray-500 lg:mx-auto">
Our advanced platform searches major search engines and uses cutting-edge AI to extract and analyze over 25 structured data points with remarkable precision.
            </p>
          </div>

          <div className="mt-20">
            <div className="grid grid-cols-1 gap-12 sm:grid-cols-2 lg:grid-cols-4">
              {features.map((feature, index) => (
                <motion.div 
                  key={feature.name}
                  className="relative"
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: index * 0.1 }}
                >
                  <div className="relative bg-white p-6 rounded-2xl shadow-lg hover:shadow-xl transition-shadow duration-300 h-full flex flex-col">
                    <div className="absolute -top-6 left-6">
                      <div className={`flex items-center justify-center h-12 w-12 rounded-xl ${feature.color} shadow-md`}>
                        <feature.icon className="h-6 w-6" aria-hidden="true" />
                      </div>
                    </div>
                    <h3 className="mt-8 text-lg font-semibold text-gray-900">
                      {feature.name}
                    </h3>
                    <p className="mt-4 text-base text-gray-600 flex-grow">
                      {feature.description}
                    </p>
                    <div className="mt-6">
                      <Link
                        to="/search"
                        className="text-sm font-medium text-blue-600 hover:text-blue-500 flex items-center"
                      >
                        Try it out <ArrowRightIcon className="ml-1 h-4 w-4" />
                      </Link>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </div>

    </div>
  );
};

export default Home;
