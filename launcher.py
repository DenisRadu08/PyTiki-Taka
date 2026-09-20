import customtkinter as ctk
from PIL import Image, ImageTk
import subprocess
import sys
import multiprocessing
import os
import json

def resource_path(relative_path):
    # Gaseste folderul secret unde PyInstaller dezarhiveaza fisierele
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_command(arg):
    if getattr(sys, 'frozen', False):
        # Daca suntem compilati ca .exe
        return [sys.executable, arg]
    else:
        # Daca rulam codul sursa Python curent
        return [sys.executable, "launcher.py", arg]

def run_launcher():
    def on_start_clicked():
        print("Starting the game...")
        root.withdraw() # Ascunde fereastra launcherului

        # Lansam exe-ul curent, dar ii spunem sa deschida visualizer-ul
        p = subprocess.Popen(get_command("--visualizer"))
        p.wait() # Asteapta ca jocul sa se deschida inainte de a continua
        root.destroy() # Opreste executia launcher.py

    # ==========================================
    # LOGICA FERESTREI DE SETARI
    # ==========================================
    def open_settings():
        settings_window = ctk.CTkToplevel(root)
        settings_window.title("Game Preferences")
        settings_window.geometry("400x350")
        settings_window.attributes('-topmost', True) # Apare deasupra tuturor
        settings_window.grab_set() # Blocheaza restul launcher-ului pana o inchidem

        # Titlu
        label_title = ctk.CTkLabel(settings_window, text="Match Settings", font=("Arial", 20, "bold"))
        label_title.pack(pady=20)

        # ====== COMBINATIE DROPDOWN ======
        label_combo = ctk.CTkLabel(settings_window, text="Match Duration:")
        label_combo.pack(pady=(10, 0))
        
        combo_options = ["3 min", "4 min", "5 min", "6 min", "8 min", "10 min"]
        duration_combo = ctk.CTkComboBox(settings_window, values=combo_options, state="readonly")
        duration_combo.set("3 min") # Default
        duration_combo.pack(pady=5)

        # ====== DEV OVERRIDE (SECUNDE) ======
        label_dev = ctk.CTkLabel(settings_window, text="[DEV ONLY] Override Seconds:")
        label_dev.pack(pady=(10, 0))
        
        dev_entry = ctk.CTkEntry(settings_window, placeholder_text="Ex: 15 (Leave empty for normal)")
        dev_entry.pack(pady=5)

        # LOGICA DE SALVARE
        def save_settings():
            dev_val = dev_entry.get().strip()
            
            # Verificam daca dev-ul a scris ceva in textbox
            if dev_val.isdigit():
                final_seconds = float(dev_val)
            else:
                # Daca nu a scris nimic, calculam din combobox
                selected_text = duration_combo.get()
                minutes = int(selected_text.split(" ")[0])
                final_seconds = float(minutes * 60)
            
            # Construim JSON-ul
            new_settings = {
                "match_rules": {
                    "match_duration_real_seconds": final_seconds
                }
            }

            # Scriem in settings.json
            with open("settings.json", "w") as f:
                json.dump(new_settings, f, indent=4)
                
            print(f"Setari salvate! {final_seconds} secunde.")
            settings_window.destroy() # Inchidem pop-up-ul
        
        # Buton Save
        save_button = ctk.CTkButton(
            settings_window, 
            text="Save Settings", 
            fg_color="#28a745", 
            hover_color="#218838", 
            command=save_settings
        )
        save_button.pack(pady=30)

    # Cream fereastra principala
    root = ctk.CTk()
    root.title("PyTiki-Taka Launcher")

    # Setam dimensiunea la exact aspectul 16:9 al imaginii
    root.geometry("800x450")
    root.resizable(False, False) # Nu lasam userul sa strice fereastra

    # Incarcam iconita direct din JPG pentru a ocoli formatul ICO
    try:
        root.iconbitmap(resource_path("logo.ico"))
    except Exception as e:
        print(f"EROARE LA ICONITA: {e}")

    # Incarcam background-ul 16:9
    bg_image = ctk.CTkImage(
        light_image=Image.open(resource_path("launcher_bg.jpg")), 
        dark_image=Image.open(resource_path("launcher_bg.jpg")), 
        size=(800, 450)
    )

    # Plasam imaginea pe tot fundalul
    bg_label = ctk.CTkLabel(root, image=bg_image, text="")
    bg_label.place(relx=0.5, rely=0.5, anchor="center")
    
    # Butonul modern de START
    start_button = ctk.CTkButton(
        root, 
        text="START MATCH", 
        font=("Arial", 20, "bold"), 
        fg_color="#CC0000", # Rosu aprins
        hover_color="#990000", # Rosu inchis la hover
        width=200, 
        height=50,
        corner_radius=10, # Buton rotunjit
        command=on_start_clicked
    )
    # Il plasam in partea de jos a ecranului
    start_button.place(relx=0.5, rely=0.85, anchor="center")

    # ====== Butonul de SETTINGS ======
    settings_button = ctk.CTkButton(
        root,
        text="⚙ SETTINGS",
        font=("Arial", 14, "bold"),
        fg_color="#333333", 
        hover_color="#555555",
        width=120,
        height=35,
        corner_radius=8,
        command=open_settings
    )

    # Il plasam in coltul din dreapta-sus
    settings_button.place(relx=0.85, rely=0.1, anchor="center")

    root.mainloop()

# Pornim bucla UI
if __name__ == "__main__":
    # OBLIGATORIU pe Windows pentru a crea 
    # executabile cu multiprocessing fara a da crash
    multiprocessing.freeze_support()

    # MASTER SWITCHBOARD
    # Verificam cu ce argumente a fost pornit acest fisier
    if len(sys.argv) == 1:
        # Daca nu are argumente (dublu-click normal),
        # pornim Launcher-ul UI
        run_launcher()

    elif sys.argv[1] == "--visualizer":
        # Daca are argumentul --visualizer,
        # pornim motorul grafic
        from visualizer import GameVisualizer
        app = GameVisualizer()
        app.run()
    
    elif sys.argv[1] == "--engine":
        # Daca are argumentul --engine, pornim motorul
        # de joc si agentii (ce facea main.py)
        import main
        main.run_game()
