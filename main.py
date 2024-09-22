import asyncio
import discord
import soundcard as sc
import numpy as np
import io
import json
import zlib
from typing import Optional, Dict, Any, Mapping
from discord.ext import commands
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winsdk.windows.storage.streams import DataReader, Buffer, InputStreamOptions


def load_config() -> Dict[str, Any]:
    """Loads and validates configuration from config.json file."""
    try:
        with open("config.json", "r") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        raise SystemExit("Error: config.json file not found.")
    except json.JSONDecodeError:
        raise SystemExit("Error: config.json is not a valid JSON file.")

    required_keys = [
        "DISCORD_TOKEN",
        "GUILD_ID",
        "VOICE_CHANNEL_ID",
        "TEXT_CHANNEL_ID",
        "desktop_clients",
        "MICROPHONE_ID",
    ]
    for key in required_keys:
        if key not in config:
            raise SystemExit(f"Error: '{key}' is missing in config.json")
        if not config[key] and key != "desktop_clients":
            raise SystemExit(f"Error: '{key}' has an empty value in config.json")

    int_keys = ["GUILD_ID", "VOICE_CHANNEL_ID", "TEXT_CHANNEL_ID"]
    for key in int_keys:
        if not config[key].isdigit():
            raise SystemExit(f"Error: '{key}' must contain only digits in config.json")
        config[key] = int(config[key])

    if not isinstance(config["desktop_clients"], list) or not config["desktop_clients"]:
        raise SystemExit(
            "Error: 'desktop_clients' must be a non-empty list in config.json"
        )

    return config


try:
    CONFIG = load_config()
    TOKEN: str = CONFIG["DISCORD_TOKEN"]
    GUILD_ID: int = CONFIG["GUILD_ID"]
    VOICE_CHANNEL_ID: int = CONFIG["VOICE_CHANNEL_ID"]
    TEXT_CHANNEL_ID: int = CONFIG["TEXT_CHANNEL_ID"]
    DESKTOP_CLIENTS: list[str] = CONFIG["desktop_clients"]
    MICROPHONE_ID: str = CONFIG["MICROPHONE_ID"]
except SystemExit as e:
    print(e)
    exit(1)

CHUNK: int = 960
CHANNELS: int = 2
RATE: int = 48000

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="^", intents=intents)

mic = None
microphone = None
mic_stream = None
audio_task = None


last_media_info: Dict[str, Any] = {}
track_crc: Mapping[int, bool] = {}

playback_status: Mapping[PlaybackStatus, str] = {
    PlaybackStatus.PLAYING: "Playing",
    PlaybackStatus.PAUSED: "Paused",
    PlaybackStatus.STOPPED: "Stopped",
    PlaybackStatus.CLOSED: "Closed",
    PlaybackStatus.CHANGING: "Changing",
    PlaybackStatus.OPENED: "Opened",
}


def release_audio_resources() -> None:
    """Releases resources of audio devices."""
    global mic_stream, microphone, audio_task

    if audio_task is not None:
        audio_task.cancel()
        audio_task = None

    if mic_stream is not None:
        mic_stream = None
    if microphone is not None:
        microphone = None


async def stream_audio() -> None:
    """Handles streaming audio from the user's microphone to the Discord voice channel."""
    global microphone, mic_stream, audio_task
    voice_client = bot.voice_clients[0]

    try:
        mic = sc.get_microphone(id=MICROPHONE_ID, include_loopback=True)

        if mic is None:
            raise ValueError(
                f"Microphone with ID '{MICROPHONE_ID}' not found or invalid."
            )

        with mic.recorder(samplerate=RATE, channels=CHANNELS) as microphone:
            mic_stream = MicrophoneStream(microphone, RATE)

            while voice_client.is_connected():
                if not voice_client.is_playing():
                    try:
                        audio_source = discord.FFmpegPCMAudio(
                            mic_stream,
                            pipe=True,
                            before_options="-f s16le -ar 48000 -ac 2",
                        )
                        voice_client.play(audio_source)
                    except Exception as e:
                        print(f"Error playing audio: {e}")
                        break
                await asyncio.sleep(0.1)

    except IndexError as e:
        print(f"Error: {e}")

    except ValueError as e:
        print(f"Error: {e}")

    except KeyboardInterrupt:
        print("KeyboardInterrupt detected, cleaning up resources...")


