import requests
import json
import sys
import math
import time
import datetime
import os
import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, 
    QGridLayout, QLabel, QListWidget, QListWidgetItem, QDialog, 
    QPushButton, QHBoxLayout, QStatusBar, QMessageBox, QTextEdit, 
    QMenuBar, QMenu, QSpinBox, QFormLayout
)
from PyQt6.QtCore import (
    QObject, QThread, pyqtSignal, QTimer, Qt, QRunnable, QThreadPool
)
from PyQt6.QtGui import QFont, QIcon

# ==============================================================================
# CONFIGURATION CONSTANTS
# ==============================================================================
# Base filename pattern for configuration files: ncmonitor.txt, ncmonitor_1.txt, etc.
CONFIG_FILE_PATTERN = re.compile(r"ncmonitor(?:[_\w]+)?\.txt$") 
# API endpoint for server info
API_SUFFIX = "/ocs/v2.php/apps/serverinfo/api/v1/info?format=json"
# Default time in milliseconds for GUI auto-refresh (60000ms = 1 minute)
DEFAULT_REFRESH_INTERVAL_MS = 60000 
# Multiplier to convert Kilobytes (KB) from the API response to Bytes
KB_TO_BYTES = 1024 
# ==============================================================================

# ==============================================================================
# THEME STYLESHEETS (QSS)
# ==============================================================================
DARK_THEME_QSS = """
    /* Main Window and Background */
    QMainWindow, QWidget, QDialog {
        background-color: #2e2e2e;
        color: #ffffff;
    }
    /* Tabs */
    QTabWidget {
        background-color: #2e2e2e;
    }
    QTabWidget::pane { 
        border: 1px solid #444; 
    }
    QTabBar::tab {
        background: #3c3c3c;
        color: #ddd;
        padding: 8px 15px;
        border: 1px solid #444;
        border-bottom: none;
    }
    QTabBar::tab:selected {
        background: #2e2e2e;
        color: #fff;
        border-top: 2px solid #5a5a5a;
        font-weight: bold;
    }
    /* Labels and Headers (default white text) */
    QLabel {
        color: #ffffff;
    }
    /* Metric Values (using objectName selector defined in add_metric_pair) */
    QLabel[objectName^="val"] {
        color: #90ee90; /* Light green for values */
        font-weight: bold;
    }
    /* Text Editors (for App List and Raw Data) */
    QTextEdit {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #555;
    }
    /* Buttons */
    QPushButton {
        background-color: #555;
        border: 1px solid #666;
        color: #ffffff;
        padding: 5px 10px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #666;
    }
    /* List Widget (Server Selection Dialog) */
    QListWidget {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #555;
    }
    QListWidget::item:selected {
        background-color: #5a5a5a;
    }
    /* Menu Bar */
    QMenuBar {
        background-color: #3c3c3c;
        color: #ffffff;
    }
    QMenu {
        background-color: #3c3c3c;
        color: #ffffff;
        border: 1px solid #555;
    }
    QMenu::item:selected {
        background-color: #5a5a5a;
    }
    /* Spin Box used in config dialogs */
    QSpinBox {
        background-color: #444;
        color: #ffffff;
        border: 1px solid #555;
        padding: 2px;
    }
"""

# Empty string means use the default system theme (usually light)
LIGHT_THEME_QSS = """
    /* Explicitly override the header style to black for light theme visibility */
    QLabel[class="header"] {
        color: #333; 
    }
"""
# ==============================================================================


# ==============================================================================
# UTILITY FUNCTIONS 
# ==============================================================================

def safe_int(value):
    """Converts a value to an integer, defaulting to 0 if conversion fails."""
    if value is None or value == '':
        return 0
    try:
        # Use float conversion first to handle API responses like "123.0"
        return int(float(value)) 
    except (ValueError, TypeError):
        return 0

def format_timedelta(seconds):
    """Converts a duration in seconds into a human-readable string."""
    seconds = safe_int(seconds)
    if seconds <= 0:
        return "N/A or Fresh Start"
    
    intervals = (
        ('years', 31536000), ('days', 86400),
        ('hours', 3600), ('minutes', 60),
    )
    
    result = []
    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            result.append(f"{value} {name}" if value > 1 else f"{value} {name.rstrip('s')}")
            
    if not result and seconds > 0:
        return f"{seconds} seconds"

    return ", ".join(result[:3]) or "Just started"


