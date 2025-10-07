#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from nav_msgs.msg import Path
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

from openai import OpenAI
from llm_config.user_config import UserConfig
from ament_index_python.packages import get_package_share_directory
import os

import math
import json

# Initialisation
config = UserConfig()
client = OpenAI(api_key=config.openai_api_key)

class LLMGuidanceNode(Node):
    def __init__(self):
        super().__init__('llm_guidance_node')
        self.get_logger().info('LLM Guidance Node started')
        self.declare_parameter("plan_topic", "/plan")
        self.plan_topic = self.get_parameter("plan_topic").get_parameter_value().string_value
        self.subscription = self.create_subscription(Path, self.plan_topic, self.plan_callback, 10)
        self.feedback_publisher = self.create_publisher(String, "/llm_feedback_to_user", 10)
        self.get_logger().info(f"LLMGuidance ready. Listening to {self.plan_topic}...")
        
        # Charger le contenu du contexte de guidage depuis un fichier texte
        package_share = get_package_share_directory('llm_guidance')
        guidance_context_path = os.path.join(package_share, 'guidance_context.txt')
        with open(guidance_context_path, "r") as f:
            self.prompt_template = f.read()
            
        guidance_dictionnary_path = os.path.join(package_share, 'guidance_dictionnary.txt')
        with open(guidance_dictionnary_path, "r") as f:
            self.words_dictionnary = f.read()

    def plan_callback(self, msg: Path):
        poses = msg.poses
        if len(poses) < 2:
            self.get_logger().warn("Plan has too few points.")
            return

        self.get_logger().info(f"Plan received with {len(poses)} points.")

        for i in range(len(poses) - 1):
            current = poses[i].pose.position
            next_p = poses[i+1].pose.position

            dx = next_p.x - current.x
            dy = next_p.y - current.y
            distance = round(math.sqrt(dx**2 + dy**2), 2)
            angle = round(math.degrees(math.atan2(dy, dx)), 1)

            # Préparation du prompt
            # Remplacer le placeholder dans le prompt
            #prompt = self.prompt_template.replace("{guidance_words_list}", self.words_dictionnary, "{distance}", distance, "{angle}", angle)
            prompt = self.prompt_template.format(guidance_words_list=self.words_dictionnary, distance=distance, angle=angle)

            llm_response = self.call_llm(prompt)
            if llm_response:
                msg_out = String()
                msg_out.data = llm_response
                self.feedback_publisher.publish(msg_out)
                self.get_logger().info(f"Instruction envoyée : {llm_response}")
            else:
                self.get_logger().error("Erreur lors de l’appel LLM")

    def call_llm(self, prompt):
        try:
            messages = [{"role": "system", "content": "Tu es un assistant vocal pour la navigation en intérieur."},
                        {"role": "user", "content": prompt}]
            completion = client.chat.completions.create(
                model=config.openai_model,
                messages=messages,
                temperature=config.openai_temperature,
                max_tokens=config.openai_max_tokens,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            self.get_logger().error(f"Erreur appel LLM : {e}")
            return None

def main(args=None):
    rclpy.init(args=args)
    node = LLMGuidanceNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()

