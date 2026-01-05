"""
EAGOWL POC - AI Analytics Service
Real-time anomaly detection for fleet operations using machine learning
"""

from flask import Flask, request, jsonify
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os
import datetime
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
import uuid

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SensorData:
    device_id: str
    timestamp: str
    speed: float
    fuel_consumption: float
    engine_temperature: float
    location_lat: float
    location_lon: float
    battery_voltage: float

class AIAnalyticsService:
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.data_buffer = []
        self.anomalies = []
        self.initialize_models()
    
    def initialize_models(self):
        """Initialize ML models for anomaly detection"""
        try:
            # Initialize Isolation Forest for general anomaly detection
            self.models['general'] = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_estimators=100
            )
            
            # Initialize models for specific metrics
            self.models['speed'] = IsolationForest(contamination=0.05, random_state=42)
            self.models['fuel'] = IsolationForest(contamination=0.05, random_state=42)
            self.models['temperature'] = IsolationForest(contamination=0.05, random_state=42)
            
            # Initialize scalers
            self.scalers['general'] = StandardScaler()
            self.scalers['speed'] = StandardScaler()
            self.scalers['fuel'] = StandardScaler()
            self.scalers['temperature'] = StandardScaler()
            
            logger.info("AI Analytics models initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing models: {str(e)}")
    
    def process_sensor_data(self, sensor_data: SensorData) -> Dict:
        """Process incoming sensor data and detect anomalies"""
        try:
            # Store data
            self.data_buffer.append(sensor_data)
            
            # Keep buffer size manageable
            if len(self.data_buffer) > 1000:
                self.data_buffer = self.data_buffer[-800:]
            
            # Prepare features for analysis
            features = np.array([
                sensor_data.speed,
                sensor_data.fuel_consumption,
                sensor_data.engine_temperature,
                sensor_data.battery_voltage
            ]).reshape(1, -1)
            
            # General anomaly detection
            try:
                if len(self.data_buffer) > 10:  # Need some data for training
                    # Train model with recent data
                    recent_data = np.array([
                        [d.speed, d.fuel_consumption, d.engine_temperature, d.battery_voltage]
                        for d in self.data_buffer[-50:]
                    ])
                    
                    if len(recent_data) > 5:
                        self.scalers['general'].fit(recent_data)
                        scaled_data = self.scalers['general'].transform(features)
                        
                        if not hasattr(self.models['general'], 'estimators_'):
                            self.models['general'].fit(recent_data)
                        
                        anomaly_score = self.models['general'].decision_function(scaled_data)[0]
                        is_anomaly = self.models['general'].predict(scaled_data)[0] == -1
                        
                        if is_anomaly:
                            anomaly_event = {
                                'id': str(uuid.uuid4()),
                                'device_id': sensor_data.device_id,
                                'timestamp': sensor_data.timestamp,
                                'anomaly_type': 'general',
                                'anomaly_score': float(anomaly_score),
                                'severity': 'high' if anomaly_score < -0.5 else 'medium',
                                'features': {
                                    'speed': sensor_data.speed,
                                    'fuel_consumption': sensor_data.fuel_consumption,
                                    'engine_temperature': sensor_data.engine_temperature,
                                    'battery_voltage': sensor_data.battery_voltage
                                },
                                'description': 'General anomaly detected in vehicle metrics'
                            }
                            self.anomalies.append(anomaly_event)
                            logger.warning(f"Anomaly detected for device {sensor_data.device_id}: score {anomaly_score}")
                            
                            return {
                                'status': 'anomaly_detected',
                                'anomaly': anomaly_event
                            }
            except Exception as e:
                logger.error(f"Error in anomaly detection: {str(e)}")
            
            # Metric-specific anomaly checks
            alerts = []
            
            # Speed anomaly
            if sensor_data.speed > 120 or sensor_data.speed < 0:
                alerts.append({
                    'type': 'speed',
                    'value': sensor_data.speed,
                    'threshold': {'min': 0, 'max': 120},
                    'severity': 'high'
                })
            
            # Fuel consumption anomaly
            if sensor_data.fuel_consumption > 20:
                alerts.append({
                    'type': 'fuel_consumption',
                    'value': sensor_data.fuel_consumption,
                    'threshold': {'max': 20},
                    'severity': 'medium'
                })
            
            # Engine temperature anomaly
            if sensor_data.engine_temperature > 100:
                alerts.append({
                    'type': 'engine_temperature',
                    'value': sensor_data.engine_temperature,
                    'threshold': {'max': 100},
                    'severity': 'high'
                })
            
            # Battery voltage anomaly
            if sensor_data.battery_voltage < 11:
                alerts.append({
                    'type': 'battery_voltage',
                    'value': sensor_data.battery_voltage,
                    'threshold': {'min': 11},
                    'severity': 'medium'
                })
            
            return {
                'status': 'normal' if not alerts else 'alerts',
                'alerts': alerts,
                'data_processed': True
            }
            
        except Exception as e:
            logger.error(f"Error processing sensor data: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def get_anomaly_summary(self) -> Dict:
        """Get summary of recent anomalies"""
        recent_anomalies = [a for a in self.anomalies 
                           if datetime.datetime.fromisoformat(a['timestamp'].replace('Z', '+00:00')) 
                           > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)]
        
        anomaly_types = {}
        for anomaly in recent_anomalies:
            anomaly_type = anomaly['anomaly_type']
            if anomaly_type not in anomaly_types:
                anomaly_types[anomaly_type] = 0
            anomaly_types[anomaly_type] += 1
        
        return {
            'total_anomalies': len(recent_anomalies),
            'by_type': anomaly_types,
            'severity_distribution': {
                'high': len([a for a in recent_anomalies if a['severity'] == 'high']),
                'medium': len([a for a in recent_anomalies if a['severity'] == 'medium']),
                'low': len([a for a in recent_anomalies if a['severity'] == 'low'])
            },
            'recent_anomalies': recent_anomalies[-10:]  # Last 10 anomalies
        }
    
    def get_performance_metrics(self) -> Dict:
        """Get performance metrics for the analytics service"""
        if not self.data_buffer:
            return {'status': 'no_data'}
        
        recent_data = self.data_buffer[-100:] if len(self.data_buffer) > 100 else self.data_buffer
        
        metrics = {
            'total_devices_processed': len(set(d.device_id for d in self.data_buffer)),
            'total_data_points': len(self.data_buffer),
            'anomalies_detected': len(self.anomalies),
            'processing_rate': len(self.data_buffer) / max(1, (datetime.datetime.now() - datetime.datetime.fromisoformat(self.data_buffer[0].timestamp.replace('Z', '+00:00'))).total_seconds() / 60) if len(self.data_buffer) > 1 else 0,
            'average_metrics': {
                'speed': np.mean([d.speed for d in recent_data]),
                'fuel_consumption': np.mean([d.fuel_consumption for d in recent_data]),
                'engine_temperature': np.mean([d.engine_temperature for d in recent_data]),
                'battery_voltage': np.mean([d.battery_voltage for d in recent_data])
            }
        }
        
        return metrics

