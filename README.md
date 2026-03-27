# 📸 EXIFeditor Pro

A professional yet simple desktop application to modify GPS and Date/Time metadata for your photos. Built with Python and PySide6, featuring an interactive Leaflet map for precise location tagging.

---

## 🚀 Getting Started

If you have never used a Python app before, follow these steps to get running on your computer.

### 1. Check your Python Version
The version of Python that comes pre-installed on macOS is often outdated and restricted. You need **Python 3.11 or newer**.

**To check your version:**
Open your Terminal (Mac) or Command Prompt (Windows) and type:
`python3 --version`  (or just `python --version` on Windows)

If it says "Python 3.11" or higher, you are good! If not, download the latest version from [python.org](https://www.python.org/downloads/). 
> **Windows Users:** During installation, you MUST check the box that says **"Add Python to PATH"**.

### 2. Download and Extract
Click the green **Code** button at the top of this GitHub page and select **Download ZIP**. Extract the folder to a location you can find easily, like your Desktop.

### 3. Create a Virtual Environment (Recommended)
A "Virtual Environment" (venv) keeps this project's files separate from the rest of your computer.

**On macOS:**
1. Open Terminal and type `cd ` (with a space at the end).
2. Drag the project folder from your Desktop into the Terminal window and hit Enter.
3. Run: `python3 -m venv venv`
4. Run: `source venv/bin/activate`

**On Windows:**
1. Open Command Prompt and type `cd ` (with a space at the end).
2. Drag the project folder into the window and hit Enter.
3. Run: `python -m venv venv`
4. Run: `venv\Scripts\activate`

### 4. Install Dependencies
While your virtual environment is active (you will see `(venv)` at the start of your command line), run:

`pip install -r requirements.txt`

### 5. Run the App

Every time you want to use the app, you need to "turn on" (activate) your virtual environment so Python can find the libraries (like PySide6 and Pillow) you installed.

**How to tell if it's active:**
Look at the very beginning of your command line. You should see `(venv)` in parentheses, like this:
`(venv) C:\Users\Name\EXIFeditor> _`

**If you don't see (venv), turn it on first:**
* **Mac / Linux:** `source venv/bin/activate`
* **Windows:** `venv\Scripts\activate`

**Once active, start the app by typing:**
* **Mac / Linux:** `python3 main.py`
* **Windows:** `python main.py`

⚠️ **Note for the First Run:** The very first time you launch the app, it may take **10 to 15 seconds** for the window to appear. This is normal! Python is setting up the map engine and loading the interface. Subsequent launches will be much faster.

---

## 🛠 Features

* **Interactive Map**: Click anywhere on the world map to set GPS coordinates.
* **Batch Processing**: Update hundreds of photos at once.
* **Smart Conversion**: Automatically converts PNG files to JPG for metadata compatibility.
* **MPO Support**: Handles 3D/Multi-Picture Object formats used by modern cameras.
* **Debug Logging**: Optional detailed process logs.

---

## 📜 Credits & Licenses

This project is made possible by the following open-source communities:

* **PySide6**: The official Python module for the Qt framework.
* **Pillow (PIL)**: The gold standard for image processing in Python.
* **piexif**: A powerful tool for reading and writing EXIF data.
* **timezonefinder**: Offline lookup of timezones based on coordinates.
* **Leaflet.js**: (Included in `/assets`) The leading open-source library for interactive maps. 
  * *Leaflet is licensed under the BSD 2-Clause License.*

---

## 🤝 Contributing

Found a bug or have a feature request? Feel free to open an Issue or submit a Pull Request.