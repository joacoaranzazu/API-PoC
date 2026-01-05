"""
EAGOWL POC - API Gateway
Complete Fleet Intelligence Platform Gateway with JWT Authentication and WalkieFleet Proxy
"""

from flask import Flask, request, jsonify, proxy_fix, Response
from flask_cors import CORS
import jwt
import requests
import os
import datetime
import logging
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
import json
import hashlib
import uuid

# Configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'eagowl-poc-secret-key-2024')
app.config['WALKIEFLEET_URL'] = os.environ.get('WALKIEFLEET_URL', 'http://poc1.eagowl.co:9998')
app.config['WALKIEFLEET_USER'] = os.environ.get('WALKIEFLEET_USER', '10000')
app.config['WALKIEFLEET_PASS'] = os.environ.get('WALKIEFLEET_PASS', '1948')

# Enable CORS
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory user database (in production, use a real database)
users = {
    'admin': {
        'password': generate_password_hash('admin123'),
        'role': 'admin',
        'company_id': 'default'
    },
    'fleet_manager': {
        'password': generate_password_hash('fleet123'),
        'role': 'manager',
        'company_id': 'company_001'
    }
}

# Service endpoints
SERVICES = {
    'ai-analytics': os.environ.get('AI_ANALYTICS_URL', 'http://ai-analytics:5001'),
    'smart-map': os.environ.get('SMART_MAP_URL', 'http://smart-map:5002'),
    'fleet-optimizer': os.environ.get('FLEET_OPTIMIZER_URL', 'http://fleet-optimizer:5003'),
    'predictive-alerts': os.environ.get('PREDICTIVE_ALERTS_URL', 'http://predictive-alerts:5004')
}

