import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import tkinter as tk
import json
from dialog_gui.chat_interface import ChatWindow

class GuiNode(Node):
    def __init__(self):
        super().__init__('gui_node')
        
        # Initialiser tkinter
        self.root = tk.Tk()
        self.chat_window = ChatWindow(self.root)
        
        # Créer un souscripteur pour recevoir les transcriptions des commandes vocales
        self.subscription = self.create_subscription(
            String,
            '/llm_input_audio_to_text',
            self.listener_user_callback,
            10)
            
        # Créer un souscripteur pour recevoir les messages de ChatGPT
        self.subscription = self.create_subscription(
            String,
            '/llm_feedback_to_user',
            self.listener_chatgpt_callback,
            10)
        
        # Démarrer tkinter avec ROS en synchronisation
        self.root.after(100, self.ros_spin)
        self.root.mainloop()
    
    def listener_user_callback(self, msg):
        # Afficher le message reçu dans la fenêtre tkinter
        self.chat_window.display_message("USER", msg.data, "lightblue")

    def listener_chatgpt_callback(self, msg):
    	# Convertir le message string en dictionnaire JSON
        response_dict = json.loads(msg.data)
        # Extraire uniquement la clé "respond"
        response_text = response_dict.get("respond", "[Error: No 'respond' field found]")
        # Afficher le message reçu dans la fenêtre tkinter
        self.chat_window.display_message("ROBOT", response_text, "lightgreen")
    
    def ros_spin(self):
        rclpy.spin_once(self, timeout_sec=0)
        self.root.after(100, self.ros_spin)

def main(args=None):
    rclpy.init(args=args)
    gui_node = GuiNode()
    rclpy.spin(gui_node)
    gui_node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()

