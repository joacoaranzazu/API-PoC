"""
EAGOWL POC - Fleet Optimizer Service
Route optimization and fleet management algorithms
"""

from flask import Flask, request, jsonify
import datetime
import json
import logging
import math
import uuid
import random
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DeliveryStop:
    id: str
    name: str
    latitude: float
    longitude: float
    priority: int  # 1-5, 1 is highest
    time_window_start: str
    time_window_end: str
    estimated_duration: int  # minutes

@dataclass
class Vehicle:
    id: str
    driver_name: str
    capacity: float
    current_lat: float
    current_lon: float
    fuel_level: float
    max_fuel: float

class FleetOptimizerService:
    def __init__(self):
        self.vehicles = []
        self.routes = []
        self.deliveries = []
        self.optimization_history = []
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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
        
        return R * c
    
    def optimize_route(self, stops: List[DeliveryStop], vehicle: Vehicle) -> Dict:
        """Optimize route for a single vehicle using nearest neighbor algorithm"""
        try:
            if not stops:
                return {'route': [], 'total_distance': 0, 'estimated_time': 0}
            
            # Start from vehicle's current location
            current_lat = vehicle.current_lat
            current_lon = vehicle.current_lon
            
            unvisited = stops.copy()
            route = []
            total_distance = 0
            
            while unvisited:
                # Find nearest unvisited stop
                nearest_stop = None
                nearest_distance = float('inf')
                
                for stop in unvisited:
                    distance = self.calculate_distance(
                        current_lat, current_lon,
                        stop.latitude, stop.longitude
                    )
                    
                    # Consider priority in distance calculation
                    priority_factor = 1.0 - (stop.priority - 1) * 0.1
                    adjusted_distance = distance * priority_factor
                    
                    if adjusted_distance < nearest_distance:
                        nearest_distance = distance
                        nearest_stop = stop
                
                if nearest_stop:
                    route.append(nearest_stop)
                    unvisited.remove(nearest_stop)
                    total_distance += nearest_distance
                    current_lat = nearest_stop.latitude
                    current_lon = nearest_stop.longitude
            
            # Estimate time (assuming average speed of 40 km/h in urban areas)
            estimated_time = (total_distance / 40) * 60  # minutes
            
            # Add service time for each stop
            total_service_time = sum(stop.estimated_duration for stop in route)
            estimated_time += total_service_time
            
            return {
                'vehicle_id': vehicle.id,
                'route': route,
                'total_distance': total_distance,
                'estimated_time': estimated_time,
                'stops_count': len(route),
                'optimization_method': 'nearest_neighbor_with_priority'
            }
            
        except Exception as e:
            logger.error(f"Error optimizing route: {str(e)}")
            return {'error': str(e)}
    
    def assign_routes(self, deliveries: List[DeliveryStop], vehicles: List[Vehicle]) -> Dict:
        """Assign deliveries to vehicles and optimize routes"""
        try:
            assignments = {}
            unassigned = deliveries.copy()
            
            # Sort vehicles by availability and capacity
            available_vehicles = sorted(vehicles, key=lambda v: v.fuel_level / v.max_fuel, reverse=True)
            
            for vehicle in available_vehicles:
                if not unassigned:
                    break
                
                # Find best delivery stops for this vehicle
                suitable_stops = []
                for delivery in unassigned:
                    distance_to_start = self.calculate_distance(
                        vehicle.current_lat, vehicle.current_lon,
                        delivery.latitude, delivery.longitude
                    )
                    
                    # Check if vehicle can handle this delivery
                    if len(suitable_stops) < 5 and distance_to_start < 50:  # Max 50km per vehicle
                        suitable_stops.append(delivery)
                
                if suitable_stops:
                    # Optimize route for this vehicle
                    route_result = self.optimize_route(suitable_stops, vehicle)
                    
                    if 'error' not in route_result:
                        assignments[vehicle.id] = route_result
                        
                        # Mark assigned deliveries
                        for stop in suitable_stops:
                            unassigned.remove(stop)
            
            return {
                'assignments': assignments,
                'unassigned_deliveries': unassigned,
                'total_vehicles_used': len(assignments),
                'total_deliveries_assigned': len(deliveries) - len(unassigned),
                'optimization_timestamp': datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error assigning routes: {str(e)}")
            return {'error': str(e)}
    
    def calculate_fuel_efficiency(self, vehicle: Vehicle, route_distance: float) -> Dict:
        """Calculate fuel efficiency and fuel consumption for a route"""
        try:
            # Average fuel consumption: 8L/100km for delivery vehicles
            fuel_per_km = 0.08
            estimated_fuel_needed = route_distance * fuel_per_km
            
            # Check if vehicle has enough fuel
            fuel_deficit = max(0, estimated_fuel_needed - vehicle.fuel_level)
            
            return {
                'vehicle_id': vehicle.id,
                'route_distance': route_distance,
                'estimated_fuel_consumption': estimated_fuel_needed,
                'current_fuel_level': vehicle.fuel_level,
                'max_fuel': vehicle.max_fuel,
                'fuel_deficit': fuel_deficit,
                'fuel_percentage': (vehicle.fuel_level / vehicle.max_fuel) * 100,
                'needs_refuel': fuel_deficit > 5  # Needs refuel if deficit > 5L
            }
            
        except Exception as e:
            logger.error(f"Error calculating fuel efficiency: {str(e)}")
            return {'error': str(e)}
    
    def get_optimization_recommendations(self) -> List[Dict]:
        """Get optimization recommendations for the fleet"""
        recommendations = []
        
        try:
            # Check for low fuel vehicles
            for vehicle in self.vehicles:
                fuel_percentage = (vehicle.fuel_level / vehicle.max_fuel) * 100
                if fuel_percentage < 20:
                    recommendations.append({
                        'type': 'fuel_alert',
                        'vehicle_id': vehicle.id,
                        'driver_name': vehicle.driver_name,
                        'fuel_percentage': fuel_percentage,
                        'priority': 'high',
                        'message': f'Vehicle {vehicle.id} needs refueling urgently',
                        'recommendation': 'Route vehicle to nearest fuel station'
                    })
                elif fuel_percentage < 40:
                    recommendations.append({
                        'type': 'fuel_warning',
                        'vehicle_id': vehicle.id,
                        'driver_name': vehicle.driver_name,
                        'fuel_percentage': fuel_percentage,
                        'priority': 'medium',
                        'message': f'Vehicle {vehicle.id} fuel level is low',
                        'recommendation': 'Plan refuel within next 4 hours'
                    })
            
            # Check for delivery efficiency
            if len(self.optimization_history) > 5:
                recent_optimizations = self.optimization_history[-5:]
                avg_efficiency = sum(opt.get('efficiency_score', 0) for opt in recent_optimizations) / len(recent_optimizations)
                
                if avg_efficiency < 0.7:
                    recommendations.append({
                        'type': 'efficiency_improvement',
                        'priority': 'medium',
                        'message': f'Fleet efficiency is below optimal ({avg_efficiency:.1%})',
                        'recommendation': 'Consider reassigning delivery zones or adjusting time windows'
                    })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting recommendations: {str(e)}")
            return []

# Initialize fleet optimizer service
optimizer_service = FleetOptimizerService()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.datetime.now().isoformat(),
        'service': 'fleet-optimizer',
        'version': '1.0.0',
        'vehicles_registered': len(optimizer_service.vehicles),
        'active_routes': len(optimizer_service.routes)
    })

