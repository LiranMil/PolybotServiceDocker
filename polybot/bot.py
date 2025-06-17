import telebot
from loguru import logger
import os
import time
from telebot.types import InputFile
from img_proc import Img
from pymongo import MongoClient
import uuid


class Bot:
    def __init__(self, token, bot_app_url):
        self.telegram_bot_client = telebot.TeleBot(token)
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)
        self.telegram_bot_client.set_webhook(url=f'{bot_app_url}/{token}/', timeout=60)
        logger.info(f'Telegram Bot initialized: {self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
        local_path = file_info.file_path
        with open(local_path, 'wb') as photo:
            photo.write(data)
        return local_path

    def send_photo(self, chat_id, img_path):
        self.telegram_bot_client.send_photo(chat_id, InputFile(img_path))


class ImageProcessingBot(Bot):
    def __init__(self, token, bot_app_url, bucket_name, s3_client, mongo_uri, mongo_db, mongo_collection):
        super().__init__(token, bot_app_url)

        # בדיקת אם בסיס נתונים או אוסף לא הוזנו
        if not mongo_db or not mongo_collection:
            logger.error("MongoDB database or collection name is missing.")
            raise ValueError("MongoDB database and collection names are required.")

        self.bucket_name = bucket_name
        self.s3_client = s3_client
        self.mongo_client = MongoClient(mongo_uri)
        self.mongo_collection = self.mongo_client[mongo_db][mongo_collection]
        self.greeted_users = set()

    def greet_user(self, chat_id):
        if chat_id not in self.greeted_users:
            self.send_text(chat_id,
                           "Hello! I’m your image processing bot 🤖. Send me an image with a caption like 'Rotate', 'Blur', or 'Concat'.")
            self.greeted_users.add(chat_id)

    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')
        chat_id = msg['chat']['id']
        self.greet_user(chat_id)

        if 'photo' not in msg:
            self.send_text(chat_id, "Please send a photo with a caption.")
            return

        caption = msg.get("caption", "").strip()
        if not caption:
            self.send_text(chat_id, "Please include a caption like 'Rotate', 'Blur', or 'Concat'.")
            return

        try:
            command_parts = caption.split()
            command = command_parts[0].lower()
            parameter = int(command_parts[1]) if len(command_parts) > 1 and command_parts[1].isdigit() else 1

            photo_path = self.download_user_photo(msg)
            img_instance = Img(photo_path)

            if command == 'blur':
                img_instance.blur()
            elif command == 'rotate':
                img_instance.rotate()
            elif command == 'concat':
                # add logic if needed
                pass

            processed_path = img_instance.save_img()
            self.send_photo(chat_id, processed_path)

            # Upload to S3
            s3_key = f"{uuid.uuid4()}.jpg"
            self.s3_client.upload_file(processed_path, self.bucket_name, s3_key)

            # Save to MongoDB
            self.mongo_collection.insert_one({
                "chat_id": chat_id,
                "command": command,
                "image_s3_key": s3_key,
                "timestamp": time.time()
            })

        except Exception as e:
            logger.error(f"Error processing image: {e}")
            self.send_text(chat_id, "There was an error processing your image.")
