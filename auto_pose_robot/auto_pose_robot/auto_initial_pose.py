#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.logging import LoggingSeverity
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseWithCovarianceStamped
import math

class AutoInitialPose(Node):
    def __init__(self):
        super().__init__('auto_initialpose')

        # QoS TRANSIENT_LOCAL pour latched publishing
        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE
        )
        self.publisher_ = self.create_publisher(
            PoseWithCovarianceStamped,
            '/initialpose',
            qos)

        # On attend la première Odometry depuis Gazebo pour calculer la pose RViz
        self.subscription_ = self.create_subscription(
            Odometry,
            '/odom',
            self.odom_callback,
            10)

        self.publie_initialpose = False

        # Paramètres « coin bas-gauche » et rotation commune
        # Dans Gazebo :
        self.coinG_x = -7.5
        self.coinG_y =  5.0
        # Dans RViz :
        self.coinR_x = -8.56
        self.coinR_y = -13.1
        # Angle de rotation (coinG ψ = 0 → coinR ψ = +1.57)
        self.rot = 1.57

        self.get_logger().info('AutoInitialPose attend /odom pour publier la pose RViz.')

    def odom_callback(self, msg: Odometry):
        if self.publie_initialpose:
            return

        # Pose Gazebo extraite de /odom
        xG = msg.pose.pose.position.x
        yG = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yawG = math.atan2(siny_cosp, cosy_cosp)

        # 1) Calcul du déplacement relatif dans Gazebo
        dx = xG - self.coinG_x
        dy = yG - self.coinG_y

        # 2) Rotation de ce vecteur de +rot (1.57 rad)
        #    [ dx'; dy' ] = R(rot) · [dx; dy]
        cr = math.cos(self.rot)
        sr = math.sin(self.rot)
        dx_r = cr * dx - sr * dy
        dy_r = sr * dx + cr * dy

        # 3) Traduction finale dans RViz
        xR = self.coinR_x + dx_r
        yR = self.coinR_y + dy_r
        yawR = yawG + self.rot

        # Construire le message PoseWithCovarianceStamped
        initial_msg = PoseWithCovarianceStamped()
        initial_msg.header.stamp = self.get_clock().now().to_msg()
        initial_msg.header.frame_id = 'map'
        initial_msg.pose.pose.position.x = xR
        initial_msg.pose.pose.position.y = yR
        initial_msg.pose.pose.position.z = 0.0
        initial_msg.pose.pose.orientation.x = 0.0
        initial_msg.pose.pose.orientation.y = 0.0
        initial_msg.pose.pose.orientation.z = math.sin(yawR / 2.0)
        initial_msg.pose.pose.orientation.w = math.cos(yawR / 2.0)

        # Covariance diagonale
        cov = [0.0] * 36
        cov[0]  = 0.25        # variance x
        cov[7]  = 0.25        # variance y
        cov[35] = 0.0685389   # variance yaw (~15° écart-type)
        initial_msg.pose.covariance = cov

        # Publication sur /initialpose
        self.publisher_.publish(initial_msg)
        self.get_logger().info(
            f'▶ Publié initialpose RViz → x: {xR:.2f}, y: {yR:.2f}, θ: {yawR:.2f} rad'
        )

        # Plus de callbacks futurs
        self.publie_initialpose = True
        self.destroy_subscription(self.subscription_)

        # Passer le logger en WARN pour ne plus spammer
        self.get_logger().set_level(LoggingSeverity.WARN)

        # Arrêter le node après 0.5 s pour laisser le message se propager
        self.create_timer(0.5, self.shutdown_node)

    def shutdown_node(self):
        self.get_logger().warn('Arrêt automatique du node AutoInitialPose.')
        self.destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = AutoInitialPose()
    rclpy.spin(node)
    if rclpy.ok():
        node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()