@app.route('/optimize', methods=['POST'])
def optimize_routes():
    """Optimize routes for fleet"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Parse deliveries
        deliveries = []
        for item in data.get('deliveries', []):
            delivery = DeliveryStop(
                id=item.get('id', str(uuid.uuid4())),
                name=item.get('name', 'Delivery Point'),
                latitude=float(item.get('latitude', 0)),
                longitude=float(item.get('longitude', 0)),
                priority=int(item.get('priority', 3)),
                time_window_start=item.get('time_window_start', '09:00'),
                time_window_end=item.get('time_window_end', '17:00'),
                estimated_duration=int(item.get('estimated_duration', 15))
            )
            deliveries.append(delivery)
        
        # Parse vehicles
        vehicles = []
        for item in data.get('vehicles', []):
            vehicle = Vehicle(
                id=item.get('id', str(uuid.uuid4())),
                driver_name=item.get('driver_name', 'Unknown'),
                capacity=float(item.get('capacity', 1000)),
                current_lat=float(item.get('current_lat', 0)),
                current_lon=float(item.get('current_lon', 0)),
                fuel_level=float(item.get('fuel_level', 50)),
                max_fuel=float(item.get('max_fuel', 60))
            )
            vehicles.append(vehicle)
        
        # Optimize routes
        result = optimizer_service.assign_routes(deliveries, vehicles)
        
        # Store optimization history
        optimization_record = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.datetime.now().isoformat(),
            'total_deliveries': len(deliveries),
            'total_vehicles': len(vehicles),
            'assignments_made': result.get('total_deliveries_assigned', 0),
            'efficiency_score': result.get('total_deliveries_assigned', 0) / max(1, len(deliveries))
        }
        optimizer_service.optimization_history.append(optimization_record)
        
        return jsonify({
            'optimization_id': optimization_record['id'],
            'result': result,
            'recommendations': optimizer_service.get_optimization_recommendations()
        })
        
    except Exception as e:
        logger.error(f"Error optimizing routes: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/fuel-efficiency', methods=['POST'])
def calculate_fuel_efficiency():
    """Calculate fuel efficiency for a route"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        vehicle = Vehicle(
            id=data.get('vehicle_id', 'unknown'),
            driver_name=data.get('driver_name', 'Unknown'),
            capacity=data.get('capacity', 1000),
            current_lat=float(data.get('current_lat', 0)),
            current_lon=float(data.get('current_lon', 0)),
            fuel_level=float(data.get('fuel_level', 50)),
            max_fuel=float(data.get('max_fuel', 60))
        )
        
        route_distance = float(data.get('route_distance', 0))
        
        result = optimizer_service.calculate_fuel_efficiency(vehicle, route_distance)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error calculating fuel efficiency: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    """Get fleet optimization recommendations"""
    try:
        recommendations = optimizer_service.get_optimization_recommendations()
        
        return jsonify({
            'recommendations': recommendations,
            'total_count': len(recommendations),
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/history', methods=['GET'])
def get_optimization_history():
    """Get optimization history"""
    try:
        limit = request.args.get('limit', 10, type=int)
        
        history = optimizer_service.optimization_history[-limit:] if optimizer_service.optimization_history else []
        
        return jsonify({
            'history': history,
            'total_count': len(optimizer_service.optimization_history),
            'showing': len(history)
        })
        
    except Exception as e:
        logger.error(f"Error getting optimization history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Fleet Optimizer Service starting on port {port}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)