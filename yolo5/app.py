import time
from pathlib import Path
from flask import Flask, request, jsonify
from detect import run
import uuid
import yaml
from loguru import logger
import os
import boto3
from pymongo import MongoClient

# --- S3 and MongoDB Configuration ---
images_bucket = os.environ['BUCKET_NAME']  # Load the S3 bucket name from the environment variable
mongo_uri = os.environ['MONGO_URI']  # MongoDB URI from environment variable
db_name = os.environ.get('MONGO_DB', 'default_db')  # MongoDB database name
collection_name = os.environ.get('MONGO_COLLECTION', 'predictions')  # MongoDB collection name

# --- Set up S3 client and MongoDB connection ---
s3_client = boto3.client('s3')  # Initialize the S3 client
mongo_client = MongoClient(mongo_uri)  # Initialize the MongoDB client
db = mongo_client[db_name]  # Connect to MongoDB database
collection = db[collection_name]  # Access the predictions collection

# --- Load Class Names ---
with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']  # Load YOLOv5 class names from YAML

app = Flask(__name__)  # Initialize Flask app

# --- Define Prediction Route ---
@app.route('/predict', methods=['POST'])  # Define the /predict endpoint to handle POST requests
def predict():
    prediction_id = str(uuid.uuid4())  # Generate a unique ID for the prediction
    logger.info(f'prediction: {prediction_id}. Start processing.')

    # Get the image name from the JSON request body
    img_name = request.json.get('imgName')  # Extract image name from JSON body
    if not img_name:  # If imgName is not provided, return an error response
        return jsonify({"error": "Missing imgName parameter"}), 400

    logger.info(f'Received imgName: {img_name}')
    
    original_img_path = f'static/data/{prediction_id}/{img_name}'  # Local path for the original image
    os.makedirs(os.path.dirname(original_img_path), exist_ok=True)  # Create directories if they don't exist

    try:
        # Download image from S3 to the local server
        s3_client.download_file(images_bucket, img_name, original_img_path)
        logger.info(f'prediction: {prediction_id}. Image download completed: {original_img_path}')
    except Exception as e:
        logger.error(f"Error downloading file from S3: {e}")
        return jsonify({"error": "Failed to download image from S3"}), 500

    # --- Run YOLOv5 Object Detection ---
    try:
        run(
            weights='yolov5s.pt',  # YOLOv5 model weights
            data='data/coco128.yaml',  # Dataset configuration file
            source=original_img_path,  # Input image location
            project='static/data',  # Directory to save results
            name=prediction_id,  # Use prediction ID as the name for results
            save_txt=True  # Save detection results in text format
        )
        logger.info(f'prediction: {prediction_id}. YOLOv5 processing completed.')
    except Exception as e:
        logger.error(f"Error running YOLOv5: {e}")
        return jsonify({"error": "YOLOv5 processing failed"}), 500

    # --- Post-Processing ---
    pred_dir = f'static/data/{prediction_id}2'  # Directory where YOLOv5 saved the predictions
    pred_summary_path = Path(f'{pred_dir}/labels/{img_name.split(".")[0]}.txt')  # Path to the prediction labels

    if not pred_summary_path.exists():
        logger.error(f'Prediction label file not found at {pred_summary_path}')
        return jsonify({"error": "Prediction result not found"}), 404

    # Parse labels from the text file
    with open(pred_summary_path) as f:
        labels = f.read().splitlines()
        labels = [line.split(' ') for line in labels]  # Split each line into components
        labels = [{
            'class': names[int(l[0])],  # Class name based on label index
            'cx': float(l[1]),  # Center x of bounding box
            'cy': float(l[2]),  # Center y of bounding box
            'width': float(l[3]),  # Width of bounding box
            'height': float(l[4]),  # Height of bounding box
        } for l in labels]  # Create list of dictionaries for each detection

    logger.info(f'prediction: {prediction_id}. Prediction summary:\n{labels}')

    # --- Upload Predicted Image to S3 ---
    predicted_img_path = Path(f'{pred_dir}/{img_name}')  # Path to predicted image
    predicted_s3_key = f'predictions/{prediction_id}/{img_name}'  # S3 path for the predicted image
    try:
        s3_client.upload_file(str(predicted_img_path), images_bucket, predicted_s3_key)
        logger.info(f'prediction: {prediction_id}. Predicted image uploaded to S3: {predicted_s3_key}')
    except Exception as e:
        logger.error(f"Error uploading predicted image to S3: {e}")
        return jsonify({"error": "Failed to upload predicted image to S3"}), 500

    # --- Store Prediction Summary in MongoDB ---
    prediction_summary = {
        'prediction_id': prediction_id,
        'original_img_path': original_img_path,
        'predicted_img_path': predicted_s3_key,
        'labels': labels,
        'time': time.time(),  # Timestamp of the prediction
    }

    try:
        result = collection.insert_one(prediction_summary)  # Insert prediction summary into MongoDB
        prediction_summary['_id'] = str(result.inserted_id)  # Add MongoDB document ID to the summary
    except Exception as e:
        logger.error(f"Error saving prediction summary to MongoDB: {e}")
        return jsonify({"error": "Failed to store prediction summary in MongoDB"}), 500

    # Return response with prediction details
    return jsonify({
        'prediction_id': prediction_id,
        'original_img_path': original_img_path,
        'predicted_img_path': predicted_s3_key,
        'predictions': labels,
    })


# --- Main Execution ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8081)  # Run the Flask app on port 8081
