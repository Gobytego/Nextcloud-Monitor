# Gobytego Nextcloud Monitor
<br>The Nextcloud Monitor is a lightweight, multi-server desktop application built with Python and PyQt6. It provides a real-time, tabbed dashboard for checking the health and performance metrics of your Nextcloud instance(s).

<br>Key Features
<br>Real-time Monitoring: Get live metrics on CPU load, RAM usage, storage, and activity.

<br>Multi-Server Support: Easily switch between different configured Nextcloud instances.

<br>Theming & UX: Includes Light and Dark themes, and an adjustable data refresh rate.

<br>Detailed Views: Separate tabs for System Health, Storage Overview, and Raw Data (for debugging).

<br>Quick Setup
<br>To run the monitor, follow these three steps. You must have Python 3.x installed.

<br>1. Install Libraries
<br>Install the necessary Python packages using pip:

<br>pip install requests PyQt6

<br>2. Create Configuration File

<br>First on the server you will need to make a serverinfo token

<br>  Most installs: 
<br>sudo -E -u www-data php occ config:app:set serverinfo token --value f8g4b5n2m1j6h7d2 <---obviously change this to your own password/passphrase

<br>  snap install: 
<br>nextcloud.occ config:app:set serverinfo token --value f8g4b5n2m1j6h7d2 <---obviously change this to your own password/passphrase

<br> if you need a super secure passphrase you can use [gobytego passphrase generator](https://gobytego.com/pass.html)

<br>Create a plain text file named ncmonitor.txt in the application's folder. This file must contain your Nextcloud Base URL and your NC-Token on separate lines:

<br>Example

<br>https://my-private-cloud.org
<br>f8g4b5n2m1j6h7d2

<br>if you have multiple servers you can make multiple files: ncmonitor.server1.txt, ncmonitor_server2.txt, etc. just has to start with "ncmonitor" and end in ".txt"

<br>3. Run the Monitor
<br>Execute the Python script directly, or run the provided Windows executable:

<br>python ncmonitor_qt.py

