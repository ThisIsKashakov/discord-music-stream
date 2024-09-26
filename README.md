# 🎧 Discord Music Streaming Bot

A Discord bot that allows you to stream live audio from desktop music clients (such as Spotify, [`YouTube Music`](https://github.com/th-ch/youtube-music), Apple Music, and Yandex Music) directly into a Discord voice channel. It uses the desktop's loopback microphone to capture the audio output and broadcast it to your Discord voice channel in real-time.

## Features:
- **Real-time music streaming** from desktop clients (Spotify, Apple Music, [`YouTube Music`](https://github.com/th-ch/youtube-music), etc.) to Discord.
- **Automatic track updates** with rich embedded messages showing the current song title, artist, and album.
- **Custom presence** to display the currently playing track as the bot's status.
- **Discord voice integration**: Join and leave voice channels via bot commands.
- **Supports multiple music platforms** that use the Windows media controls.

## Requirements:
- Python 3.8+
- Discord bot token
- [`Virtual audio cable`](https://vb-audio.com/Cable/) (e.g., VB-Audio Virtual Cable) for loopback recording

## Setup:
1. Clone the repository and install the required packages using `pip install -r requirements.txt`.
2. Set up the `config.json` file with your Discord bot token, guild ID, and other settings.
3. [Configure `Virtual audio cable` for specific apps](./docs/virtual_audio_cable_setup.md) to ensure proper audio routing.
4. Start the bot, and it will automatically connect to the specified voice channel and begin streaming music.

## Usage:
- Use the `^join` command to make the bot join a voice channel.
- Use the `^leave` command to make the bot leave the voice channel.
- The bot will stream the music playing on your desktop client and display the current track in a Discord text channel.
