import tkinter as tk
from tkinter import scrolledtext

class ChatWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Interface")

        # Créer la boîte de dialogue avec une barre de défilement
        self.chat_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, bg="white")
        self.chat_box.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.chat_box.config(state=tk.DISABLED)

        # Ajouter le bouton de réinitialisation
        self.reset_button = tk.Button(root, text="Nettoyer", command=self.reset_chat)
        self.reset_button.pack(pady=10)

    def display_message(self, sender, message, backgroundColor):
        self.chat_box.config(state=tk.NORMAL)
        
        # Insérer le fond vert pour le "sender"
        self.chat_box.insert(tk.END, f"{sender}::", "sender")
        
        # Insérer le message
        self.chat_box.insert(tk.END, f" {message}\n\n")
        
        self.chat_box.tag_config("sender", background=backgroundColor)
        
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.yview(tk.END)

    def reset_chat(self):
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.delete('1.0', tk.END)
        self.chat_box.config(state=tk.DISABLED)

'''
# Testez la fenêtre de chat avec tkinter
if __name__ == "__main__":
    root = tk.Tk()
    chat_window = ChatWindow(root)
    chat_window.display_message("User", "Hello, how are you?")
    chat_window.display_message("ChatGPT", "I'm fine, thank you!")
    root.mainloop()
'''

