import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- MIDDLEWARE: Verify Token ---
def verify_token(req):
    """Checks for 'Authorization' header and verifies it with Firebase"""
    token = req.headers.get('Authorization')
    if not token:
        print("Auth Error: No Authorization header found")
        return None
    try:
        decoded_token = auth.verify_id_token(token)
        print(f"Auth Success: User {decoded_token['uid']}")
        return decoded_token
    except Exception as e:
        print(f"Auth Error: Token verification failed - {e}")
        return None

@app.route('/', methods=['GET'])
def home():
    return "TogetherNow Backend Running"

# --- PUBLIC ROUTES ---
@app.route('/events', methods=['GET'])
def get_events():
    events_ref = db.collection('events').order_by('created_at', direction=firestore.Query.DESCENDING)
    docs = events_ref.stream()
    events = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        events.append(data)
    return jsonify(events), 200

# --- PROTECTED ROUTES ---
@app.route('/events', methods=['POST'])
def create_event():
    user = verify_token(request) # 1. Verify User
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    new_event = {
        'title': data.get('title'),
        'category': data.get('category'),
        'location': data.get('location'),
        'max_people': int(data.get('max_people')),
        'current_people': 1,
        'created_at': datetime.now(),
        'creator_name': user.get('name', 'Unknown'), # Use name from token
        'creator_uid': user['uid'],
        'members': [user['uid']]
    }
    db.collection('events').add(new_event)
    return jsonify({"message": "Created"}), 201

@app.route('/join', methods=['POST'])
def join_event():
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    event_ref = db.collection('events').document(data.get('event_id'))
    event = event_ref.get()

    if event.exists:
        members = event.to_dict().get('members', [])
        if user['uid'] in members:
            # Unjoin
            event_ref.update({
                'members': firestore.ArrayRemove([user['uid']]),
                'current_people': firestore.Increment(-1)
            })
            return jsonify({"status": "unjoined"}), 200
        else:
            # Join
            event_ref.update({
                'members': firestore.ArrayUnion([user['uid']]),
                'current_people': firestore.Increment(1)
            })
            return jsonify({"status": "joined"}), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    user = verify_token(request)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
        
    event_ref = db.collection('events').document(event_id)
    doc = event_ref.get()
    
    # Check if the requester is the creator
    if doc.exists and doc.to_dict().get('creator_uid') == user['uid']:
        event_ref.delete()
        return jsonify({"message": "Deleted"}), 200
    
    return jsonify({"error": "Permission denied"}), 403

if __name__ == '__main__':
    app.run(debug=True, port=5000)