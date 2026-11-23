import customtkinter as ctk
from PIL import Image, ImageTk
import subprocess
import sys
import multiprocessing
import os
import json
from ai_brains import get_available_ai_builds, BASE_BUILD_NAME

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
    # Incarcam setarile salvate anterior (nume echipe, AI build, durata meci)
    saved_team_a_name = "RED"
    saved_team_b_name = "BLUE"
    saved_team_a_ai = BASE_BUILD_NAME
    saved_team_b_ai = BASE_BUILD_NAME
    avail_builds = get_available_ai_builds()
    try:
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as rf:
                loaded_init = json.load(rf)
                teams_cfg = loaded_init.get("teams", {})
                saved_team_a_name = str(teams_cfg.get("A", {}).get("name", "RED")).strip() or "RED"
                saved_team_b_name = str(teams_cfg.get("B", {}).get("name", "BLUE")).strip() or "BLUE"
                ta_ai = str(teams_cfg.get("A", {}).get("ai_build", BASE_BUILD_NAME))
                tb_ai = str(teams_cfg.get("B", {}).get("ai_build", BASE_BUILD_NAME))
                if ta_ai in avail_builds:
                    saved_team_a_ai = ta_ai
                if tb_ai in avail_builds:
                    saved_team_b_ai = tb_ai
    except Exception:
        pass

    def set_game_mode_and_launch(mode):
        print(f"Starting the game in mode: {mode}...")
        name_a = (team_a_entry.get().strip()[:10].upper()) or "RED"
        name_b = (team_b_entry.get().strip()[:10].upper()) or "BLUE"
        ai_a = team_a_ai_combo.get() or BASE_BUILD_NAME
        ai_b = team_b_ai_combo.get() or BASE_BUILD_NAME

        settings_data = {
            "match_rules": {"match_duration_real_seconds": 180.0, "game_mode": mode},
            "teams": {
                "A": {"name": name_a, "ai_build": ai_a},
                "B": {"name": name_b, "ai_build": ai_b}
            }
        }
        try:
            if os.path.exists("settings.json"):
                with open("settings.json", "r") as f:
                    loaded = json.load(f)
                    if "match_rules" in loaded:
                        settings_data["match_rules"].update(loaded["match_rules"])
                        settings_data["match_rules"]["game_mode"] = mode
        except Exception:
            pass
        try:
            with open("settings.json", "w") as f:
                json.dump(settings_data, f, indent=4)
        except Exception:
            pass

        root.withdraw() # Ascunde fereastra launcherului

        # Lansam exe-ul curent, dar ii spunem sa deschida visualizer-ul
        p = subprocess.Popen(get_command("--visualizer"))
        ret_code = p.wait() # Asteapta ca jocul sa se inchida
        if ret_code == 42:
            # Utilizatorul a apasat "MAIN MENU" in timpul jocului -> readucem meniul principal pe ecran!
            # Reimprospatam lista de AI builds in caz ca s-a antrenat un model nou
            fresh_builds = get_available_ai_builds()
            team_a_ai_combo.configure(values=fresh_builds)
            team_b_ai_combo.configure(values=fresh_builds)
            root.deiconify()
        else:
            root.destroy() # Opreste executia launcher.py cand utilizatorul apasa QUIT / ESC

    def on_start_clicked():
        set_game_mode_and_launch("match")

    def on_scenarios_clicked():
        set_game_mode_and_launch("scenarios")

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
            
            # Construim JSON-ul pastrand game_mode si configuratia echipelor
            existing_mode = "match"
            existing_teams = {
                "A": {"name": (team_a_entry.get().strip()[:10].upper()) or "RED", "ai_build": team_a_ai_combo.get() or BASE_BUILD_NAME},
                "B": {"name": (team_b_entry.get().strip()[:10].upper()) or "BLUE", "ai_build": team_b_ai_combo.get() or BASE_BUILD_NAME}
            }
            try:
                if os.path.exists("settings.json"):
                    with open("settings.json", "r") as rf:
                        existing_mode = json.load(rf).get("match_rules", {}).get("game_mode", "match")
            except Exception:
                pass
            new_settings = {
                "match_rules": {
                    "match_duration_real_seconds": final_seconds,
                    "game_mode": existing_mode
                },
                "teams": existing_teams
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

    # ==========================================================
    # CARDURI CONFIGURARE ECHIPE (NUME + SELECTOR AI BUILD)
    # ==========================================================
    # Card Stanga: ECHIPA A (RED)
    team_a_card = ctk.CTkFrame(root, width=225, height=130, corner_radius=12, fg_color="#161C28", border_width=2, border_color="#DC143C")
    team_a_card.pack_propagate(False)
    team_a_card.place(relx=0.20, rely=0.54, anchor="center")

    ctk.CTkLabel(team_a_card, text="LEFT TEAM (RED)", font=("Arial", 12, "bold"), text_color="#FF5C77").pack(pady=(8, 4))
    team_a_entry = ctk.CTkEntry(team_a_card, width=185, height=28, placeholder_text="Team Name (RED)", justify="center", font=("Arial", 12, "bold"))
    team_a_entry.insert(0, saved_team_a_name)
    team_a_entry.pack(pady=(2, 6))

    team_a_ai_combo = ctk.CTkComboBox(team_a_card, width=185, height=28, values=avail_builds, state="readonly", font=("Arial", 12))
    team_a_ai_combo.set(saved_team_a_ai)
    team_a_ai_combo.pack(pady=(2, 6))

    # Card Dreapta: ECHIPA B (BLUE)
    team_b_card = ctk.CTkFrame(root, width=225, height=130, corner_radius=12, fg_color="#161C28", border_width=2, border_color="#1E90FF")
    team_b_card.pack_propagate(False)
    team_b_card.place(relx=0.80, rely=0.54, anchor="center")

    ctk.CTkLabel(team_b_card, text="RIGHT TEAM (BLUE)", font=("Arial", 12, "bold"), text_color="#5BB2FF").pack(pady=(8, 4))
    team_b_entry = ctk.CTkEntry(team_b_card, width=185, height=28, placeholder_text="Team Name (BLUE)", justify="center", font=("Arial", 12, "bold"))
    team_b_entry.insert(0, saved_team_b_name)
    team_b_entry.pack(pady=(2, 6))

    team_b_ai_combo = ctk.CTkComboBox(team_b_card, width=185, height=28, values=avail_builds, state="readonly", font=("Arial", 12))
    team_b_ai_combo.set(saved_team_b_ai)
    team_b_ai_combo.pack(pady=(2, 6))
    
    # Butonul modern de START MATCH (90 MIN)
    start_button = ctk.CTkButton(
        root, 
        text="START MATCH", 
        font=("Arial", 18, "bold"), 
        fg_color="#CC0000", # Rosu aprins
        hover_color="#990000", # Rosu inchis la hover
        width=210, 
        height=50,
        corner_radius=10, # Buton rotunjit
        command=on_start_clicked
    )
    start_button.place(relx=0.33, rely=0.85, anchor="center")

    # Butonul modern pentru TACTICAL SCENARIOS (Faze & Testare)
    scenarios_button = ctk.CTkButton(
        root,
        text="TACTICAL SCENARIOS",
        font=("Arial", 18, "bold"),
        fg_color="#0066CC", # Albastru electric
        hover_color="#004C99", # Albastru inchis la hover
        width=240,
        height=50,
        corner_radius=10,
        command=on_scenarios_clicked
    )
    scenarios_button.place(relx=0.66, rely=0.85, anchor="center")

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
