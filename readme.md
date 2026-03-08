# ASL Dictionary Discord Bot

A Discord bot designed to help users quickly look up **American Sign Language (ASL)** signs from multiple online dictionaries directly inside Discord.

The bot aggregates results from several ASL learning resources and presents them in a clean, organized format to make sign lookup faster and easier for students, interpreters, and ASL learners.

---

## Purpose

This bot was created to make **ASL sign lookup accessible within Discord communities** such as:

- ASL learning servers
- Deaf/Hard of Hearing communities
- Interpreter training groups
- Linguistics communities
- Educational servers

Instead of searching multiple websites manually, users can run a single command and see results from several ASL dictionaries at once.

---

## Features

### Sign Lookup Command

Users can search for ASL signs using a simple command.

Example: /sign hello


The bot searches multiple ASL dictionaries and returns matching results.

Results are prioritized and displayed in this order:

1. LifePrint
2. Handspeak
3. SigningSavvy
4. SignASL
5. ASLCore
6. SpreadTheSign

Exact matches appear first, followed by similar matches when available.

---

### Multi-Dictionary Support

The bot pulls sign results from multiple sources, including:

- LifePrint
- Handspeak
- SigningSavvy
- SignASL
- ASLCore
- SpreadTheSign

Each provider can maintain its own local dictionary cache for faster lookups.

---

### Local Dictionary Storage

The bot stores scraped dictionary entries locally using JSONL files.

Benefits:

- Faster searches
- Reduced API/web requests
- Easier debugging
- Easier provider separation

Example storage files:
- handspeak-dict.txt
- lifeprint-dict.txt
- signingsavvy-dict.txt
- aslcore-dict.txt
---
To Create Your Own Discord Bot
- Go to the Discord Developer Portal
- Create a new application
- Add a bot
- Copy the bot token
- Paste the token into the .env file
  - DISCORD_TOKEN=your_bot_token_here
- Run bot using `python bot.py`
- Example command: /sign hello
- Example output: 

ASL Sign Results for "HELLO"

LifePrint https://lifeprint.com/asl101/pages-signs/h/hello.htm

Handspeak https://handspeak.com/word/search/index.php?id=1023

SigningSavvy https://www.signingsavvy.com/sign/HELLO

---
Project Structure:
```
asl-discord-bot/
│
├── bot.py
├── cogs/
│   └── sign_lookup.py
│
├── data/
│   ├── handspeak-dict.txt
│   ├── lifeprint-dict.txt
│   └── ondemand-dict.txt
│
├── utils/
│   └── dictionary_tools.py
│
├── requirements.txt
└── README.md
```
---
Dependencies: 
- pip install -r requirements.txt
- discord.py
- aiohttp
- requests
- beautifulsoup4
---


# Disclaimer

This bot references publicly available ASL learning resources.
All dictionary content belongs to the original providers.

Please support the original ASL educators and websites whenever possible.

---

# Contributing

Pull requests and improvements are welcome.

Possible future improvements:

Synonym matching

Fuzzy search

Expanded dictionary support

Video previews

ASL practice tools

# Discord for testing changes: https://discord.gg/mQTHCwnTRR
