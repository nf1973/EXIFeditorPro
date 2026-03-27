import sys
import os
import piexif
import shutil
import zoneinfo 
import platform
import subprocess

from pathlib import Path
from datetime import datetime, timedelta
from timezonefinder import TimezoneFinder
from PySide6.QtCore import Qt, QThread, Signal, QDateTime, QObject, Slot, QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QListWidget, QListWidgetItem, QLabel, QCheckBox, 
    QLineEdit, QPushButton, QProgressBar, QGroupBox, QGridLayout, 
    QDateTimeEdit, QSplitter, QDoubleSpinBox, QMessageBox, QStyle
)
from PySide6.QtGui import QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PIL import Image

# CONFIGURATION OPTIONS
APP_NAME = "EXIFeditor Pro"         # The Window Title in the App!
OUTPUT_FOLDER = "EXIFeditorPro"     # The name of the folder to create (within the user's Desktop folder)
DEFAULT_THEME_DARK = False          # If True, Dark Mode is used at startup
DEFAULT_UPDATE_DATE = False         # If True, Update Date / Time Metadata is checked at startup
DEFAULT_UPDATE_GPS = False          # If True, Update GPS Location is checked at startup
CONVERSION_TO_JPG_QUALITY = 95      # Increasing to 100 is possible - images will be much bigger but probably not noticably different quality
AUTO_CLEAR_AFTER_PROCESSING = True  # If True, clears the file list automatically after processing
AUTO_OPEN_OUTPUT_FOLDER = True      # If True, automatically opens the output folder after processing
DEBUG_MODE = False                  # If True, creates a log file in the output folder

# SET DEFAULT MAP LOCATION AND ZOOM LEVEL - Set the default location to Trafalgar Square, London and default Timezone to UTC
DEFAULT_LAT = 51.5080
DEFAULT_LON = -0.1281
DEFAULT_OFFSET = 0.0                # UTC Offset at DEFAULT_LAT, DEFAULT_LON
DEFAULT_MAP_ZOOM = 5                # Fully zoomed out = 0, Fully zoomed in = 20

# Determine the primary system font based on OS
if platform.system() == "Darwin":     # macOS
    DEFAULT_FONT = '".AppleSystemUIFont"'
elif platform.system() == "Windows": # Windows
    DEFAULT_FONT = '"Segoe UI"'
else:                                # Linux/Ubuntu
    DEFAULT_FONT = '"Ubuntu", "Liberation Sans"'

MAP_HTML = f"""
<!DOCTYPE html>
<html>
<head>
    <!-- Local Leaflet Files -->
    <link rel="stylesheet" href="leaflet.css" />
    <script src="leaflet.js"></script>
    
    <!-- Qt WebChannel (Leave this exactly as is) -->
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    
    <style>
        body {{ margin: 0; padding: 0; overflow: hidden; }}
        #map {{ 
            height: 100vh; width: 100vw; background: #ddd; 
            transition: filter 0.4s ease, opacity 0.4s ease;
        }}
        /* Styles for the "Greyed Out" state */
        .disabled-map {{ 
            filter: grayscale(100%) brightness(0.7); 
            opacity: 0.6; 
            pointer-events: none; 
        }}
        #overlay {{
            position: absolute; top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.7); color: white;
            padding: 20px; border-radius: 10px; font-family: sans-serif;
            z-index: 1000; display: none; text-align: center;
            border: 1px solid rgba(255,255,255,0.2);
        }}
    </style>
</head>
<body>
    <div id="overlay">Map interaction is disabled.<br>Select <b>"Update GPS Location"</b> to pick a location.</div>
    <div id="map"></div>
    <script>
        var map = L.map('map', {{ 
            zoomControl: true, tap: false, dragging: true, scrollWheelZoom: true
        }}).setView([{DEFAULT_LAT}, {DEFAULT_LON}], {DEFAULT_MAP_ZOOM});

        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '© OpenStreetMap'
        }}).addTo(map);

        var marker = L.marker([{DEFAULT_LAT}, {DEFAULT_LON}], {{ draggable: true }}).addTo(map);
        
        var bridge;
        new QWebChannel(qt.webChannelTransport, function (channel) {{
            bridge = channel.objects.pyBridge;
        }});

        map.on('click', function(e) {{
            marker.setLatLng(e.latlng);
            if(bridge) {{ bridge.updateCoords(e.latlng.lat, e.latlng.lng); }}
        }});

        // Function called by Python to toggle the visual state
        window.setMapState = function(enabled) {{
            var mapDiv = document.getElementById('map');
            var overlay = document.getElementById('overlay');
            if (enabled) {{
                mapDiv.classList.remove('disabled-map');
                overlay.style.display = 'none';
            }} else {{
                mapDiv.classList.add('disabled-map');
                overlay.style.display = 'block';
            }}
        }};

        setTimeout(function() {{ map.invalidateSize(); }}, 500);
    </script>
</body>
</html>
"""

