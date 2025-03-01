#__________________________________________IMPORTS
from flask import Flask, request, render_template, url_for, redirect
import requests
import urllib.parse
import datetime
from flask_cors import CORS
import os
from flask import send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin

#______________________________________Flask Application Initialization
app = Flask(__name__, static_folder="frontend/build/static")
#______________________________________CORS Configuration: Allowing React app to make requests
CORS(app, origins="http://localhost:3000", methods=["GET", "POST", "OPTIONS"])
#______________________________________Server Configuration
HUB_AUTHKEY = '1234567890'# Authentication key for Hub
HUB_URL = 'http://localhost:5555'# Hub endpoint URL
CHANNELS = None# Cached list of channels
LAST_CHANNEL_UPDATE = None# Timestamp of last channel update
db = SQLAlchemy() 
headers = {"Authorization": "authkey 1234567890"}

#__________________________________________USER MODEL required by Flask-User for authentication and account management
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100, collation='NOCASE'), nullable=False, unique=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean(), nullable=False, server_default='1')
    email_confirmed_at = db.Column(db.DateTime())


#__________________________________________Class-Based Configuration for the Flask Application
class ConfigClass(object):
    ########################### Secret key for session management (Note: Replace this in production)
    # Flask-User settings
    USER_MANAGER_ENABLE_EMAIL = False  # Disabled email for now
    USER_APP_NAME = "Chat Server"  # Shown in emails and page titles
    USER_ENABLE_USERNAME = True  
    USER_REQUIRE_RETYPE_PASSWORD = False  # Disabled password for now
    USER_EMAIL_SENDER_EMAIL = "noreply@example.com"
user_manager = LoginManager(app) # Setting up Flask-login to handle user authentication and account management
@user_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
#______________________________________Channel Validation Update
def update_channels():
    global CHANNELS, LAST_CHANNEL_UPDATE
    if CHANNELS and LAST_CHANNEL_UPDATE and (datetime.datetime.now() - LAST_CHANNEL_UPDATE).seconds < 60:
        return CHANNELS # fetch list of channels from server
    response = requests.get('http://localhost:5555/channels', headers=headers)
    print("Response from Hub:", response.text) 
    if response.status_code != 200:
        return "Error fetching channels: "+str(response.text), 400
    channels_response = response.json()
    if not 'channels' in channels_response:
        return "No channels in response", 400
    CHANNELS = channels_response['channels']
    LAST_CHANNEL_UPDATE = datetime.datetime.now()
    return CHANNELS
#______________________________________Routing To Home Page to fetch list of channels from server
@app.route('/home')
def home_page():    
    return render_template("home.html", channels=update_channels())

#______________________________________Routing To Show and display list of messages from channel
@app.route('/show')
def show_channel():
    print("Request headers:", request.headers)  # Just for checking
    show_channel = request.args.get('channel', None)
    if not show_channel:
        return "No channel specified", 400
    channel = None
    for c in update_channels():
        if c['endpoint'] == urllib.parse.unquote(show_channel):
            channel = c
            break
    if not channel:
        return "Channel not found", 404
    response = requests.get(channel['endpoint'], headers=headers)
    if response.status_code != 200:
        return "Error fetching messages: "+str(response.text), 400
    messages = response.json()
    return render_template("channel.html", channel=channel, messages=messages)

#______________________________________Routing To Send A Message To The Channel
@app.route('/post', methods=['POST'])
def post_message():
    post_channel = request.form['channel']
    if not post_channel:
        return "No channel specified", 400
    channel = None
    for c in update_channels():
        if c['endpoint'] == urllib.parse.unquote(post_channel):
            channel = c
            break
    if not channel:
        return "Channel not found", 404
    message_content = request.form['content']
    message_sender = request.form['sender']
    message_timestamp = datetime.datetime.now().isoformat()
    response = requests.post(channel['endpoint'],
                             headers=headers,
                             json={'content': message_content, 'sender': message_sender, 'timestamp': message_timestamp})
    if response.status_code != 200:
        return "Error posting message: "+str(response.text), 400
    return redirect(url_for('show_channel')+'?channel='+urllib.parse.quote(post_channel))
#______________________________________React App Routing To Main Page
@app.route('/')
def serve_react_app(): # Send index.html from React build folder
    return send_from_directory(os.path.join(app.root_path, 'frontend/build'), 'index.html')
@app.route('/static/<path:path>') # Serve static files (CSS, JS, images) from the React app
def serve_static(path):
    return send_from_directory(os.path.join(app.root_path, 'frontend/build/static'), path)

#______________________________________Application Entry Point
if __name__ == '__main__':
    app.run(port=5005, debug=True)# Start development server on port 5005