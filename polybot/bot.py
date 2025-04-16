import telebot
from loguru import logger
import os
import time
from telebot.types import InputFile
from img_proc import Img

class Bot:
    def __init__(self, token, bot_app_url):
        self.telegram_bot_client = telebot.TeleBot(token)
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)
        self.telegram_bot_client.set_webhook(url=f'{bot_app_url}/{token}/', timeout=60)
        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')
        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)
        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")
        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )

    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


class QuoteBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')
        if msg["text"] != 'Please don\'t quote me':
            self.send_text_with_quote(msg['chat']['id'], msg["text"], quoted_msg_id=msg["message_id"])


class ImageProcessingBot(Bot):
    def __init__(self, token, bot_app_url):
        super().__init__(token, bot_app_url)
        self.concat_waiting_for_image = False
        self.first_image_path = None
        self.greeted_users = set()

    def greet_user(self, chat_id):
        if chat_id not in self.greeted_users:
            self.send_text(chat_id,
                           "Hello! I’m your image processing bot 🤖. Send me an image with a caption like 'Rotate', 'Blur', or 'Concat' to get started.")
            self.greeted_users.add(chat_id)

    # הנה ההתאמה החדשה
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')

        # הדפסת כל המידע שמתקבל בהודעה כדי לבדוק את המבנה שלה
        logger.info(f"Message data: {msg}")

        chat_id = msg['chat']['id']
        self.greet_user(chat_id)

        # אם יש תמונה
        if 'photo' in msg:
            # הדפסת פרטי התמונה
            logger.info(f"Photos in message: {msg['photo']}")

            # ננסה גם להדפיס את ה-caption אם יש
            caption = msg.get("caption", "").strip()
            logger.info(f"Caption: {caption}")

            if not caption:
                self.send_text(chat_id, "Please include a caption to specify the action (e.g., 'Rotate', 'Blur').")
                return

            try:
                # פיצול ה-caption לקבלת הפקודה ופרמטרים
                command_parts = caption.split()
                command = command_parts[0].lower()
                parameter = int(command_parts[1]) if len(command_parts) > 1 and command_parts[1].isdigit() else 1

                # טיפול בפקודות שונות (Blur, Rotate, Concat)
                photo_path = self.download_user_photo(msg)
                img_instance = Img(photo_path)

                if command == 'blur':
                    img_instance.blur()
                elif command == 'rotate':
                    img_instance.rotate()
                elif command == 'concat':
                    # אפשר להוסיף כאן את הלוגיקה של ה-Concat אם דרוש
                    pass

                # שמירת התמונה המעובדת ושליחתה
                processed_image_path = img_instance.save_img()
                self.send_photo(msg['chat']['id'], processed_image_path)

            except Exception as e:
                logger.error(f"Error processing image: {e}")
                self.send_text(msg['chat']['id'], "There was an error processing the image.")
        else:
            self.send_text(msg['chat']['id'], "Please send a photo with a valid caption.")
