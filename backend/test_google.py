import os
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Your Google API key and Custom Search Engine ID
# Ensure these are correctly set in your .env file
API_KEY = os.getenv("GOOGLE_API_KEY")
CX = os.getenv("GOOGLE_CX")

# The search query
QUERY = "Brandon Cox + Air Force Veteran and current South Carolina Representative"

# Build the service object for the API
service = build("customsearch", "v1", developerKey=API_KEY)

# A list to store all the search results
all_results = []

try:
    # --- First request: Get the first 10 results (start=1) ---
    print(f"Fetching results 1-10 for query: '{QUERY}'")
    results_page1 = service.cse().list(
        q=QUERY,
        cx=CX,
        num=10,  # Max number of results per request is 10
        start=1, # Starting result index
        gl='in'  # Set the location to India
    ).execute()

    if 'items' in results_page1:
        all_results.extend(results_page1['items'])
        print("Successfully fetched 10 results.")
    else:
        print("No search results found in the first page.")

    # --- Second request: Get the next 10 results (start=11) ---
    print(f"\nFetching results 11-20 for query: '{QUERY}'")
    results_page2 = service.cse().list(
        q=QUERY,
        cx=CX,
        num=10,
        start=11 # Start from the 11th result for the second page
    ).execute()

    if 'items' in results_page2:
        all_results.extend(results_page2['items'])
        print("Successfully fetched the next 10 results.")
    else:
        print("No further search results found (page 2).")

    # --- Print all 20 combined results ---
    print("\n--- All Combined Search Results (20 total) ---\n")
    if all_results:
        for i, item in enumerate(all_results, 1):
            title = item.get('title')
            link = item.get('link')
            
            # print(f"Result {i}:")
            # print(f"Title: {title}")
            print(f"Link: {link}\n")
    else:
        print("No search results were found for the query.")

except Exception as e:
    print(f"An error occurred: {e}")
