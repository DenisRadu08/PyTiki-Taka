import PyInstaller.__main__
import customtkinter
import os

# Find exactly where CustomTkinter is hiding on your hard drive
customtkinter_location = os.path.dirname(customtkinter.__file__)

print(f"Found CustomTkinter at: {customtkinter_location}")
print("Starting build...")

# Run PyInstaller programmatically
PyInstaller.__main__.run([
    'launcher.py',
    '--noconsole',
    '--onefile',
    '--name=PyTikiTaka',
    '--icon=logo.ico',
    '--add-data=logo.ico;.',
    '--add-data=launcher_bg.jpg;.',
    # Forcibly inject the entire CustomTkinter folder!
    f'--add-data={customtkinter_location};customtkinter/'
])
