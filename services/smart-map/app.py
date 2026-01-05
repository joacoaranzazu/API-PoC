"""
EAGOWL POC - Smart Map Service
Geospatial clustering and fleet visualization
"""

from flask import Flask, request, jsonify
import numpy as np
import datetime
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import uuid
import math
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VehicleLocation:
    device_id: str
    timestamp: str
    latitude: float
    longitude: float
    speed: float
    heading: float
    status: str  # active, idle, offline

class SmartMapService:
    def __init__(self):
        self.locations = []
        self.clusters = []
        self.geofences = []
        self.initialize_geofences()
    
    def initialize_geofences(self):
        """Initialize default geofences"""
        self.geofences = [
            {
                'id': 'main_office',
                'name': 'Main Office',
                'type': 'circle',
                'center': {'lat': 40.7128, 'lon': -74.0060},  # NYC coordinates
                'radius': 1000,  # meters
                'color': '#00ff00'
            },
            {
                'id': 'warehouse_a',
                'name': 'Warehouse A',
                'type': 'circle',
                'center': {'lat': 40.7580, 'lon': -73.9855},
                'radius': 500,
                'color': '#0000ff'
            }
        ]
    
    def add_location(self, location: VehicleLocation):
        """Add vehicle location and update clusters"""
        self.locations.append(location)
        
        # Keep buffer size manageable
        if len(self.locations) > 500:
            self.locations = self.locations[-400:]
        
        # Update clusters periodically
        if len(self.locations) % 20 == 0:
            self.update_clusters()
    
    def update_clusters(self):
        """Update vehicle clusters using DBSCAN-like algorithm"""
        try:
            if len(self.locations) < 3:
                return
            
            # Get current locations
            current_locations = [loc for loc in self.locations 
                               if datetime.datetime.fromisoformat(loc.timestamp.replace('Z', '+00:00')) 
                               > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)]
            
            if len(current_locations) < 3:
                return
            
            # Simple clustering based on proximity
            clusters = []
            visited = set()
            
            for i, loc1 in enumerate(current_locations):
                if loc1.device_id in visited:
                    continue
                
                cluster = {
                    'id': str(uuid.uuid4()),
                    'center_lat': loc1.latitude,
                    'center_lon': loc1.longitude,
                    'vehicles': [loc1.device_id],
                    'count': 1,
                    'avg_speed': loc1.speed
                }
                visited.add(loc1.device_id)
                
                # Find nearby vehicles
                for j, loc2 in enumerate(current_locations[i+1:], i+1):
                    if loc2.device_id in visited:
                        continue
                    
                    distance = self.haversine_distance(
                        loc1.latitude, loc1.longitude,
                        loc2.latitude, loc2.longitude
                    )
                    
                    if distance < 1000:  # Within 1km
                        cluster['vehicles'].append(loc2.device_id)
                        cluster['count'] += 1
                        cluster['avg_speed'] = (cluster['avg_speed'] + loc2.speed) / 2
                        visited.add(loc2.device_id)
                        
                        # Update cluster center
                        cluster['center_lat'] = (cluster['center_lat'] + loc2.latitude) / 2
                        cluster['center_lon'] = (cluster['center_lon'] + loc2.longitude) / 2
                
                clusters.append(cluster)
            
            self.clusters = clusters
            logger.info(f"Updated {len(clusters)} clusters")
            
        except Exception as e:
            logger.error(f"Error updating clusters: {str(e)}")
    
    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula"""
        R = 6371  # Earth's radius in kilometers
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c * 1000  # Return distance in meters
    
    def get_vehicles_in_geofence(self, geofence_id: str) -> List[str]:
        """Get vehicles within a specific geofence"""
        geofence = next((g for g in self.geofences if g['id'] == geofence_id), None)
        if not geofence:
            return []
        
        vehicles_in_fence = []
        current_locations = [loc for loc in self.locations 
                           if datetime.datetime.fromisoformat(loc.timestamp.replace('Z', '+00:00')) 
                           > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)]
        
        for location in current_locations:
            if geofence['type'] == 'circle':
                distance = self.haversine_distance(
                    geofence['center']['lat'], geofence['center']['lon'],
                    location.latitude, location.longitude
                )
                
                if distance <= geofence['radius']:
                    vehicles_in_fence.append(location.device_id)
        
        return vehicles_in_fence
    
    def get_density_heatmap(self, bounds: Dict) -> List[List]:
        """Generate density heatmap data"""
        try:
            lat_min = bounds.get('south', 40.7)
            lat_max = bounds.get('north', 40.8)
            lon_min = bounds.get('west', -74.1)
            lon_max = bounds.get('east', -73.9)
            
            # Create grid
            grid_size = 0.01  # Approximately 1km grid
            lat_steps = int((lat_max - lat_min) / grid_size)
            lon_steps = int((lon_max - lon_min) / grid_size)
            
            heatmap = np.zeros((lat_steps, lon_steps))
            
            # Count vehicles in each grid cell
            current_locations = [loc for loc in self.locations 
                               if datetime.datetime.fromisoformat(loc.timestamp.replace('Z', '+00:00')) 
                               > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)]
            
            for location in current_locations:
                if (lat_min <= location.latitude <= lat_max and 
                    lon_min <= location.longitude <= lon_max):
                    
                    lat_idx = int((location.latitude - lat_min) / grid_size)
                    lon_idx = int((location.longitude - lon_min) / grid_size)
                    
                    if 0 <= lat_idx < lat_steps and 0 <= lon_idx < lon_steps:
                        heatmap[lat_idx][lon_idx] += 1
            
            # Convert to list format for frontend
            heatmap_data = []
            for i in range(lat_steps):
                for j in range(lon_steps):
                    if heatmap[i][j] > 0:
                        heatmap_data.append({
                            'lat': lat_min + i * grid_size,
                            'lon': lon_min + j * grid_size,
                            'intensity': int(heatmap[i][j]),
                            'weight': min(heatmap[i][j] / 5, 1.0)  # Normalize to 0-1
                        })
            
            return heatmap_data
            
        except Exception as e:
            logger.error(f"Error generating heatmap: {str(e)}")
            return []
    
    def get_fleet_statistics(self) -> Dict:
        """Get fleet statistics"""
        current_locations = [loc for loc in self.locations 
                           if datetime.datetime.fromisoformat(loc.timestamp.replace('Z', '+00:00')) 
                           > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)]
        
        if not current_locations:
            return {'total_vehicles': 0, 'status_distribution': {}}
        
        status_counts = {}
        total_vehicles = len(current_locations)
        
        for location in current_locations:
            status = location.status
            if status not in status_counts:
                status_counts[status] = 0
            status_counts[status] += 1
        
        return {
            'total_vehicles': total_vehicles,
            'status_distribution': status_counts,
            'active_clusters': len(self.clusters),
            'geofence_count': len(self.geofences)
        }

# Initialize smart map service
smart_map_service = SmartMapService()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.datetime.now().isoformat(),
        'service': 'smart-map',
        'version': '1.0.0',
        'vehicles_tracked': len(smart_map_service.locations),
        'active_clusters': len(smart_map_service.clusters),
        'geofences': len(smart_map_service.geofences)
    })

@app.route('/location', methods=['POST'])
def add_location():
    """Add vehicle location"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        location = VehicleLocation(
            device_id=data.get('device_id', 'unknown'),
            timestamp=data.get('timestamp', datetime.datetime.now().isoformat()),
            latitude=float(data.get('latitude', 0)),
            longitude=float(data.get('longitude', 0)),
            speed=float(data.get('speed', 0)),
            heading=float(data.get('heading', 0)),
            status=data.get('status', 'active')
        )
        
        smart_map_service.add_location(location)
        
        return jsonify({
            'status': 'location_added',
            'device_id': location.device_id,
            'timestamp': location.timestamp
        })
        
    except Exception as e:
        logger.error(f"Error adding location: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/locations', methods=['GET'])
def get_locations():
    """Get current vehicle locations"""
    try:
        hours = request.args.get('hours', 1, type=int)
        
        cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        
        locations = [loc for loc in smart_map_service.locations 
                    if datetime.datetime.fromisoformat(loc.timestamp.replace('Z', '+00:00')) > cutoff_time]
        
        return jsonify({
            'locations': [
                {
                    'device_id': loc.device_id,
                    'timestamp': loc.timestamp,
                    'latitude': loc.latitude,
                    'longitude': loc.longitude,
                    'speed': loc.speed,
                    'heading': loc.heading,
                    'status': loc.status
                }
                for loc in locations
            ],
            'total_count': len(locations),
            'time_period_hours': hours
        })
        
    except Exception as e:
        logger.error(f"Error getting locations: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/clusters', methods=['GET'])
def get_clusters():
    """Get vehicle clusters"""
    try:
        # Update clusters before returning
        smart_map_service.update_clusters()
        
        return jsonify({
            'clusters': smart_map_service.clusters,
            'total_count': len(smart_map_service.clusters),
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting clusters: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/geofences', methods=['GET', 'POST'])
def geofences():
    """Get or create geofences"""
    if request.method == 'GET':
        return jsonify({
            'geofences': smart_map_service.geofences,
            'total_count': len(smart_map_service.geofences)
        })
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            geofence = {
                'id': str(uuid.uuid4()),
                'name': data.get('name', 'New Geofence'),
                'type': data.get('type', 'circle'),
                'center': data.get('center'),
                'radius': data.get('radius', 1000),
                'color': data.get('color', '#ff0000')
            }
            
            smart_map_service.geofences.append(geofence)
            
            return jsonify({
                'status': 'geofence_created',
                'geofence': geofence
            })
            
        except Exception as e:
            logger.error(f"Error creating geofence: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/heatmap', methods=['GET'])
def get_heatmap():
    """Get density heatmap data"""
    try:
        bounds = {
            'south': float(request.args.get('south', 40.7)),
            'north': float(request.args.get('north', 40.8)),
            'west': float(request.args.get('west', -74.1)),
            'east': float(request.args.get('east', -73.9))
        }
        
        heatmap_data = smart_map_service.get_density_heatmap(bounds)
        
        return jsonify({
            'heatmap': heatmap_data,
            'bounds': bounds,
            'total_points': len(heatmap_data)
        })
        
    except Exception as e:
        logger.error(f"Error getting heatmap: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/statistics', methods=['GET'])
def get_statistics():
    """Get fleet statistics"""
    try:
        return jsonify(smart_map_service.get_fleet_statistics())
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/geofence/<geofence_id>/vehicles', methods=['GET'])
def get_vehicles_in_geofence(geofence_id):
    """Get vehicles within a specific geofence"""
    try:
        vehicles = smart_map_service.get_vehicles_in_geofence(geofence_id)
        
        return jsonify({
            'geofence_id': geofence_id,
            'vehicles': vehicles,
            'count': len(vehicles)
        })
        
    except Exception as e:
        logger.error(f"Error getting vehicles in geofence: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Smart Map Service starting on port {port}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)