# Initialize analytics service
analytics_service = AIAnalyticsService()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.datetime.now().isoformat(),
        'service': 'ai-analytics',
        'version': '1.0.0',
        'models_loaded': len(analytics_service.models),
        'data_points_processed': len(analytics_service.data_buffer),
        'anomalies_detected': len(analytics_service.anomalies)
    })

@app.route('/analyze', methods=['POST'])
def analyze_data():
    """Analyze incoming sensor data"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Handle batch or single data point
        if isinstance(data, list):
            results = []
            for item in data:
                sensor_data = SensorData(
                    device_id=item.get('device_id', 'unknown'),
                    timestamp=item.get('timestamp', datetime.datetime.now().isoformat()),
                    speed=float(item.get('speed', 0)),
                    fuel_consumption=float(item.get('fuel_consumption', 0)),
                    engine_temperature=float(item.get('engine_temperature', 0)),
                    location_lat=float(item.get('location_lat', 0)),
                    location_lon=float(item.get('location_lon', 0)),
                    battery_voltage=float(item.get('battery_voltage', 12))
                )
                result = analytics_service.process_sensor_data(sensor_data)
                results.append(result)
            
            return jsonify({
                'status': 'batch_processed',
                'results': results,
                'total_processed': len(results)
            })
        else:
            sensor_data = SensorData(
                device_id=data.get('device_id', 'unknown'),
                timestamp=data.get('timestamp', datetime.datetime.now().isoformat()),
                speed=float(data.get('speed', 0)),
                fuel_consumption=float(data.get('fuel_consumption', 0)),
                engine_temperature=float(data.get('engine_temperature', 0)),
                location_lat=float(data.get('location_lat', 0)),
                location_lon=float(data.get('location_lon', 0)),
                battery_voltage=float(data.get('battery_voltage', 12))
            )
            
            result = analytics_service.process_sensor_data(sensor_data)
            return jsonify(result)
            
    except Exception as e:
        logger.error(f"Error in analyze_data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/anomalies', methods=['GET'])
def get_anomalies():
    """Get detected anomalies"""
    try:
        hours = request.args.get('hours', 24, type=int)
        severity = request.args.get('severity', None)
        
        cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        
        anomalies = analytics_service.anomalies.copy()
        anomalies = [a for a in anomalies 
                    if datetime.datetime.fromisoformat(a['timestamp'].replace('Z', '+00:00')) > cutoff_time]
        
        if severity:
            anomalies = [a for a in anomalies if a['severity'] == severity]
        
        return jsonify({
            'anomalies': anomalies,
            'total_count': len(anomalies),
            'time_period_hours': hours,
            'filters_applied': {'severity': severity} if severity else {}
        })
        
    except Exception as e:
        logger.error(f"Error getting anomalies: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/summary', methods=['GET'])
def get_summary():
    """Get analytics summary"""
    try:
        summary = analytics_service.get_anomaly_summary()
        metrics = analytics_service.get_performance_metrics()
        
        return jsonify({
            'anomaly_summary': summary,
            'performance_metrics': metrics,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/metrics', methods=['GET'])
def get_metrics():
    """Get detailed performance metrics"""
    try:
        return jsonify(analytics_service.get_performance_metrics())
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/models/retrain', methods=['POST'])
def retrain_models():
    """Retrain ML models with new data"""
    try:
        analytics_service.initialize_models()
        
        # Retrain with accumulated data
        if len(analytics_service.data_buffer) > 50:
            recent_data = np.array([
                [d.speed, d.fuel_consumption, d.engine_temperature, d.battery_voltage]
                for d in analytics_service.data_buffer[-100:]
            ])
            
            for model_name in ['general', 'speed', 'fuel', 'temperature']:
                if model_name in analytics_service.models:
                    analytics_service.scalers[model_name].fit(recent_data)
                    analytics_service.models[model_name].fit(recent_data)
            
            return jsonify({
                'status': 'models_retrained',
                'data_points_used': len(recent_data),
                'models_updated': list(analytics_service.models.keys())
            })
        
        return jsonify({
            'status': 'insufficient_data',
            'data_points_available': len(analytics_service.data_buffer),
            'data_points_required': 50
        })
        
    except Exception as e:
        logger.error(f"Error retraining models: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"AI Analytics Service starting on port {port}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)