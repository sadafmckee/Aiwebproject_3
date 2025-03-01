
#__________________________________________IMPORTS
from flask import Flask, request, render_template, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import json 
import datetime 
import requests   

db = SQLAlchemy() 
#__________________________________________DATA MODEL:Defining the Channel model representing the channels table in the database
################ NB: Make sure to add flask_user UserMixin as this adds additional fields and properties required by Flask-User
class Channel(db.Model):
    __tablename__ = 'channels'
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column('is_active', db.Boolean(), nullable=False, server_default='1')
    name = db.Column(db.String(100, collation='NOCASE'), nullable=False)
    endpoint = db.Column(db.String(100, collation='NOCASE'), nullable=False, unique=True)
    authkey = db.Column(db.String(100, collation='NOCASE'), nullable=False)
    type_of_service = db.Column(db.String(100, collation='NOCASE'), nullable=False)
    last_heartbeat = db.Column(db.DateTime(), nullable=True, server_default=None)


#__________________________________________Class-Based Configuration for the Flask Application
class ConfigClass(object):
    ########################### Secret key for session management (Note: Replace this in production)

    # Flask settings
    SECRET_KEY = 'This is an INSECURE secret!! DO NOT use this in production!!' # change to something random, no matter what
    # Flask-SQLAlchemy settings
    SQLALCHEMY_DATABASE_URI = 'sqlite:///chat_server.sqlite'  
    SQLALCHEMY_TRACK_MODIFICATIONS = False  
    


#__________________________________________APP INITIALIZATION: Creation & Configuration of an instance of the Flask application
app = Flask(__name__, static_folder="frontend/build/static")
app.config.from_object(__name__ + '.ConfigClass')  # 
app.app_context().push() 
db.init_app(app)  
db.create_all()  

SERVER_AUTHKEY = '1234567890'  # Server authorization key used for validating incoming requests
STANDARD_CLIENT_URL = 'http://localhost:5005' # standard configuration in client.py, chang to real URL if necessary


#__________________________________________ HELPER FUNCTIONS to perform health check for a given channel
def health_check(endpoint, authkey):
    # make GET request to URL
    # add authkey to request header
    try:
        response = requests.get(endpoint+'/health',
                                headers={'Authorization': 'authkey '+authkey})
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return False
    if response.status_code != 200:
        return False
    # check if response is JSON with {"name": <channel_name>}
    if 'name' not in response.json():
        return False
    # check if channel name is as expected
    # (channels can't change their name, must be re-registered)
    channel = Channel.query.filter_by(endpoint=endpoint).first()
    channel.active = False
    db.session.commit()
    if not channel:
        print(f"Channel {endpoint} not found in database")
        return False
    expected_name = channel.name
    if response.json()['name'] != expected_name:
        return False

    # everything is OK, set last_heartbeat to now
    channel.active = True
    channel.last_heartbeat = datetime.datetime.now()
    db.session.commit()  # save to database
    return True
#__________________________________________cli command to check health of all channels
@app.cli.command('check_channels')
def check_channels():
    channels = Channel.query.all()
    for channel in channels:
        if not health_check(channel.endpoint, channel.authkey):
            print(f"Channel {channel.endpoint} is not healthy")
        else:
            print(f"Channel {channel.endpoint} is healthy")
#__________________________________________ROUTES: Home page route - Displaying a list of all channels and is accessible to anyone
@app.route('/')
def home_page():
    channels = Channel.query.all()      # Query all channels from the database
    return render_template("hub_home.html", channels=channels, STANDARD_CLIENT_URL=STANDARD_CLIENT_URL)

#__________________________________________REST API ENDPOINTS: Flask REST route endpoints for creating or updating a channel (POST request)
@app.route('/channels', methods=['POST'])
def create_channel():
    global SERVER_AUTHKEY
    record = json.loads(request.data)
    if 'Authorization' not in request.headers:  #Authorization check
        return "No authorization header", 400
    if request.headers['Authorization'] != 'authkey ' + SERVER_AUTHKEY:
        return "Invalid authorization header ({})".format(request.headers['Authorization']), 400
    if 'name' not in record:     
        return "Record has no name", 400
    if 'endpoint' not in record:
        return "Record has no endpoint", 400
    if 'authkey' not in record:
        return "Record has no authkey", 400
    if 'type_of_service' not in record:
        return "Record has no type of service representation", 400
    update_channel = Channel.query.filter_by(endpoint=record['endpoint']).first()
    print("update_channel: ", update_channel)
    if update_channel:  # If channel already exists, update it
        update_channel.name = record['name']
        update_channel.authkey = record['authkey']
        update_channel.type_of_service = record['type_of_service']
        update_channel.active = False
        db.session.commit()         # Save changes to the database
        if not health_check(record['endpoint'], record['authkey']):     # Perform health check to validate channel status
            return "Channel is not healthy", 400
        return jsonify(created=False,          
                       id=update_channel.id), 200
    else:  # If channel does not exist, create a new one
        channel = Channel(name=record['name'],
                          endpoint=record['endpoint'],
                          authkey=record['authkey'],
                          type_of_service=record['type_of_service'],
                          last_heartbeat=datetime.datetime.now(),
                          active=True)
        db.session.add(channel)          # Add and commit the new channel to the database
        db.session.commit() 
        if not health_check(record['endpoint'], record['authkey']):          # Perform health check & if health check fails, delete the newly created channel
            db.session.delete(channel)  # delete channel from database
            db.session.commit()
            return "Channel is not healthy", 400         # Return JSON response indicating creation
        return jsonify(created=True, id=channel.id), 200

# Endpoint for retrieving all channels (GET request)

@app.route('/channels', methods=['GET'])
def get_channels():
    channels = Channel.query.all()     # Query all channels from the database
    return jsonify(channels=[{'name': c.name,         # Return JSON response containing all channels' data
                              'endpoint': c.endpoint,
                              'authkey': c.authkey,
                              'type_of_service': c.type_of_service} for c in channels]), 200
@app.route('/health', methods=['GET'])
def health():
    # check either all channels or a specific channel (if id is provided)
    if 'id' in request.args:
        channel = Channel.query.filter_by(id=request.args['id']).first()
        health_check(channel.endpoint, channel.authkey)
    else:
        channels = Channel.query.all()
        for channel in channels:
            health_check(channel.endpoint, channel.authkey)

    # flask redirect to home page
    return redirect(url_for('home_page'))

#__________________________________________________________________APPLICATION ENTRY POINT: Run the Flask application on port 5555 in debug mode
if __name__ == '__main__':
    app.run(port=5555, debug=True)