def read_config_file(config_filepath):
    """Reads the configuration (URL and Token) from the specified text file."""
    try:
        with open(config_filepath, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        if len(lines) < 2:
            raise ValueError("Configuration file requires at least two lines: URL and Token.")
        
        nc_url = lines[0]
        nc_token = lines[1]
        
        if not nc_url.startswith('http'):
             raise ValueError("The URL (first line) in the file appears invalid. Must start with http:// or https://")

        return nc_url, nc_token

    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: '{config_filepath}'.")
    except Exception as e:
        raise Exception(f"Failed to parse configuration file: {e}")


def find_and_load_configs(script_dir):
    """Scans the directory for ncmonitor*.txt files and loads the URL/Token from each."""
    config_list = []
    for filename in os.listdir(script_dir):
        if CONFIG_FILE_PATTERN.match(filename):
            full_path = os.path.join(script_dir, filename)
            try:
                nc_url, nc_token = read_config_file(full_path)
                
                name = nc_url.split('//')[-1].rstrip('/')
                name_prefix = filename.replace('.txt', '')
                
                config_list.append({
                    'name': f"[{name_prefix}] {name}",
                    'url': nc_url,
                    'token': nc_token,
                    'path': full_path
                })
            except Exception as e:
                print(f"Warning: Skipping invalid config file {filename}. Error: {e}")
                continue
                
    return config_list


def format_bytes(bytes_value, decimals=2):
    """Converts a number of bytes into a human-readable string (e.g., KB, MB, GB, TB)."""
    bytes_value = safe_int(bytes_value)

    if bytes_value == 0:
        return '0 Bytes'
    
    k = 1024
    dm = decimals if decimals >= 0 else 0
    sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    
    i = 0
    if bytes_value > 0:
        i = math.floor(math.log(bytes_value, k))
        i = min(i, len(sizes) - 1)
        
    return f"{bytes_value / (k ** i):.{dm}f} {sizes[i]}"


def fetch_metrics(nc_url, nc_token):
    """Fetches Nextcloud server metrics and returns the data dictionary."""
    api_url = nc_url.rstrip('/') + API_SUFFIX
    headers = {
        'NC-Token': nc_token,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        response.raise_for_status() 
        
        data = response.json()
        
        meta = data.get('ocs', {}).get('meta', {})
        if meta.get('status') != 'ok':
            raise Exception(f"API Status Error: {meta.get('message', 'Unknown error')}")

        return data

    except requests.exceptions.HTTPError as err:
        raise Exception(f"HTTP Error: {err}. Check URL/Token.")
    except requests.exceptions.ConnectionError as err:
        raise Exception(f"Connection Error: {err}. Server unreachable.")
    except requests.exceptions.Timeout:
        raise Exception("Request timed out after 15 seconds.")
    except Exception as err:
        # Wrap any unexpected error for consistency
        raise Exception(f"An unexpected error occurred: {err}")

# ==============================================================================
# PYQT6 THREADING AND WORKER CLASSES
# ==============================================================================

class NextcloudWorker(QRunnable):
    """A QRunnable task to fetch data in a separate thread from the QThreadPool."""
    def __init__(self, nc_url, nc_token, signals):
        super().__init__()
        self.nc_url = nc_url
        self.nc_token = nc_token
        self.signals = signals

    def run(self):
        """Fetches data and emits the results or an error."""
        try:
            data = fetch_metrics(self.nc_url, self.nc_token)
            self.signals.data_fetched.emit(data)
        except Exception as e:
            self.signals.error.emit(str(e))


class WorkerSignals(QObject):
    """Defines the signals available from a running worker thread."""
    data_fetched = pyqtSignal(dict) # Data dictionary emitted upon success
    error = pyqtSignal(str)         # Error message emitted upon failure


# ==============================================================================
# PYQT6 DIALOGS
# ==============================================================================

class ServerSelectionDialog(QDialog):
    """A modal dialog for selecting one of the available server configurations."""
    def __init__(self, parent, configs, current_config):
        super().__init__(parent)
        self.setWindowTitle("Select Nextcloud Server")
        self.configs = configs
        self.selected_config = None
        
        self.setModal(True)
        self.setGeometry(100, 100, 450, 400)

        main_layout = QVBoxLayout(self)

        header_label = QLabel("Available Server Configurations:")
        header_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        main_layout.addWidget(header_label)
        
        current_label = QLabel(f"Currently active: <b>{current_config['name']}</b>")
        main_layout.addWidget(current_label)

        # List Widget
        self.list_widget = QListWidget()
        main_layout.addWidget(self.list_widget)
        
        initial_selection_index = 0
        
        for idx, config in enumerate(self.configs):
            item = QListWidgetItem(config['name'])
            self.list_widget.addItem(item)
            if config['name'] == current_config['name']:
                initial_selection_index = idx

        if self.configs:
            self.list_widget.setCurrentRow(initial_selection_index)

        # Buttons
        button_layout = QHBoxLayout()
        select_button = QPushButton("Switch Server")
        select_button.clicked.connect(self.accept_selection)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(select_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)

    def accept_selection(self):
        """Handles selection and sets the result."""
        selected_row = self.list_widget.currentRow()
        if selected_row >= 0:
            self.selected_config = self.configs[selected_row]
            self.accept()
        else:
            QMessageBox.warning(self, "Selection Required", "Please select a server from the list.")

    def get_selected_config(self):
        return self.selected_config


class RefreshIntervalDialog(QDialog):
    """A modal dialog for setting the data refresh interval in seconds."""
    def __init__(self, parent, current_interval_ms):
        super().__init__(parent)
        self.setWindowTitle("Set Refresh Interval")
        self.current_interval_ms = current_interval_ms
        self.new_interval_ms = current_interval_ms
        
        self.setModal(True)
        self.setFixedWidth(300)

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Spin Box for Interval (in seconds)
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(10, 3600)  # Min 10s, Max 1 hour
        self.interval_spinbox.setSuffix(" seconds")
        
        # Set current value (convert ms to seconds)
        initial_seconds = self.current_interval_ms // 1000
        self.interval_spinbox.setValue(initial_seconds)
        
        form_layout.addRow("Auto-Refresh Rate:", self.interval_spinbox)
        main_layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Apply")
        save_button.clicked.connect(self.accept_selection)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)
        
        # Add a short instruction label
        instruction_label = QLabel(
            f"Current Interval: <b>{initial_seconds}s</b><br>Minimum: 10s, Maximum: 3600s."
        )
        instruction_label.setStyleSheet("padding-top: 5px;")
        main_layout.addWidget(instruction_label)

    def accept_selection(self):
        """Calculates the new interval in milliseconds and accepts."""
        new_seconds = self.interval_spinbox.value()
        self.new_interval_ms = new_seconds * 1000
        self.accept()

    def get_new_interval(self):
        return self.new_interval_ms


# ==============================================================================
# PYQT6 MAIN APPLICATION
# ==============================================================================

class NextcloudMonitorApp(QMainWindow):
    """Main application window for the Nextcloud Monitor GUI using PyQt6."""
    
    def __init__(self, initial_config, all_configs): 
        super().__init__()
        
        self.server_configs = all_configs
        self.current_config = initial_config 
        self.metric_labels = {} # Stores QLabel references for dynamic updating
        self.app_list_text = QTextEdit()
        self.raw_data_text = QTextEdit()
        self.thread_pool = QThreadPool()
        self.refresh_timer = QTimer(self)
        self.is_dark_theme = False # New state for theme (False = Light, True = Dark)
        self.theme_toggle_action = None # Will be set in create_menu_bar
        
        # Customizable refresh interval
        self.refresh_interval_ms = DEFAULT_REFRESH_INTERVAL_MS
        
        self.setWindowTitle(f"Gobytego Nextcloud Monitor: {initial_config['url']}")
        self.setGeometry(100, 100, 702, 550)
        
        self.init_ui()
        
        # Apply the initial theme (Light by default)
        self.apply_theme(self.is_dark_theme)
        
        # Apply the initial configuration and start the refresh loop
        self.apply_new_config(initial_config)
        

    def init_ui(self):
        """Initializes the main window structure, menu bar, and tabs."""
        
        # Central Widget and Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 1. Menu Bar
        self.create_menu_bar()

        # 2. Header
        header_label = QLabel("Gobytego Nextcloud Metrics Dashboard")
        header_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header_label)

        # 3. Tab Widget
        self.tabs = QTabWidget()
        self.create_tabs()
        main_layout.addWidget(self.tabs)
        
        # 4. Buttons (Manual Refresh)
        button_frame = QWidget()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        refresh_button = QPushButton("Manual Refresh")
        refresh_button.clicked.connect(self.start_fetch)
        
        button_layout.addWidget(refresh_button)
        main_layout.addWidget(button_frame)

        # 5. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Add permanent credit label to the right side of the status bar
        self.credit_label = QLabel("Made by Adam of Gobytego")
        self.credit_label.setStyleSheet("color: #777; padding-right: 10px;") 
        self.status_bar.addPermanentWidget(self.credit_label)

        self.status_bar.showMessage("Initializing monitor...")
        
        # Connect the timer
        self.refresh_timer.timeout.connect(self.start_fetch)

    def create_menu_bar(self):
        """Sets up the menu bar for configuration actions, including the theme and refresh rate toggle."""
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        config_menu = menu_bar.addMenu("Configuration")
        
        # Server Config Action
        change_server_action = config_menu.addAction("Change Server Config")
        change_server_action.triggered.connect(self.select_new_config_dialog)
        
        # Refresh Rate Action (NEW)
        refresh_rate_action = config_menu.addAction("Set Refresh Rate")
        refresh_rate_action.triggered.connect(self.set_refresh_interval_dialog)

        config_menu.addSeparator() 

        # Theme Toggle Action
        self.theme_toggle_action = config_menu.addAction("Switch to Dark Theme") # Initial text (assuming light is default)
        self.theme_toggle_action.triggered.connect(self.toggle_theme)

        config_menu.addSeparator() 
        
        exit_action = config_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)


    def create_tabs(self):
        """Creates and populates the tab widgets."""
        self.tabs.addTab(self.create_core_metrics_tab(), "Core Metrics")
        self.tabs.addTab(self.create_system_health_tab(), "System Health")
        self.tabs.addTab(self.create_activity_security_tab(), "Activity && Security")
        self.tabs.addTab(self.create_storage_overview_tab(), "Storage")
        self.tabs.addTab(self.create_config_details_tab(), "System Config")
        self.tabs.addTab(self.create_raw_data_tab(), "Raw Data")

    def create_tab_content(self, title):
        """Helper to create a standard tab layout."""
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.setColumnStretch(1, 1) # Make the value column stretch
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        return tab, layout

    def add_metric_pair(self, layout, label_text, var_name, row=None, is_header=False):
        """Helper to create a label-value pair in a grid layout."""
        if row is None:
            # Determine the current row count based on the number of items in column 0
            row = layout.rowCount() 

        # Metric Label (Left)
        label = QLabel(label_text)
        if is_header:
            label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            # Set a class for the header label for theme specific styling
            label.setObjectName("header") 
            # Original explicit style removed to allow QSS to control the color
            label.setStyleSheet("margin-top: 10px; margin-bottom: 5px;") 
            layout.addWidget(label, row, 0, 1, 2) # Span two columns
        else:
            # Value Label (Right)
            value_label = QLabel("N/A")
            value_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            value_label.setObjectName(var_name) # Used to find the label later and for theme QSS
            self.metric_labels[var_name] = value_label
            
            layout.addWidget(label, row, 0)
            layout.addWidget(value_label, row, 1, alignment=Qt.AlignmentFlag.AlignRight)
        
        return row

    def create_core_metrics_tab(self):
        tab, layout = self.create_tab_content("Core Metrics")
        self.add_metric_pair(layout, "Nextcloud Version:", "version_val")
        self.add_metric_pair(layout, "PHP Service Uptime:", "php_uptime_val")
        self.add_metric_pair(layout, "Total Users:", "users_val")
        self.add_metric_pair(layout, "Total Files:", "files_val")
        self.add_metric_pair(layout, "Web Server:", "webserver_val")
        self.add_metric_pair(layout, "CPU Core Count:", "cpunum_val")
        return tab

    def create_activity_security_tab(self):
        tab, layout = self.create_tab_content("Activity & Security")
        self.add_metric_pair(layout, "Active (5 min):", "active5m_val")
        self.add_metric_pair(layout, "Active (1 hour):", "active1h_val")
        self.add_metric_pair(layout, "Active (24 hours):", "active24h_val")

        self.add_metric_pair(layout, "SECURITY & STATUS", "", is_header=True)
        self.add_metric_pair(layout, "Failed Login Attempts:", "failed_logins_val")
        self.add_metric_pair(layout, "Maintenance Mode:", "maintenance_val")

        self.add_metric_pair(layout, "SHARING OVERVIEW", "", is_header=True)
        self.add_metric_pair(layout, "Total Shares:", "total_shares_val")
        self.add_metric_pair(layout, "Local Shares:", "local_shares_val")
        self.add_metric_pair(layout, "Federated Shares:", "federated_shares_val")
        self.add_metric_pair(layout, "Public Link Shares:", "public_shares_val")
        return tab

    def create_system_health_tab(self):
        tab, layout = self.create_tab_content("System Health")
        # RAM/SWAP (FIXED: These now show in GB/MB thanks to KB_TO_BYTES correction)
        self.add_metric_pair(layout, "RAM Used:", "ram_used_val")
        self.add_metric_pair(layout, "RAM Total:", "ram_total_val")
        self.add_metric_pair(layout, "Swap Used:", "swap_used_val")
        
        self.add_metric_pair(layout, "CPU LOAD", "", is_header=True)
        self.add_metric_pair(layout, "CPU Load (1m):", "cpu1m_val")
        self.add_metric_pair(layout, "CPU Load (5m):", "cpu5m_val")
        self.add_metric_pair(layout, "CPU Load (15m):", "cpu15m_val")
        
        self.add_metric_pair(layout, "PHP OPCACHE PERFORMANCE", "", is_header=True)
        self.add_metric_pair(layout, "Opcache Hit Rate:", "opcache_hit_rate_val")
        self.add_metric_pair(layout, "Opcache Used Memory:", "opcache_used_val")
        self.add_metric_pair(layout, "Opcache Wasted Memory:", "opcache_wasted_val")
        return tab

    def create_storage_overview_tab(self):
        tab, layout = self.create_tab_content("Storage")
        self.add_metric_pair(layout, "Total Storage Used:", "storage_used_val")
        self.add_metric_pair(layout, "Total Storage Free:", "storage_free_val")
        self.add_metric_pair(layout, "Database Size:", "db_size_val")
        
        self.add_metric_pair(layout, "APP SUMMARY", "", is_header=True)
        self.add_metric_pair(layout, "Enabled Apps:", "enabled_apps_val")
        self.add_metric_pair(layout, "Total Apps Installed:", "app_count_val")
        return tab

    def create_config_details_tab(self):
        tab, layout = self.create_tab_content("System Config")
        
        self.add_metric_pair(layout, "PHP CONFIGURATION", "", is_header=True)
        self.add_metric_pair(layout, "PHP Version:", "php_val")
        # PHP Memory Limit is correctly shown in MB/GB
        self.add_metric_pair(layout, "PHP Memory Limit:", "php_memory_limit_val") 
        self.add_metric_pair(layout, "PHP Max Execution Time:", "php_max_exec_val")
        
        self.add_metric_pair(layout, "DATABASE DETAILS", "", is_header=True)
        self.add_metric_pair(layout, "DB Type:", "db_type_val")
        self.add_metric_pair(layout, "DB Version:", "db_version_val")
        self.add_metric_pair(layout, "DB Host:", "db_host_val")
        
        # Enabled Apps List (QTextEdit)
        self.add_metric_pair(layout, "ENABLED APPS LIST", "", is_header=True)
        
        # Add QTextEdit for scrollable list
        row = layout.rowCount()
        self.app_list_text.setReadOnly(True)
        self.app_list_text.setText("Apps list loading...")
        self.app_list_text.setFont(QFont("Segoe UI", 9))
        
        layout.addWidget(self.app_list_text, row, 0, 1, 2)
        layout.setRowStretch(row, 1) # Allow the text widget to take up space
        
        return tab

    def create_raw_data_tab(self):
        tab, layout = self.create_tab_content("Raw Data (Debug)")
        
        header_label = QLabel("Raw JSON Response (Used for Debugging)")
        header_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(header_label, 0, 0, 1, 2)
        
        self.raw_data_text.setReadOnly(True)
        self.raw_data_text.setFont(QFont("Courier", 8))
        self.raw_data_text.setText("Fetching raw data...")
        
        layout.addWidget(self.raw_data_text, 1, 0, 1, 2)
        layout.setRowStretch(1, 1)
        
        return tab
    
    def apply_theme(self, is_dark):
        """Applies the dark or light theme stylesheet to the entire application,
           blocking signals temporarily to prevent window resize shifts."""
        self.is_dark_theme = is_dark
        theme_qss = DARK_THEME_QSS if is_dark else LIGHT_THEME_QSS
        
        # Apply the stylesheet to the singleton QApplication instance
        app_instance = QApplication.instance()
        if app_instance:
            # 1. Block signals to prevent resize/layout events during style change
            app_instance.blockSignals(True)
            
            app_instance.setStyleSheet(theme_qss)
            
            # 2. Re-enable signals
            app_instance.blockSignals(False)
        
        # Update the toggle action text
        if self.theme_toggle_action:
            new_text = "Switch to Light Theme" if is_dark else "Switch to Dark Theme"
            self.theme_toggle_action.setText(new_text)

    def toggle_theme(self):
        """Switches the theme between dark and light."""
        self.apply_theme(not self.is_dark_theme)

    def apply_new_config(self, config_object):
        """Updates the app's configuration and restarts monitoring."""
        self.current_config = config_object
        self.nc_url = config_object['url']
        self.nc_token = config_object['token']
        
        self.setWindowTitle(f"Gobytego Nextcloud Monitor: {self.nc_url}")
        
        # Reset all metrics to N/A while fetching
        for label in self.metric_labels.values():
            label.setText("N/A")
            
        self.app_list_text.setText("Apps list loading...")
        self.raw_data_text.setText("Fetching raw data...")

        self.update_status(f"Monitoring server: {self.nc_url}...", "blue")
        
        # Start or restart the refresh timer
        self.refresh_timer.stop()
        self.refresh_timer.start(self.refresh_interval_ms)
        
        # Immediately start the fetch operation
        self.start_fetch()

    def set_refresh_interval_dialog(self):
        """Opens a dialog to set the new refresh interval."""
        dialog = RefreshIntervalDialog(self, self.refresh_interval_ms)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_interval_ms = dialog.get_new_interval()
            if new_interval_ms != self.refresh_interval_ms:
                self.refresh_interval_ms = new_interval_ms
                self.refresh_timer.stop()
                self.refresh_timer.start(self.refresh_interval_ms)
                
                new_interval_sec = self.refresh_interval_ms // 1000
                self.update_status(f"Refresh rate set to {new_interval_sec} seconds. Fetching now...", "orange")
                self.start_fetch() # Immediate refresh after changing interval


    def select_new_config_dialog(self):
        """Opens the selection dialog."""
        dialog = ServerSelectionDialog(self, self.server_configs, self.current_config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_config = dialog.get_selected_config()
            if new_config:
                self.apply_new_config(new_config)


    def start_fetch(self):
        """Initializes the worker thread to fetch metrics."""
        # Calculate next refresh time for status bar
        next_refresh_time = datetime.datetime.now() + datetime.timedelta(milliseconds=self.refresh_interval_ms)
        status_msg = f"Fetching new data... Next refresh at {next_refresh_time.strftime('%H:%M:%S')}."
        self.update_status(status_msg, "blue")

        # Create signals object
        signals = WorkerSignals()
        signals.data_fetched.connect(self.update_gui_metrics)
        signals.error.connect(self.handle_fetch_error)

        # Create worker and run it in the thread pool
        worker = NextcloudWorker(self.nc_url, self.nc_token, signals)
        self.thread_pool.start(worker)

    def handle_fetch_error(self, error_message):
        """Handles errors from the worker thread."""
        self.raw_data_text.setText(f"ERROR: Could not fetch data. Check your URL/Token.\n\n{error_message}")
        self.update_status(f"Error: {error_message}", "red")

    def update_status(self, message, color="black"):
        """Updates the status bar message and color."""
        style = f"color: {color}; font-weight: bold;"
        self.status_bar.setStyleSheet(style)
        self.status_bar.showMessage(message)

    def update_gui_metrics(self, data):
        """Processes the fetched data and updates the GUI labels."""
        try:
            # Update Raw Data Tab first
            self.raw_data_text.setText(json.dumps(data, indent=2))
            
            # --- Extract Data ---
            nc_data = data['ocs']['data']['nextcloud']
            server_data = data['ocs']['data']['server']
            active_users = data['ocs']['data']['activeUsers']
            system_info = nc_data.get('system', {})
            db_info = server_data.get('database', {})
            php_info = server_data.get('php', {})
            storage_data = nc_data.get('storage', {})
            shares = nc_data.get('shares', {})
            opcache_stats = php_info.get('opcache', {}).get('opcache_statistics', {})
            opcache_memory = php_info.get('opcache', {}).get('memory_usage', {})

            # --- System Health Metrics (with KB to Bytes correction) ---
            ram_total_kb = safe_int(system_info.get('mem_total', 0))
            ram_free_kb = safe_int(system_info.get('mem_free', 0))
            ram_total = ram_total_kb * KB_TO_BYTES
            ram_used = (ram_total_kb - ram_free_kb) * KB_TO_BYTES
            
            swap_total_kb = safe_int(system_info.get('swap_total', 0))
            swap_free_kb = safe_int(system_info.get('swap_free', 0))
            swap_total = swap_total_kb * KB_TO_BYTES
            swap_used = (swap_total_kb - swap_free_kb) * KB_TO_BYTES
            
            cpuload_data = system_info.get('cpuload', [0, 0, 0])
            cpu_load = [cpuload_data[i] if len(cpuload_data) > i else 0 for i in range(3)]
            
            opcache_hit_rate = opcache_stats.get('opcache_hit_rate', 0.0)
            opcache_used_memory = opcache_memory.get('used_memory', 0)
            wasted_memory = opcache_memory.get('wasted_memory', 0)

            # PHP Uptime calculation
            start_time_ts = safe_int(opcache_stats.get('start_time', 0))
            current_time_ts = int(time.time())
            uptime_seconds = current_time_ts - start_time_ts if start_time_ts > 0 and current_time_ts > start_time_ts else 0
            uptime_display = format_timedelta(uptime_seconds)

            # Storage Overview (Fallback logic retained)
            storage_free = safe_int(storage_data.get('free'))
            storage_used = safe_int(storage_data.get('used'))
            if storage_used == 0 and storage_free == 0:
                storage_free = safe_int(system_info.get('freespace'))
                storage_used_display = "0 Bytes (Data Missing)"
                storage_free_display = f"{format_bytes(storage_free)} (System Freespace)"
            else:
                storage_used_display = format_bytes(storage_used)
                storage_free_display = format_bytes(storage_free)

            # --- FIX: Ensure App List Content is always a string ---
            app_data = data['ocs']['data'].get('app', None)
            enabled_app_lines_str = "APP DATA IS MISSING FROM NEXTCLOUD API RESPONSE."
            enabled_app_count = "N/A (Data Missing)"
            total_app_count = "N/A (Data Missing)"

            if app_data and isinstance(app_data, dict):
                enabled_apps = app_data.get('enabled', [])
                installed_apps = app_data.get('installed', [])

                if isinstance(enabled_apps, list) and isinstance(installed_apps, list):
                    temp_lines = []
                    for app in enabled_apps:
                        if isinstance(app, dict):
                            app_name = app.get('id', 'Unknown App')
                            app_version = app.get('version', 'N/A')
                            temp_lines.append(f"{app_name}: v{app_version}")
                        elif isinstance(app, str):
                            temp_lines.append(f"{app}: vN/A")
                    
                    enabled_app_count = len(enabled_apps)
                    total_app_count = len(installed_apps)
                    # This joins the list of strings into one single string with newlines
                    enabled_app_lines_str = "\n".join(sorted(temp_lines))
                # If lists are not lists, the default string message is kept

            # --- Update UI Labels ---
            updates = {
                # Core Metrics
                'version_val': system_info.get('version', 'N/A'),
                'php_uptime_val': uptime_display,
                'users_val': str(storage_data.get('num_users', 0)),
                'files_val': f"{storage_data.get('num_files', 0):,}",
                'webserver_val': server_data.get('webserver', 'N/A'),
                'cpunum_val': system_info.get('cpunum', 'N/A'),

                # Activity & Security
                'active5m_val': str(active_users.get('last5minutes', 0)),
                'active1h_val': str(active_users.get('last1hour', 0)),
                'active24h_val': str(active_users.get('last24hours', 0)),
                'maintenance_val': 'Yes' if system_info.get('maintenance', False) else 'No',
                'failed_logins_val': str(system_info.get('failing_login_attempts', 0)),
                'total_shares_val': str(shares.get('num_shares', 0)),
                'local_shares_val': str(shares.get('num_shares_user', 0)),
                'federated_shares_val': str(shares.get('num_fed_shares_sent', 0)),
                'public_shares_val': str(shares.get('num_shares_link', 0)),
                
                # System Health (Fixed Units)
                'ram_used_val': format_bytes(ram_used),
                'ram_total_val': format_bytes(ram_total),
                'swap_used_val': format_bytes(swap_used),
                'cpu1m_val': f"{cpu_load[0]:.2f}",
                'cpu5m_val': f"{cpu_load[1]:.2f}",
                'cpu15m_val': f"{cpu_load[2]:.2f}",
                'opcache_hit_rate_val': f"{opcache_hit_rate:.2f}%",
                'opcache_used_val': format_bytes(opcache_used_memory),
                'opcache_wasted_val': format_bytes(wasted_memory),

                # Storage Overview
                'storage_used_val': storage_used_display,
                'storage_free_val': storage_free_display,
                'db_size_val': format_bytes(safe_int(db_info.get('size'))),
                # Use the processed count variables
                'enabled_apps_val': str(enabled_app_count),
                'app_count_val': str(total_app_count),
                
                # Configuration
                'php_val': php_info.get('version', 'N/A'),
                'php_memory_limit_val': format_bytes(php_info.get('memory_limit', 0)),
                'php_max_exec_val': f"{php_info.get('max_execution_time', 'N/A')}s",
                'db_type_val': db_info.get('type', 'N/A'),
                'db_version_val': db_info.get('version', 'N/A'),
                'db_host_val': db_info.get('host', 'N/A'),
            }

            for key, value in updates.items():
                if key in self.metric_labels:
                    self.metric_labels[key].setText(str(value))

            # Update the QTextEdit for the enabled apps list (Now guaranteed to be a string)
            self.app_list_text.setText(enabled_app_lines_str)
            
            # Update status with next refresh time
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            next_refresh_time = datetime.datetime.now() + datetime.timedelta(milliseconds=self.refresh_interval_ms)
            status_msg = (
                f"Last updated: {current_time}. "
                f"Next check at {next_refresh_time.strftime('%H:%M:%S')} "
                f"({self.refresh_interval_ms // 1000}s interval)."
            )
            self.update_status(status_msg, "green")

        except Exception as e:
            # Added a more detailed message in case of data processing failure
            error_msg = f"Failed to process fetched data: {type(e).__name__}: {e}"
            QMessageBox.critical(self, "Data Processing Error", error_msg)
            self.update_status("Error processing data", "red")


if __name__ == "__main__":
    
    # --- STEP 1: LOAD ALL CONFIGURATIONS ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    all_configs = find_and_load_configs(script_dir)

    if not all_configs:
        print("\n--- FATAL ERROR: CONFIGURATION REQUIRED ---")
        print("No valid configuration files found matching 'ncmonitor*.txt' in the script directory.")
        print("\nACTION REQUIRED: Please create a file named 'ncmonitor.txt' (or similar) with:")
        print("Line 1: Nextcloud Base URL (e.g., https://cloud.example.com)")
        print("Line 2: NC-Token")
        sys.exit(1)
        
    INITIAL_CONFIG = all_configs[0]

    # --- STEP 2: RUN PYQT GUI ---
    app = QApplication(sys.argv)
    
    # Optional: Set a nice icon (Qt needs a proper path, but we'll skip the actual file check for portability)
    ICON_FILE_PATH = os.path.join(script_dir, "gbgicon.png") 
    if os.path.exists(ICON_FILE_PATH):
        app.setWindowIcon(QIcon(ICON_FILE_PATH))

    window = NextcloudMonitorApp(INITIAL_CONFIG, all_configs) 
    window.show()
    sys.exit(app.exec())
