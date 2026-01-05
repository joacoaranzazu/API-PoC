"""
EAGOWL POC - Predictive Alerts Service
Configurable alert rules and notification system
"""

from flask import Flask, request, jsonify
import datetime
import json
import logging
import uuid
import threading
import time
import random
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AlertRule:
    id: str
    name: str
    description: str
    condition: str  # Rule condition in simple format
    threshold_value: float
    operator: str  # >, <, >=, <=, ==, !=
    device_id: Optional[str] = None
    severity: str = 'medium'  # low, medium, high, critical
    enabled: bool = True
    created_at: Optional[str] = None
    last_triggered: Optional[str] = None

@dataclass
class Alert:
    id: str
    rule_id: str
    device_id: str
    message: str
    severity: str
    value: float
    threshold: float
    timestamp: str
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[str] = None

class PredictiveAlertsService:
    def __init__(self):
        self.alert_rules = []
        self.active_alerts = []
        self.alert_history = []
        self.notification_handlers = []
        self.initialize_default_rules()
        self.start_monitoring_thread()
    
    def initialize_default_rules(self):
        """Initialize default alert rules"""
        default_rules = [
            AlertRule(
                id=str(uuid.uuid4()),
                name="High Speed Alert",
                description="Alert when vehicle speed exceeds threshold",
                condition="speed > threshold",
                threshold_value=120.0,
                operator=">",
                severity="high",
                created_at=datetime.datetime.now().isoformat()
            ),
            AlertRule(
                id=str(uuid.uuid4()),
                name="Low Fuel Alert",
                description="Alert when fuel level is critically low",
                condition="fuel_level < threshold",
                threshold_value=15.0,
                operator="<",
                severity="medium",
                created_at=datetime.datetime.now().isoformat()
            ),
            AlertRule(
                id=str(uuid.uuid4()),
                name="Engine Overheating",
                description="Alert when engine temperature is too high",
                condition="engine_temperature > threshold",
                threshold_value=95.0,
                operator=">",
                severity="critical",
                created_at=datetime.datetime.now().isoformat()
            ),
            AlertRule(
                id=str(uuid.uuid4()),
                name="Battery Low Alert",
                description="Alert when battery voltage is low",
                condition="battery_voltage < threshold",
                threshold_value=11.5,
                operator="<",
                severity="medium",
                created_at=datetime.datetime.now().isoformat()
            )
        ]
        
        self.alert_rules.extend(default_rules)
        logger.info(f"Initialized {len(default_rules)} default alert rules")
    
    def start_monitoring_thread(self):
        """Start background monitoring thread"""
        def monitor():
            while True:
                try:
                    self.check_alert_conditions()
                    time.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    logger.error(f"Error in monitoring thread: {str(e)}")
                    time.sleep(60)
        
        monitoring_thread = threading.Thread(target=monitor, daemon=True)
        monitoring_thread.start()
        logger.info("Alert monitoring thread started")
    
    def check_alert_conditions(self):
        """Check alert conditions with mock data (in production, would get from actual sensors)"""
        # This is a simulation - in production, would connect to actual data sources
        mock_data = self.generate_mock_sensor_data()
        
        for data_point in mock_data:
            self.evaluate_rules_for_data(data_point)
    
    def generate_mock_sensor_data(self) -> List[Dict]:
        """Generate mock sensor data for testing"""
        mock_data = []
        device_ids = ['veh_001', 'veh_002', 'veh_003', 'veh_004', 'veh_005']
        
        for device_id in device_ids:
            # Generate realistic but varied sensor readings
            data_point = {
                'device_id': device_id,
                'timestamp': datetime.datetime.now().isoformat(),
                'speed': random.uniform(0, 150),
                'fuel_level': random.uniform(5, 80),
                'engine_temperature': random.uniform(70, 105),
                'battery_voltage': random.uniform(10.5, 14.5),
                'latitude': random.uniform(40.7, 40.8),
                'longitude': random.uniform(-74.1, -74.0)
            }
            mock_data.append(data_point)
        
        return mock_data
    
    def evaluate_rules_for_data(self, data_point: Dict):
        """Evaluate all alert rules for a data point"""
        try:
            for rule in self.alert_rules:
                if not rule.enabled:
                    continue
                
                # Skip if rule is device-specific and doesn't match
                if rule.device_id and rule.device_id != data_point['device_id']:
                    continue
                
                # Extract the relevant value based on condition
                field_name = rule.condition.split()[0]
                if field_name not in data_point:
                    continue
                
                current_value = float(data_point[field_name])
                
                # Check if rule condition is met
                alert_triggered = self.evaluate_condition(
                    current_value, rule.operator, rule.threshold_value
                )
                
                if alert_triggered:
                    self.create_alert(rule, data_point, current_value)
                
        except Exception as e:
            logger.error(f"Error evaluating rules for data point: {str(e)}")
    
    def evaluate_condition(self, value: float, operator: str, threshold: float) -> bool:
        """Evaluate a single condition"""
        if operator == '>':
            return value > threshold
        elif operator == '<':
            return value < threshold
        elif operator == '>=':
            return value >= threshold
        elif operator == '<=':
            return value <= threshold
        elif operator == '==':
            return abs(value - threshold) < 0.01
        elif operator == '!=':
            return abs(value - threshold) >= 0.01
        return False
    
    def create_alert(self, rule: AlertRule, data_point: Dict, value: float):
        """Create a new alert"""
        try:
            # Check if there's already an active alert for this rule and device
            existing_alert = next(
                (a for a in self.active_alerts 
                 if a.rule_id == rule.id and a.device_id == data_point['device_id'] and not a.acknowledged),
                None
            )
            
            if existing_alert:
                return  # Alert already exists
            
            alert = Alert(
                id=str(uuid.uuid4()),
                rule_id=rule.id,
                device_id=data_point['device_id'],
                message=f"{rule.name}: {rule.description} (Value: {value:.2f}, Threshold: {rule.threshold_value})",
                severity=rule.severity,
                value=value,
                threshold=rule.threshold_value,
                timestamp=datetime.datetime.now().isoformat()
            )
            
            self.active_alerts.append(alert)
            self.alert_history.append(alert)
            
            # Update rule last triggered time
            rule.last_triggered = alert.timestamp
            
            # Send notification
            self.send_notification(alert)
            
            logger.warning(f"Alert created: {alert.message}")
            
        except Exception as e:
            logger.error(f"Error creating alert: {str(e)}")
    
    def send_notification(self, alert: Alert):
        """Send notification for alert"""
        # In production, would send to email, SMS, webhook, etc.
        notification_data = {
            'alert_id': alert.id,
            'message': alert.message,
            'severity': alert.severity,
            'device_id': alert.device_id,
            'timestamp': alert.timestamp
        }
        
        # Log notification (in production, would send to external service)
        logger.info(f"Notification sent: {notification_data}")
        
        # Store notification handler result
        self.notification_handlers.append({
            'alert_id': alert.id,
            'timestamp': datetime.datetime.now().isoformat(),
            'status': 'sent'
        })
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> Dict:
        """Acknowledge an alert"""
        try:
            alert = next((a for a in self.active_alerts if a.id == alert_id), None)
            if not alert:
                return {'error': 'Alert not found'}
            
            alert.acknowledged = True
            alert.acknowledged_by = acknowledged_by
            alert.acknowledged_at = datetime.datetime.now().isoformat()
            
            # Move from active to history
            self.active_alerts.remove(alert)
            
            return {
                'status': 'acknowledged',
                'alert_id': alert_id,
                'acknowledged_by': acknowledged_by,
                'acknowledged_at': alert.acknowledged_at
            }
            
        except Exception as e:
            logger.error(f"Error acknowledging alert: {str(e)}")
            return {'error': str(e)}
    
    def get_alert_statistics(self) -> Dict:
        """Get alert statistics"""
        total_alerts = len(self.alert_history)
        active_alerts = len(self.active_alerts)
        
        severity_counts = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        for alert in self.active_alerts:
            if alert.severity in severity_counts:
                severity_counts[alert.severity] += 1
        
        recent_alerts = [a for a in self.alert_history 
                        if datetime.datetime.fromisoformat(a.timestamp.replace('Z', '+00:00')) 
                        > datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)]
        
        return {
            'total_alerts': total_alerts,
            'active_alerts': active_alerts,
            'alerts_last_24h': len(recent_alerts),
            'severity_distribution': severity_counts,
            'rules_enabled': len([r for r in self.alert_rules if r.enabled]),
            'total_rules': len(self.alert_rules)
        }