class MapBridge(QObject):
    coordsChanged = Signal(float, float)
    @Slot(float, float)
    def updateCoords(self, lat, lng):
        self.coordsChanged.emit(lat, lng)

class ImageUpdater(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(str)

    def __init__(self, files, payload):
        super().__init__()
        self.files, self.payload = files, payload
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.out_dir = Path.home() / "Desktop" / f"{OUTPUT_FOLDER}" / f"{timestamp}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        
        # Start Location & UTC Offset
        self.current_lat = DEFAULT_LAT
        self.current_lng = DEFAULT_LON
        self.current_offset = DEFAULT_OFFSET

    def to_dms(self, dec):
        d = int(abs(dec)); m = int((abs(dec) - d) * 60)
        s = (abs(dec) - d - m/60) * 3600
        return ((d, 1), (m, 1), (int(s * 100), 100))

    def run(self):
        
        # Determine if Debugging is turned on
        if DEBUG_MODE:
            log_path = self.out_dir / "debug_log.txt"
            log_context = open(log_path, "a", encoding="utf-8")
        else:
            # This creates a dummy context that does nothing when called
            import io
            log_context = io.StringIO()

        with log_context as log:
            log.write(f"Processing started at {datetime.now()}\n\n")
            log.write(f"Settings: GPS={self.payload['apply_gps']} ({self.payload['lat']}, {self.payload['lon']})\n")
            log.write(f"Settings: Date={self.payload['apply_date']} ({self.payload['date_val']}) Offset={self.payload['offset_h']}h\n")
            log.write(f"Number of files to process: {len(self.files)}\n")

            for i, file_path in enumerate(self.files):
                try:
                    self.status.emit(f"Processing: {os.path.basename(file_path)}")
                    log.write(f"\n[{i+1}/{len(self.files)}] FILE: {os.path.basename(file_path)}\n")

                    p = Path(file_path)
                    file_stem = p.stem
                    current_working_source = file_path
                    original_ext = p.suffix

                    # Check the real contents of the file
                    with Image.open(file_path) as img_check:
                        actual_format = img_check.format
                        log.write(f"  - Internal Format: {actual_format}\n")

                    ext_clean = original_ext.lower().replace('.', '')
                    is_disguised_png = (actual_format == "PNG" and ext_clean in ['jpg', 'jpeg'])
                    is_disguised_jpg = (actual_format in ("JPEG", "MPO") and ext_clean == 'png')

                    if is_disguised_png:
                        log.write(f"  - WARNING: PNG disguised as {original_ext}. Forcing PNG conversion logic.\n")
                        self.status.emit(f"Fixing disguised PNG: {os.path.basename(file_path)}")
                    elif is_disguised_jpg:
                        log.write(f"  - NOTE: JPEG disguised as {original_ext}. Ignoring extension, using JPG logic.\n")
                        self.status.emit(f"Handling disguised JPG: {os.path.basename(file_path)}")
                    
                    if actual_format not in ("JPEG", "PNG", "MPO"):
                        log.write(f"  - SKIPPED: {os.path.basename(file_path)} (Unsupported format: {actual_format})\n")
                    
                    is_png = (actual_format == "PNG")

                    # If input file is a PNG convert to JPG for the output
                    if is_png:
                        self.status.emit(f"Converting PNG to JPG: {os.path.basename(file_path)}")
                        img = Image.open(file_path)
                        if img.mode in ("RGBA", "P"):
                            # Create white background for transparent PNGs
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
                            img = background
                        else:
                            img = img.convert("RGB")
                        
                        # Save a temporary JPG to work with
                        temp_jpg = self.out_dir / f"temp_{i}.jpg"
                        log.write(f"  - Action: Converting PNG -> temporary JPG ({temp_jpg.name})\n")
                        img.save(str(temp_jpg), "JPEG", quality=CONVERSION_TO_JPG_QUALITY, subsampling=0)
                        log.write(f"  - Created temp JPG: {temp_jpg.name}\n")
                        current_working_source = str(temp_jpg)

                    # Load EXIF (from the JPG or the Converted PNG)
                    try:
                        exif_dict = piexif.load(current_working_source)
                    except Exception:
                        # Create empty EXIF structure if none exists already
                        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

                    if self.payload['apply_gps']:
                        lat, lon = self.payload['lat'], self.payload['lon']
                        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = 'N' if lat >= 0 else 'S'
                        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = self.to_dms(lat)
                        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = 'E' if lon >= 0 else 'W'
                        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = self.to_dms(lon)


                    if self.payload['apply_date']:
                        new_date = self.payload['date_val']
                        
                        # Update Standard EXIF Tags
                        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = new_date.encode('utf-8')
                        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = new_date.encode('utf-8')
                        exif_dict["0th"][piexif.ImageIFD.DateTime] = new_date.encode('utf-8')

                        # Update GPS Date/Time
                        try:
                            local_dt = datetime.strptime(new_date, "%Y:%m:%d %H:%M:%S")
                            # We subtract the offset to get back to UTC
                            # Example: 13:00 in NY (UTC-5) -> 13 - (-5) = 18:00 UTC
                            utc_dt = local_dt - timedelta(hours=self.payload['offset_h'])
                            
                            exif_dict["GPS"][piexif.GPSIFD.GPSDateStamp] = utc_dt.strftime("%Y:%m:%d").encode('utf-8')
                            exif_dict["GPS"][piexif.GPSIFD.GPSTimeStamp] = (
                                (utc_dt.hour, 1),
                                (utc_dt.minute, 1),
                                (utc_dt.second, 1)
                            )
                        except Exception as e:
                            log.write(f"  - GPS Time Calculation Error: {e}\n")

                    # Determine Destination Path - if it was a PNG, switch the extension to .jpg for the final file
                    output_ext = ".jpg" if is_png else original_ext
                    dest = self.out_dir / f"{file_stem}{output_ext}"

                    # Check for duplicates in output folder
                    counter = 1
                    while dest.exists():
                        dest = self.out_dir / f"{file_stem}_{counter}{output_ext}"
                        counter += 1

                    # Final Save
                    if is_png:
                        # Insert metadata into the temp JPG and rename it to final dest
                        piexif.insert(piexif.dump(exif_dict), current_working_source)
                        os.replace(current_working_source, str(dest))
                    else:
                        # Copy original JPG and update it
                        shutil.copy2(file_path, str(dest))
                        piexif.insert(piexif.dump(exif_dict), str(dest))

                    log.write(f"  - Output: Saved as {dest.name}\n")
                    log.write(f"  - Status: SUCCESS\n")

                except Exception as e:
                    log.write(f"  - Status: FAILED\n")
                    log.write(f"  - Error Detail: {type(e).__name__}: {str(e)}\n")
                    self.status.emit(f"Failed: {os.path.basename(file_path)}")
                    continue            

                self.progress.emit(int(((i + 1) / len(self.files)) * 100))

            log.write(f"\nProcessing finished at {datetime.now()}\n")
        self.finished.emit(str(self.out_dir))

class EXIFeditorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tf = TimezoneFinder()
        self.current_offset = 0.0
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 850)
        self.is_dark = DEFAULT_THEME_DARK
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        # ==========================================
        # 1. MAIN WINDOW & HORIZONTAL SPLITTER
        # ==========================================
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # The "Dividing Line" between the sidebar and the map
        splitter = QSplitter(Qt.Horizontal)
        
        # --- THE SIDEBAR CONTAINER ---
        # (Originally: left_widget)
        left_widget = QWidget()
        # --- THE SIDEBAR'S VERTICAL STACK ---
        # (Originally: left_layout)
        left_layout = QVBoxLayout(left_widget)

        # ==========================================
        # CONTROLS SIDEBAR (LEFT)
        # ==========================================
        
        # THEME HEADER
        header = QHBoxLayout()
        header.addStretch()
        btn_theme = QPushButton("🌓 Switch Mode")
        btn_theme.setFixedWidth(120)
        btn_theme.clicked.connect(self.toggle_theme)
        header.addWidget(btn_theme)
        left_layout.addLayout(header)

        # GROUP 1: FILELIST & BUTTONS
        f_group = QGroupBox("📁 1. Source Images")
        f_vbox = QVBoxLayout(f_group)
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection) 
        self.clear_file_list() 
        f_vbox.addWidget(self.file_list)

        # File management buttons
        btn_layout = QHBoxLayout()
        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self.remove_selected_files)
        btn_clr = QPushButton("Clear All")
        btn_clr.clicked.connect(self.clear_file_list)
        btn_layout.addWidget(btn_remove)
        btn_layout.addWidget(btn_clr)
        f_vbox.addLayout(btn_layout)
        
        left_layout.addWidget(f_group)

        # GROUP 2: DATE & TIME SETTINGS
        dt_group = QGroupBox("🕒 2. Date && Time")
        dt_grid = QGridLayout(dt_group)
        
        self.cb_date = QCheckBox("Update Date/Time Metadata")
        self.cb_date.setChecked(DEFAULT_UPDATE_DATE)
        dt_grid.addWidget(self.cb_date, 0, 0, 1, 2) 

        dt_grid.addWidget(QLabel("Local Time:"), 1, 0)
        self.dt_picker = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_picker.setCalendarPopup(True)
        self.dt_picker.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_picker.dateTimeChanged.connect(self.refresh_offset_on_date_change)
        dt_grid.addWidget(self.dt_picker, 1, 1)
        
        dt_grid.addWidget(QLabel("UTC Offset:"), 2, 0)
        self.offset_input = QDoubleSpinBox()
        self.offset_input.setRange(-14, 14)
        self.offset_input.setSingleStep(0.5)
        self.offset_input.setSuffix(" hrs")
        self.offset_input.setValue(DEFAULT_OFFSET)
        dt_grid.addWidget(self.offset_input, 2, 1)
        
        left_layout.addWidget(dt_group)

        # GROUP 3: GPS LOCATION SETTINGS
        gps_group = QGroupBox("📍 3. Location")
        gps_vbox = QVBoxLayout(gps_group)
        self.cb_gps = QCheckBox("Update GPS Location")
        self.cb_gps.setChecked(DEFAULT_UPDATE_GPS)
        gps_vbox.addWidget(self.cb_gps)
        
        self.in_coords = QLineEdit(f"{DEFAULT_LAT}, {DEFAULT_LON}")
        self.in_coords.setPlaceholderText("Lat, Lng (Click map to update)")
        gps_vbox.addWidget(self.in_coords)
        
        left_layout.addWidget(gps_group)

        # STATUS BAR
        left_layout.addStretch() 
        self.st_lbl = QLabel("Ready.")
        self.p_bar = QProgressBar()
        left_layout.addWidget(self.st_lbl)  
        left_layout.addWidget(self.p_bar)
        
        self.btn_run = QPushButton("🚀 PROCESS && SAVE IMAGES")
        self.btn_run.setFixedHeight(55)
        self.btn_run.clicked.connect(self.process)
        left_layout.addWidget(self.btn_run)

        # ==========================================
        # 3. MAP (RIGHT)
        # ==========================================
        self.browser = QWebEngineView()
        self.bridge = MapBridge()
        self.bridge.coordsChanged.connect(self.update_location_ui)
        
        s = self.browser.settings()
        s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True) 
        
        self.channel = QWebChannel(self.browser.page())
        self.channel.registerObject("pyBridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)

        # ==========================================
        # 4. FINAL ASSEMBLY & INTERACTION
        # ==========================================
        # Add the Controls Sidebar and Map into the Splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(1, 1) 
        main_layout.addWidget(splitter)
        
        self.setAcceptDrops(True)

        # Logic for the controls
        self.cb_gps.toggled.connect(self.toggle_gps_ui)
        self.toggle_gps_ui(self.cb_gps.isChecked())

        self.cb_date.toggled.connect(self.dt_picker.setEnabled)
        self.cb_date.toggled.connect(self.offset_input.setEnabled)

        self.dt_picker.setEnabled(self.cb_date.isChecked())
        self.offset_input.setEnabled(self.cb_date.isChecked())

        # Load Map
        script_dir = os.path.dirname(os.path.abspath(__file__))
        assets_dir = os.path.join(script_dir, "assets")
        base_url = QUrl.fromLocalFile(assets_dir + os.path.sep)
        self.browser.setHtml(MAP_HTML, baseUrl=base_url)
        self.browser.loadFinished.connect(lambda: self.toggle_gps_ui(self.cb_gps.isChecked()))

    def apply_theme(self):
        bg = "#1e1e1e" if self.is_dark else "#f5f5f5"
        fg = "#e0e0e0" if self.is_dark else "#333333"
        item_bg = "#2b2b2b" if self.is_dark else "#ffffff"
        border = "#3d3d3d" if self.is_dark else "#cccccc"
        accent = "#3498db"
        disabled_bg = "#1a1a1a" if self.is_dark else "#e0e0e0"
        disabled_fg = "#666666" if self.is_dark else "#888888"
        locked_bg = "#252525" if self.is_dark else "#eeeeee" 

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {bg}; color: {fg}; font-family: {DEFAULT_FONT}, sans-serif; }}
            QGroupBox {{ border: 1px solid {border}; margin-top: 15px; font-weight: bold; color: {accent}; border-radius: 5px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px; }}
            
            QLineEdit, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QListWidget {{ 
                background: {item_bg}; 
                border: 1px solid {border}; 
                padding: 5px; 
                color: {fg}; 
                border-radius: 3px; 
            }}
            
            QDoubleSpinBox[readOnly="true"], QLineEdit[readOnly="true"] {{
                background-color: {locked_bg};
                color: {fg}; 
                border: 1px solid {border}; 
            }}
            
            QLineEdit:disabled, QDateTimeEdit:disabled, QSpinBox:disabled, 
            QDoubleSpinBox:disabled, QCheckBox:disabled, QLabel:disabled {{ 
                color: {disabled_fg}; 
                background-color: {disabled_bg}; 
                border: 1px dashed {border};
            }}

            QPushButton {{ background: {accent if not self.is_dark else "#3d3d3d"}; color: white; border: none; padding: 8px; border-radius: 4px; }}
            QPushButton:hover {{ background: #2980b9; }}
            QProgressBar {{ border: 1px solid {border}; height: 12px; text-align: center; border-radius: 6px; background: {item_bg}; }}
            QProgressBar::chunk {{ background-color: {accent}; border-radius: 6px; }}
        """)

    def toggle_theme(self):
        self.is_dark = not self.is_dark
        self.apply_theme()

    def update_tz_from_current_coords(self):
        try:
            coords = self.in_coords.text().split(",")
            lat, lng = float(coords[0]), float(coords[1])
            self.update_location_ui(lat, lng)
        except:
            pass

    def toggle_gps_ui(self, gps_enabled):
        self.in_coords.setEnabled(gps_enabled)
        
        # Safely run Javascript only if the browser has a page loaded
        if not self.browser.url().isEmpty():
            state = "true" if gps_enabled else "false"
            self.browser.page().runJavaScript(f"setMapState({state});")
        
        self.offset_input.setReadOnly(gps_enabled)
        self.offset_input.setProperty("readOnly", gps_enabled)
        
        self.offset_input.style().unpolish(self.offset_input)
        self.offset_input.style().polish(self.offset_input)

    def clear_file_list(self):
        self.file_list.clear()
        hint_item = QListWidgetItem("🖼️ Drag & Drop JPG images here...")
        hint_item.setFlags(Qt.NoItemFlags)
        hint_item.setTextAlignment(Qt.AlignCenter)
        self.file_list.addItem(hint_item)

    def remove_selected_files(self):
            # Get list of selected items
            items = self.file_list.selectedItems()
            if not items:
                return
                
            for item in items:
                # Check if we are accidentally trying to "remove" the hint text
                if "Drag & Drop" in item.text():
                    continue
                self.file_list.takeItem(self.file_list.row(item))
                
            # If the user removed everything, bring the hint back
            if self.file_list.count() == 0:
                self.clear_file_list()

    def open_folder(self, path):
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':  # macOS
            subprocess.Popen(['open', path])
        else:  # Linux and other Unix-like systems
            subprocess.Popen(['xdg-open', path])

    def on_finished(self, folder_path):
            self.btn_run.setEnabled(True)
            self.st_lbl.setText("Ready.")
            self.p_bar.reset()
            
            AUTO_CLEAR_AFTER_PROCESSING and self.clear_file_list()
            AUTO_OPEN_OUTPUT_FOLDER and self.open_folder(folder_path)

    def update_location_ui(self, lat, lng):
        # Always update the UTC Offset if "Update GPS Location" is enabled
        if self.cb_gps.isChecked():
            self.in_coords.setText(f"{lat:.6f}, {lng:.6f}")
            
            tz_str = self.tf.timezone_at(lng=lng, lat=lat)
            if tz_str:
                try:
                    tz = zoneinfo.ZoneInfo(tz_str)
                    dt = self.dt_picker.dateTime().toPython()
                    offset = dt.replace(tzinfo=tz).utcoffset().total_seconds() / 3600
                    
                    # This works even if setReadOnly is True!
                    self.offset_input.setValue(offset)
                    self.current_offset = offset
                except: pass

    def refresh_offset_on_date_change(self):
        if self.cb_gps.isChecked():
            try:
                # Get current coords from the input field
                coords = self.in_coords.text().split(",")
                lat, lng = float(coords[0]), float(coords[1])
                
                # Use find the TZ and update the offset
                tz_str = self.tf.timezone_at(lng=lng, lat=lat)
                if tz_str:
                    tz = zoneinfo.ZoneInfo(tz_str)
                    # Use the NEWLY selected date to check for DST
                    dt = self.dt_picker.dateTime().toPython()
                    offset = dt.replace(tzinfo=tz).utcoffset().total_seconds() / 3600
                    
                    self.offset_input.setValue(offset)
                    self.current_offset = offset
            except Exception:
                pass

    def dragEnterEvent(self, e): e.accept() if e.mimeData().hasUrls() else e.ignore()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        
        # Check if the first item is our hint and remove it
        if self.file_list.count() > 0:
            first_item = self.file_list.item(0)
            if "Drag & Drop" in first_item.text():
                self.file_list.takeItem(0)


        existing = [self.file_list.item(i).data(Qt.UserRole) for i in range(self.file_list.count())]
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')) and f not in existing:
                pixmap = QPixmap(f).scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                #item = QListWidgetItem(QIcon(pixmap), os.path.basename(f))
                icon = self.style().standardIcon(QStyle.SP_FileIcon) 
                item = QListWidgetItem(icon, os.path.basename(f))
                item.setData(Qt.UserRole, f)
                self.file_list.addItem(item)

    def process(self):        
        files = [self.file_list.item(i).data(Qt.UserRole) 
                for i in range(self.file_list.count()) 
                if self.file_list.item(i).data(Qt.UserRole)]

        # Check for no files OR no tasks selected
        apply_gps = self.cb_gps.isChecked()
        apply_date = self.cb_date.isChecked()
        
        error_msg = ""
        if not files:
            error_msg = "Please add at least one image file to process."
        elif not (apply_gps or apply_date):
            error_msg = "Please enable at least one of 'Update Date/Time Metadata' or 'Update GPS Location'."

        if error_msg:
            QMessageBox.warning(self, "Action Required", error_msg)
            return

        try:
            coords = self.in_coords.text().split(",")
            lat, lon = float(coords[0]), float(coords[1]); 
            apply_gps = self.cb_gps.isChecked()
        except: lat, lon, apply_gps = DEFAULT_LAT, DEFAULT_LON, False
        
        payload = {
            'apply_gps': apply_gps, 'lat': lat, 'lon': lon,
            'apply_date': self.cb_date.isChecked(),
            'offset_h': self.offset_input.value(), 
            'date_val': self.dt_picker.dateTime().toString("yyyy:MM:dd HH:mm:ss")
        }
        
        self.btn_run.setEnabled(False)
        self.worker = ImageUpdater(files, payload)
        self.worker.progress.connect(self.p_bar.setValue)
        self.worker.status.connect(self.st_lbl.setText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()        

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EXIFeditorApp(); window.show()
    sys.exit(app.exec())