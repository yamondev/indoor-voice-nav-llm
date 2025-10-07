#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from ament_index_python.packages import get_package_share_directory
import yaml
import json
import math
import os

class NavigationCommandNode(Node):
    def __init__(self):
        super().__init__('navigation_command_node')

        # Souscrire aux intentions
        self.subscriber = self.create_subscription(String, '/llm_feedback_to_user', self.handle_intent, 10)

        # Client d'action vers Nav2
        self.client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # Charger le fichier YAML des destinations
        package_share = get_package_share_directory('nav_command')
        yaml_path = os.path.join(package_share, 'locations.yaml')
        with open(yaml_path, 'r') as f:
            self.locations = yaml.safe_load(f)
            self.locations_keys = {key for key in self.locations}

    def handle_intent(self, msg):
        try:
            data = json.loads(msg.data)
            if data["intent"] != "navigate_to":
                self.get_logger().info("❌ Intention non gérée.")
                return

            dest = data["destination"]
            
            if dest not in self.locations_keys:
                self.get_logger().error(f"❌ Destination inconnue : {dest}")
                return
            
            pose = self.locations[dest]
            self.send_goal(pose)           

        except Exception as e:
            self.get_logger().error(f"Erreur dans le message reçu : {e}")

    def send_goal(self, pose_dict):
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = pose_dict["x"]
        goal.pose.pose.position.y = pose_dict["y"]

        # Convertir theta en quaternion
        theta = pose_dict["theta"]
        goal.pose.pose.orientation.z = math.sin(theta / 2)
        goal.pose.pose.orientation.w = math.cos(theta / 2)

        #self.get_logger().info(f"📍 connecting............")
        self.client.wait_for_server()
        #self.get_logger().info(f"📍 server connected")
        #self.client.send_goal_async(goal)
        future = self.client.send_goal_async(goal)
        future.add_done_callback(self.goal_response_callback)
        self.get_logger().info(f"📍 Navigation vers {pose_dict} envoyée.")
        
    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('🚫 Goal rejeté.')
            return

        self.get_logger().info('✅ Goal accepté. En attente de résultat...')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.navigation_result_callback)

    def navigation_result_callback(self, future):
        result = future.result().result
        if result.error_code == 0:
            message = {
            	"intent": "navigation_status",
            	"respond": "Nous sommes arrivés à destination."
            }
        else:
            message = {
            	"intent": "navigation_status",
            	"respond": "Navigation échouée. Impossible d’atteindre la destination."
            }

        # Publier vers /llm_feedback_to_user
        pub = self.create_publisher(String, '/llm_feedback_to_user', 10)
        pub.publish(String(data=json.dumps(message)))
        self.get_logger().info(f"🗣️ Message publié : {message['respond']}")


def main():
    rclpy.init()
    node = NavigationCommandNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

