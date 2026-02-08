import requests
from bs4 import BeautifulSoup

def perform_web_search(query):
    try:
        # Send an HTTP GET request to the URL
        iterate = [lifeprint(), signingsavvy(), handspeak(), spreadthesign(), youglish(), aslcore(), aslsignbank(), signasl()]
        iterResponse = []
        for link in iterate:
            # run queries for multiple sites
            iterResponse.append(requests.get(link))
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
# format = https://www.signingsavvy.com/search/{word to be searched}
async def signingsavvy(arg):
    pass
#search HandSpeak
# maybe need to generate a dictionary of HandSpeaks website to connect words to the numbers listed
async def handspeak(arg):
    payload = {'key1':'value1', 'key2':'value2'}
    r = requests.post('https://handspeak.com/word/', data=payload)
    print(r.content)
#search spread the sign
#format = https://www.spreadthesign.com/en.us/search/?q={word to be searched}
async def spreadthesign(arg):
    link = 'https://www.spreadthesign.com/en.us/search/?q='+{arg}
    return link
#search youglish
# https://youglish.com/pronounce/{word to be searched}/signlanguage
async def youglish(arg):
    link = "https://youglish.com/pronounce/"+{arg}+"/signlanguage"
    pass
#search aslcore
# format = https://aslcore.org/search/?query={word to be searched}
async def aslcore(arg):
    link = "https://aslcore.org/search/?query="+{arg}
    pass
#search asl signbank
# format = http://aslsignbank.haskins.yale.edu/signs/search/?search={word to be searched}
async def aslsignbank(arg):
    link = "http://aslsignbank.haskins.yale.edu/signs/search/?search="+{arg}
    pass
#search signasl.org
#format = https://www.signasl.org/sign/{word to be searched}
async def signasl(arg):
    link = "https://www.signasl.org/sign/"+{arg}
    pass