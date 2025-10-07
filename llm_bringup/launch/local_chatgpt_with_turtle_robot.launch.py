#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# flake8: noqa
#
# Copyright 2023 Herman Ye @Auromix
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Description:
# This launch file is a part of ROS-LLM project developed to control and interact with the turtlesim robot or your own robot.
# The launch file contains a LaunchDescription object which defines the ROS2 nodes to be executed.
# 
# Node test Method:
# ros2 launch llm_bringup local_chatgpt_with_turtle_robot.launch.py
# ros2 topic pub /llm_state std_msgs/msg/String "data: 'listening'" -1

# Author: Herman Ye @Auromix

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    """
    # Chemins vers les packages
    turtlebot3_gazebo_dir = get_package_share_directory('turtlebot3_gazebo')
    nav2_bringup_dir = get_package_share_directory('turtlebot3_navigation2')
    home_dir = os.path.expanduser("~")
    map_path = os.path.join(home_dir, "map_house.yaml")
    
    if not os.path.exists(map_path):
        raise RuntimeError(f"map file not found: {map_path}")

    # Lancement de turtlebot3_house.launch.py
    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(turtlebot3_gazebo_dir, 'launch', 'turtlebot3_house.launch.py')
        )
    )

    # Lancement de navigation2 avec la carte
    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'navigation2.launch.py')
        ),
        launch_arguments={
            'map': map_path,
            'use_sim_time': 'True',
            'autostart': 'True',
            'use_composition': 'False',
        }.items()
    )
    """
    
    
    
    return LaunchDescription(
        [
            DeclareLaunchArgument(
            'output_dir',
            default_value='/tmp/metrics',
            description='Répertoire où le nœud "results" écrit les métriques'),
            
            Node(
                package="results",
                executable="results_node",
                name="results_node",
                output="screen",
                arguments=['--ros-args', '-p', ['output_dir:=', LaunchConfiguration('output_dir')]],
            ),
            
            Node(
                package="auto_pose_robot",
                executable="auto_initial_pose",
                name="auto_initial_pose",
                output="screen",
            ),
            
            Node(
                package="dialog_gui",
                executable="gui_node",
                name="gui_node",
                output="screen",
            ),
            
            Node(
                package="nav_command",
                executable="navigation_command_node",
                name="navigation_command_node",
                output="screen",
            ),
            
            Node(
                package="llm_guidance",
                executable="llm_guidance_node",
                name="llm_guidance_node",
                output="screen",
            ),
            
            Node(
                package="llm_input",
                executable="llm_audio_input_local",
                name="llm_audio_input_local",
                output="screen",
            ),
            Node(
                package="llm_model",
                executable="chatgpt",
                name="chatgpt",
                output="screen",
            ),
            Node(
                package="llm_output",
                executable="llm_audio_output",
                name="llm_audio_output",
                output="screen",
            ),
        ]
    )
