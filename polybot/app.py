import flask
from flask import request
import os
import boto3
from dotenv import load_dotenv
from bot import ImageProcessingBot

load_dotenv()

app = flask.Flask(__name__)

# --- Environment Variables ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
BOT_APP_URL = os.environ.get('BOT_APP_URL')
BUCKET_NAME = os.environ.get('BUCKET_NAME')
MONGO_URI = os.environ.get('MONGO_URI')
MONGO_DB = os.environ.get('MONGO_DB')
MONGO_COLLECTION = os.environ.get('MONGO_COLLECTION')

# --- Validations ---
if not TELEGRAM_BOT_TOKEN or not BOT_APP_URL or not BUCKET_NAME or not MONGO_URI:
    raise RuntimeError("Missing one or more required environment variables.")

# --- Initialize S3 Client ---
s3_client = boto3.client('s3')

# --- Initialize Bot ---
bot = ImageProcessingBot(
    token=TELEGRAM_BOT_TOKEN,
    bot_app_url=BOT_APP_URL,
    bucket_name=BUCKET_NAME,
    s3_client=s3_client,
    mongo_uri=MONGO_URI,
    mongo_db=MONGO_DB,
    mongo_collection=MONGO_COLLECTION
)

# --- Routes ---
@app.route('/', methods=['GET'])
def index():
    return 'Ok'

@app.route(f'/{TELEGRAM_BOT_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    try:
        bot.handle_message(req['message'])
    except Exception as e:
        print(f"Error handling message: {e}")
    return 'Ok'

# --- Run App ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8443)