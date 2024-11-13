import asyncio
import json
import ssl
import aiohttp
import websockets
import websockets.exceptions
import zlib
import os
import logging
from datetime import datetime
from logger import logger
from dotenv import load_dotenv
import os

load_dotenv()
# Discord settings
source_token = os.getenv("SOURCE_USER_TOKEN")
dest_token = os.getenv("DEST_TOKEN")
dest_user_id = os.getenv("DEST_USER_ID")

source_channel_id = os.getenv("SOURCE_CHANNEL_ID")
source_channel_list = [
    "1306126223696728104", 
    "1306180867965587496"
]

dest_channel_id = os.getenv("DEST_CHANNEL_ID")

discord_ws_url = "wss://gateway.discord.gg/?v=6&encoding=json"
discord_api_url = "https://discord.com/api/v9"

if not os.path.exists("logs"):
    os.makedirs("logs")

# Generate filename with timestamp
log_filename = f"logs/discord_log.txt"


async def send_payload(ws, payload):
    data = json.dumps(payload)
    if len(data.encode()) > 1048000:
        logging.warning("Payload too large, truncating...")
        payload["d"] = {
            k: v[:1000] if isinstance(v, str) else v for k, v in payload["d"].items()
        }
        data = json.dumps(payload)
    await ws.send(data)


async def send_dm(message):
    headers = {"Authorization": dest_token, "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        channel_data = {"recipient_id": dest_user_id}
        async with session.post(
            f"{discord_api_url}/users/@me/channels", headers=headers, json=channel_data
        ) as response:
            if response.status == 200:
                dm_channel = await response.json()
                # channel_id = dm_channel["id"]
                channel_id = dest_channel_id

                message_data = {"content": message}
                async with session.post(
                    f"{discord_api_url}/channels/{channel_id}/messages",
                    headers=headers,
                    json=message_data,
                ) as msg_response:
                    if msg_response.status == 200:
                        logging.info("DM sent successfully: {message}")
                    else:
                        logging.error("Failed to send DM: {msg_response.status}")


async def send_message_to_channel(message):
    headers = {"Authorization": f"{dest_token}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        message_data = {"content": message}
        async with session.post(
            f"{discord_api_url}/channels/{dest_channel_id}/messages",
            headers=headers,
            json=message_data,
        ) as msg_response:
            if msg_response.status == 200:
                logging.info(
                    f"Message sent successfully to channel {dest_channel_id}: {message}"
                )
            else:
                logging.error(
                    f"Failed to send message to channel {dest_channel_id}: {msg_response.status}"
                )


async def heartbeat(ws, interval, last_sequence):
    while True:
        await asyncio.sleep(interval)
        payload = {"op": 1, "d": last_sequence}
        await send_payload(ws, payload)
        logging.info("Heartbeat packet sent.")


async def identify(ws):
    identify_payload = {
        "op": 2,
        "d": {
            "token": source_token,
            "properties": {"$os": "windows", "$browser": "chrome", "$device": "pc"},
            "compress": True,
            "large_threshold": 50,
            "intents": 513,
        },
    }
    await send_payload(ws, identify_payload)
    logging.info("Identification sent.")


async def on_message(ws):
    last_sequence = None
    while True:
        try:
            message = await ws.recv()
            if isinstance(message, bytes):
                message = zlib.decompress(message).decode("utf-8")
            event = json.loads(message)
            if event["d"].get("channel_id", None) in source_channel_list:
                logger.info(
                    "📢📢📢📢📢 Received Channel ID", event["d"].get("channel_id", None)
                )
                await send_message_to_channel(event["d"].get("content", None))
            op_code = event.get("op", None)

            if op_code == 10:
                interval = event["d"]["heartbeat_interval"] / 1000
                asyncio.create_task(heartbeat(ws, interval, last_sequence))

            elif op_code == 0:
                last_sequence = event.get("s", None)
                event_type = event.get("t")

                if event_type == "MESSAGE_CREATE":
                    # Log all message details
                    author = event["d"]["author"]
                    content = event["d"]["content"]
                    channel_type = event["d"].get("channel_type", None)

                    # Process DM forwarding
                    if channel_type == 1:
                        author_id = author["id"]
                        if author_id != dest_user_id and content:
                            # logging.info(f"✨DM received: {content}")
                            await send_dm(content)

            elif op_code == 9:
                logging.info(f"Invalid session. Starting a new session...")
                await identify(ws)

        except Exception as e:
            logging.error(f"Error processing message: ")
            continue


async def main():
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    while True:
        try:
            async with websockets.connect(discord_ws_url, ssl=ssl_context) as ws:
                await identify(ws)
                await on_message(ws)
        except websockets.exceptions.ConnectionClosed as e:
            logging.error(f"WebSocket connection closed unexpectedly:. Reconnecting...")
            await asyncio.sleep(5)
            continue
        except Exception as e:
            logging.error(f"Unexpected error: . Reconnecting...")
            await asyncio.sleep(5)
            continue


if __name__ == "__main__":
    asyncio.run(main())