class MicrophoneStream(io.RawIOBase):
    def __init__(self, microphone: Any, samplerate: int) -> None:
        self.microphone = microphone
        self.samplerate = samplerate
        self.buffer = b""

    def read(self, size: int = -1) -> bytes:
        if size == -1:
            return self._read_chunk()

        while len(self.buffer) < size:
            self.buffer += self._read_chunk()

        data = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return data

    def _read_chunk(self) -> bytes:
        if self.microphone is None:
            raise RuntimeError("Microphone has been closed or is unavailable.")

        try:
            data = self.microphone.record(numframes=CHUNK)
            int_data = (data * 32767).astype(np.int16)
            self.microphone.flush()
            return int_data.tobytes()
        except Exception as e:
            release_audio_resources()
            return b""

    def readable(self) -> bool:
        return True


async def read_stream_into_buffer(stream_ref: Any, buffer: Buffer) -> None:
    """Reads data from a media stream into a buffer."""
    readable_stream = await stream_ref.open_read_async()
    await readable_stream.read_async(
        buffer, buffer.capacity, InputStreamOptions.READ_AHEAD
    )


async def read_stream_into_buffer(stream_ref: Any, buffer: Buffer) -> None:
    """Reads data from a media stream into a buffer."""
    readable_stream = await stream_ref.open_read_async()
    await readable_stream.read_async(
        buffer, buffer.capacity, InputStreamOptions.READ_AHEAD
    )


async def extract_media_info(session) -> Optional[Dict[str, Any]]:
    """Extracts media information and thumbnail for the current session."""
    info = await session.try_get_media_properties_async()
    info_dict = {
        song_attr: info.__getattribute__(song_attr)
        for song_attr in dir(info)
        if song_attr[0] != "_"
    }
    info_dict["genres"] = list(info_dict["genres"])
    return info_dict


async def get_current_media_info():
    manager = await MediaManager.request_async()
    sessions = manager.get_sessions()

    for session in sessions:
        source_app = session.source_app_user_model_id
        if source_app and any(client in source_app for client in DESKTOP_CLIENTS):
            media_info = await extract_media_info(session)
            playback_info = session.get_playback_info()
            status = playback_status.get(playback_info.playback_status, "Unknown")
            return media_info, status
    return None, None


def get_track_crc(title: str, artist: str) -> int:
    """Generate CRC for track information."""
    return zlib.crc32(f"{title} - {artist}".encode("utf-8"))


def is_valid_string(s: Any) -> bool:
    """Check if the input is a non-empty string."""
    return isinstance(s, str) and len(s.strip()) > 0


async def send_embed_message(channel: discord.TextChannel, **kwargs: Any) -> None:
    """Send a rich embedded message to the Discord text channel."""
    title = kwargs.get("title", "Unknown Title")
    artist = kwargs.get("artist", "Unknown Artist")
    album = kwargs.get("album")
    thumbnail_bytes = kwargs.get("thumbnail_bytes", None)
    current_track_crc = kwargs.get("current_track_crc", 0)

    now_playing = f"**Now Playing: {title} - {artist}"
    if album:
        now_playing += f" ({album})"
    now_playing += "**"

    copyable = f"```\n{title} - {artist}\n```"

    embed = discord.Embed(description=now_playing, color=discord.Color.blue())
    embed.add_field(name="", value=copyable, inline=False)

    file = None
    if thumbnail_bytes:
        file = discord.File(
            io.BytesIO(thumbnail_bytes),
            filename=f"thumbnail_{current_track_crc}.png",
        )
        embed.set_thumbnail(url=f"attachment://thumbnail_{current_track_crc}.png")

    try:
        await channel.send(embed=embed, file=file)
    except discord.errors.HTTPException as e:
        print(f"Error sending message: {e}")


async def update_presence(
    title: str, artist: str, album: Optional[str], status: str
) -> None:
    """Update bot's presence with current track information."""
    name = f"{title} - {artist}"
    if album:
        name += f" ({album})"
    name += f". Status: {status}"

    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name=name,
    )
    await bot.change_presence(activity=activity)


async def process_media_info(
    media_info: Dict[str, Any], status: str, session=None
) -> None:
    """Process media information and update bot's presence and Discord channel."""
    global last_media_info, track_crc

    title = media_info.get("title", "")
    artist = media_info.get("artist", "")
    album = media_info.get("album_title", "")

    if not (is_valid_string(title) and is_valid_string(artist)):
        print("Invalid or empty media information received. Skipping update.")
        return

    current_track_crc = get_track_crc(title, artist)

    if current_track_crc not in track_crc or not track_crc[current_track_crc]:
        track_crc = {crc: False for crc in track_crc}
        track_crc[current_track_crc] = True

        thumbnail_bytes = None
        if "thumbnail" in media_info:
            thumb_stream_ref = media_info["thumbnail"]
            if thumb_stream_ref:
                thumb_read_buffer = Buffer(5000000)
                await read_stream_into_buffer(thumb_stream_ref, thumb_read_buffer)
                thumbnail_bytes = bytearray(thumb_read_buffer.length)
                reader = DataReader.from_buffer(thumb_read_buffer)
                reader.read_bytes(thumbnail_bytes)

        channel = bot.get_channel(TEXT_CHANNEL_ID)
        if channel:
            await send_embed_message(
                channel=channel,
                title=title,
                artist=artist,
                album=album if is_valid_string(album) else None,
                thumbnail_bytes=thumbnail_bytes,
                current_track_crc=current_track_crc,
            )
        else:
            print(f"Error: Could not find text channel with ID {TEXT_CHANNEL_ID}")

        await update_presence(
            title, artist, album if is_valid_string(album) else None, status
        )

        last_media_info = media_info


