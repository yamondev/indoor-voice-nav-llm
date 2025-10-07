#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
import math
import yaml
import os

class WaypointRecorder(Node):
    def __init__(self):
        super().__init__('waypoint_recorder')
        self.subscription = self.create_subscription(
            PoseStamped,
            '/goal_pose',  # ← assure-toi que c’est bien ce topic
            self.pose_callback,
            10
        )
        self.locations = {}
        self.yaml_path = os.path.expanduser('~/locations.yaml')
        self.get_logger().info('Clique avec “2D Nav Goal” puis entre un nom dans le terminal.')

    def pose_callback(self, msg):
        x = msg.pose.position.x
        y = msg.pose.position.y
        z = msg.pose.orientation.z
        w = msg.pose.orientation.w
        theta = 2 * math.atan2(z, w)

        print(f"Position capturée : x={x:.2f}, y={y:.2f}, theta={theta:.2f}")
        name = input("Nom de ce point : ").strip()
        if name:
            self.locations[name] = {
                'x': float(x),
                'y': float(y),
                'theta': round(theta, 2)
            }
            print(f"✅ Point « {name} » enregistré.\n")

    def destroy_node(self):
        if self.locations:
            with open(self.yaml_path, 'w') as f:
                yaml.dump(self.locations, f)
            print(f"📁 Fichier sauvegardé ici : {self.yaml_path}")
        super().destroy_node()

def main():
    rclpy.init()
    node = WaypointRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