def token_required(f):
    """JWT token validation decorator"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            token = token.split(' ')[1]  # Remove 'Bearer ' prefix
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data.get('user')
            
            if current_user not in users:
                return jsonify({'error': 'Invalid token'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
            
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.datetime.now().isoformat(),
        'version': '1.0.0',
        'services': list(SERVICES.keys())
    })

@app.route('/auth/login', methods=['POST'])
def login():
    """User authentication endpoint"""
    try:
        auth = request.get_json()
        
        if not auth or not auth.get('username') or not auth.get('password'):
            return jsonify({'error': 'Could not verify'}), 401, {
                'WWW-Authenticate': 'Basic realm="Login required"'
            }
        
        user = auth.get('username')
        password = auth.get('password')
        
        if user in users and check_password_hash(users[user]['password'], password):
            token = jwt.encode({
                'user': user,
                'role': users[user]['role'],
                'company_id': users[user]['company_id'],
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            return jsonify({
                'token': token,
                'user': user,
                'role': users[user]['role'],
                'company_id': users[user]['company_id'],
                'expires_in': 86400  # 24 hours
            })
        
        return jsonify({'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Authentication failed'}), 500

@app.route('/auth/refresh', methods=['POST'])
@token_required
def refresh_token(current_user):
    """Refresh JWT token"""
    try:
        token = jwt.encode({
            'user': current_user,
            'role': users[current_user]['role'],
            'company_id': users[current_user]['company_id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'expires_in': 86400
        })
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return jsonify({'error': 'Token refresh failed'}), 500

def proxy_to_walkiefleet(path, method, data=None, headers=None):
    """Proxy requests to WalkieFleet API"""
    try:
        url = f"{app.config['WALKIEFLEET_URL']}/{path}"
        auth = (app.config['WALKIEFLEET_USER'], app.config['WALKIEFLEET_PASS'])
        
        # Prepare headers
        proxy_headers = {}
        if headers:
            # Filter out hop-by-hop headers
            hop_by_hop = {'connection', 'keep-alive', 'proxy-authenticate', 
                         'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade'}
            proxy_headers = {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}
        
        # Make request to WalkieFleet
        if method == 'GET':
            response = requests.get(url, auth=auth, headers=proxy_headers, timeout=30)
        elif method == 'POST':
            response = requests.post(url, json=data, auth=auth, headers=proxy_headers, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, json=data, auth=auth, headers=proxy_headers, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(url, auth=auth, headers=proxy_headers, timeout=30)
        else:
            return json.dumps({'error': 'Invalid method'}).encode(), 400, {'Content-Type': 'application/json'}
        
        # Filter response headers
        response_headers = {}
        for key, value in response.headers.items():
            if key.lower() not in {'connection', 'keep-alive', 'proxy-authenticate', 
                                  'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade'}:
                response_headers[key] = value
        
        return response.content, response.status_code, response_headers
        
    except requests.exceptions.RequestException as e:
        logger.error(f"WalkieFleet proxy error: {str(e)}")
        return json.dumps({'error': 'WalkieFleet service unavailable'}).encode(), 503, {'Content-Type': 'application/json'}

def proxy_to_service(service_name, path, method, data=None, headers=None):
    """Proxy requests to internal microservices"""
    try:
        service_url = SERVICES.get(service_name)
        if not service_url:
            return json.dumps({'error': f'Service {service_name} not found'}).encode(), 404, {'Content-Type': 'application/json'}
            
        url = f"{service_url}/{path}"
        
        # Prepare headers
        proxy_headers = {'Content-Type': 'application/json'}
        if headers:
            proxy_headers.update(headers)
        
        # Add authentication to service requests
        proxy_headers['X-Service-Auth'] = 'internal-service-key'
        
        # Make request to service
        if method == 'GET':
            response = requests.get(url, headers=proxy_headers, timeout=30)
        elif method == 'POST':
            response = requests.post(url, json=data, headers=proxy_headers, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, json=data, headers=proxy_headers, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(url, headers=proxy_headers, timeout=30)
        else:
            return json.dumps({'error': 'Invalid method'}).encode(), 400, {'Content-Type': 'application/json'}
        
        return response.content, response.status_code, dict(response.headers)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Service proxy error ({service_name}): {str(e)}")
        return json.dumps({'error': f'Service {service_name} unavailable'}).encode(), 503, {'Content-Type': 'application/json'}

# WalkieFleet proxy routes
@app.route('/walkiefleet/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@token_required
def walkiefleet_proxy(current_user, path):
    """Proxy to WalkieFleet API"""
    data = request.get_json() if request.method in ['POST', 'PUT'] else None
    content, status_code, headers = proxy_to_walkiefleet(path, request.method, data, dict(request.headers))
    
    return Response(content, status=status_code, headers=headers)

# Service proxy routes
@app.route('/api/<service_name>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@token_required
def service_proxy(current_user, service_name, path):
    """Proxy to internal microservices"""
    data = request.get_json() if request.method in ['POST', 'PUT'] else None
    content, status_code, headers = proxy_to_service(service_name, path, request.method, data, dict(request.headers))
    
    return Response(content, status=status_code, headers=headers)

# Dashboard endpoints
@app.route('/api/dashboard', methods=['GET'])
@token_required
def get_dashboard_data(current_user):
    """Aggregate dashboard data from all services"""
    try:
        dashboard_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'user': current_user,
            'services_status': {},
            'fleet_summary': {},
            'alerts_summary': {},
            'analytics_summary': {}
        }
        
        # Check service health
        for service_name, service_url in SERVICES.items():
            try:
                response = requests.get(f"{service_url}/health", timeout=5)
                dashboard_data['services_status'][service_name] = {
                    'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                    'response_time': response.elapsed.total_seconds()
                }
            except:
                dashboard_data['services_status'][service_name] = {
                    'status': 'unavailable',
                    'response_time': None
                }
        
        # Get fleet data from WalkieFleet
        try:
            content, status_code, _ = proxy_to_walkiefleet('api/fleet', 'GET')
            if status_code == 200:
                fleet_data = json.loads(content.decode()) if content else {}
                dashboard_data['fleet_summary'] = fleet_data
        except:
            dashboard_data['fleet_summary'] = {'error': 'Unable to fetch fleet data'}
        
        return jsonify(dashboard_data)
        
    except Exception as e:
        logger.error(f"Dashboard data error: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard data'}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({'error': 'Unauthorized'}), 401

if __name__ == '__main__':
    # Configure proxy for proper header handling
    app.wsgi_app = proxy_fix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"EAGOWL API Gateway starting on port {port}")
    logger.info(f"WalkieFleet URL: {app.config['WALKIEFLEET_URL']}")
    logger.info(f"Services configured: {list(SERVICES.keys())}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)