async def handle_media_change(session, args) -> None:
    """Handler for changing media properties (e.g., changing a track)."""
    await asyncio.sleep(1)

    source_app = session.source_app_user_model_id
    if (
        source_app is not None
        and isinstance(source_app, str)
        and any(client in source_app for client in DESKTOP_CLIENTS)
    ):
        media_info = await extract_media_info(session)
        playback_info = session.get_playback_info()
        status = playback_status.get(playback_info.playback_status, "Unknown")
        await process_media_info(media_info, status, session)
    else:
        print(f"Source app '{source_app}' is not supported.")


async def handle_playback_change(session, args) -> None:
    """Handler for changing the playback state (pause/play)."""
    global last_media_info
    source_app = session.source_app_user_model_id

    if (
        source_app is not None
        and isinstance(source_app, str)
        and any(client in source_app for client in DESKTOP_CLIENTS)
    ):
        playback_info = session.get_playback_info()
        status = playback_status.get(playback_info.playback_status, "Unknown")
        await update_presence(
            last_media_info.get("title", "Unknown Title"),
            last_media_info.get("artist", "Unknown Artist"),
            last_media_info.get("album_title", "Unknown Album"),
            status,
        )


async def setup_media_events() -> None:
    """Setting up event handlers for Windows Media."""
    manager = await MediaManager.request_async()
    loop = asyncio.get_running_loop()

    for session in manager.get_sessions():
        session.add_media_properties_changed(
            lambda s, args: asyncio.run_coroutine_threadsafe(
                handle_media_change(s, args), loop
            )
        )
        session.add_playback_info_changed(
            lambda s, args: asyncio.run_coroutine_threadsafe(
                handle_playback_change(s, args), loop
            )
        )

    print("Media event handlers registered.")


@bot.event
async def on_ready() -> None:
    global audio_task, last_media_info
    print(f"Logged in as {bot.user.name}")

    media_info, status = await get_current_media_info()

    if media_info:
        await process_media_info(media_info, status)
    else:
        activity = discord.Activity(
            type=discord.ActivityType.playing,
            name="Audio Streaming",
        )
        await bot.change_presence(activity=activity)

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print(f"Error: Could not find guild with ID {GUILD_ID}")
        return
    voice_channel = guild.get_channel(VOICE_CHANNEL_ID)
    if voice_channel is None:
        print(f"Error: Could not find voice channel with ID {VOICE_CHANNEL_ID}")
        return
    await voice_channel.connect()
    if audio_task is None or audio_task.done():
        audio_task = asyncio.create_task(stream_audio())

    await setup_media_events()


@bot.command()
async def join(ctx: commands.Context) -> None:
    global audio_task
    if ctx.voice_client is None:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await channel.connect()
            if audio_task is None or audio_task.done():
                audio_task = asyncio.create_task(stream_audio())
        else:
            await ctx.send("You are not connected to a voice channel.")
    else:
        await ctx.send("The bot is already connected to a voice channel.")


@bot.command()
async def leave(ctx: commands.Context) -> None:
    if ctx.voice_client:
        release_audio_resources()

        if ctx.voice_client.is_connected():
            await ctx.voice_client.disconnect()
    else:
        await ctx.send("The bot is not connected to a voice channel.")


def main() -> None:
    try:
        bot.run(TOKEN)
    except discord.LoginFailure as e:
        print(f"Error: Failed to log in. The token may be invalid. Details: {e}")
    except discord.HTTPException as e:
        print(
            f"Error: An HTTP error occurred while connecting to Discord. Details: {e}"
        )
    except KeyboardInterrupt:
        print("Keyboard interrupt detected. Shutting down...")
    except RuntimeError as e:
        print(f"Runtime error occurred: {e}")
    except ConnectionResetError as e:
        print(f"Connection reset error occurred: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        release_audio_resources()
        if not bot.is_closed():
            asyncio.run(bot.close())


if __name__ == "__main__":
    main()
