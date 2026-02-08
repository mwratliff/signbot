import requests
from bs4 import BeautifulSoup

def perform_web_search(query):
    first_letter = query[0].lower()
    search_url = f"https://www.lifeprint.com/asl101/pages-signs/{first_letter}/{query}.htm"
    try:
        # Send an HTTP GET request to the URL
        response = requests.get(search_url)
        response.raise_for_status()  # Raise an exception for bad status codes

        # Parse the HTML content of the page
        soup = BeautifulSoup(response.content, 'html.parser')

        # Example: Find all link tags (adjust based on actual website structure)
        # Look for specific CSS classes or IDs to pinpoint relevant results
        results = soup.find_all('a', class_='result-link')
        print(soup)
        if results:
            first_result_title = results[0].get_text(strip=True)
            first_result_url = results[0]['href']
            return f"Found a result: [{first_result_title}]({first_result_url})"
        else:
            return "No relevant results found."

    except requests.exceptions.RequestException as e:
        return f"An error occurred during web request: {e}"
    except Exception as e:
        return f"An error occurred during parsing: {e}"



# when searching lifeprint, search for a web page and then search youtube channel
# if no page, search youtube channel for closest matching video

async def lifeprint(arg):
    # search and see if a useful web page exists

    # Search youtube channel for a video
    signs_youtube = f"https://www.youtube.com/@aslu/search?query={arg}"
    print(f"Searching youtube channel for {arg}")

# input word to be searched in signingsavvy (if multiple words, add a +)