# Initialize predictive alerts service
alerts_service = PredictiveAlertsService()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.datetime.now().isoformat(),
        'service': 'predictive-alerts',
        'version': '1.0.0',
        'active_alerts': len(alerts_service.active_alerts),
        'total_rules': len(alerts_service.alert_rules)
    })

@app.route('/alerts', methods=['GET'])
def get_alerts():
    """Get alerts"""
    try:
        status = request.args.get('status', 'active')  # active, all, acknowledged
        severity = request.args.get('severity', None)
        limit = request.args.get('limit', 50, type=int)
        
        alerts = []
        
        if status == 'active':
            alerts = alerts_service.active_alerts
        elif status == 'all':
            alerts = alerts_service.alert_history
        elif status == 'acknowledged':
            alerts = [a for a in alerts_service.alert_history if a.acknowledged]
        
        # Filter by severity
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        # Limit results
        alerts = alerts[:limit] if limit > 0 else alerts
        
        return jsonify({
            'alerts': alerts,
            'total_count': len(alerts),
            'filters': {
                'status': status,
                'severity': severity,
                'limit': limit
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting alerts: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/alerts/<alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    """Acknowledge an alert"""
    try:
        data = request.get_json() or {}
        acknowledged_by = data.get('acknowledged_by', 'system')
        
        result = alerts_service.acknowledge_alert(alert_id, acknowledged_by)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error acknowledging alert: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/rules', methods=['GET', 'POST'])
def manage_rules():
    """Get or create alert rules"""
    if request.method == 'GET':
        enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
        
        rules = alerts_service.alert_rules
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        
        return jsonify({
            'rules': rules,
            'total_count': len(rules)
        })
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            
            rule = AlertRule(
                id=str(uuid.uuid4()),
                name=data.get('name', 'New Rule'),
                description=data.get('description', ''),
                condition=data.get('condition', 'value > threshold'),
                threshold_value=float(data.get('threshold_value', 0)),
                operator=data.get('operator', '>'),
                device_id=data.get('device_id', None),
                severity=data.get('severity', 'medium'),
                enabled=data.get('enabled', True),
                created_at=datetime.datetime.now().isoformat()
            )
            
            alerts_service.alert_rules.append(rule)
            
            return jsonify({
                'status': 'rule_created',
                'rule': rule
            })
            
        except Exception as e:
            logger.error(f"Error creating rule: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/rules/<rule_id>/toggle', methods=['PUT'])
def toggle_rule(rule_id):
    """Toggle alert rule enabled/disabled"""
    try:
        rule = next((r for r in alerts_service.alert_rules if r.id == rule_id), None)
        if not rule:
            return jsonify({'error': 'Rule not found'}), 404
        
        rule.enabled = not rule.enabled
        
        return jsonify({
            'status': 'toggled',
            'rule_id': rule_id,
            'enabled': rule.enabled
        })
        
    except Exception as e:
        logger.error(f"Error toggling rule: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/statistics', methods=['GET'])
def get_statistics():
    """Get alert statistics"""
    try:
        return jsonify(alerts_service.get_alert_statistics())
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/test-alert', methods=['POST'])
def test_alert():
    """Trigger a test alert"""
    try:
        data = request.get_json()
        device_id = data.get('device_id', 'test_device')
        value = float(data.get('value', 100))
        rule_id = data.get('rule_id')
        
        # Find rule
        rule = None
        if rule_id:
            rule = next((r for r in alerts_service.alert_rules if r.id == rule_id), None)
        
        if not rule:
            # Use first enabled rule
            rule = next((r for r in alerts_service.alert_rules if r.enabled), None)
        
        if not rule:
            return jsonify({'error': 'No rule found'}), 404
        
        # Create test alert
        test_data = {
            'device_id': device_id,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        alerts_service.create_alert(rule, test_data, value)
        
        return jsonify({
            'status': 'test_alert_created',
            'device_id': device_id,
            'value': value,
            'rule_id': rule.id
        })
        
    except Exception as e:
        logger.error(f"Error creating test alert: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5004))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Predictive Alerts Service starting on port {port}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)