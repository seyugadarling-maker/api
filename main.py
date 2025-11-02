import os
import json
import subprocess
import threading
import time
import requests
from flask import Flask, render_template, request, jsonify
from pathlib import Path

app = Flask(__name__)

# Configuration
SERVER_DIR = Path("server")
JAR_FILE = SERVER_DIR / "fabric-server.jar"
SERVER_PROPERTIES = SERVER_DIR / "server.properties"
EULA_FILE = SERVER_DIR / "eula.txt"
FABRIC_DOWNLOAD_URL = "https://meta.fabricmc.net/v2/versions/loader/1.21/0.16.0/1.1.0/server/jar"

# Global variables to track server state
server_process = None
server_thread = None
current_config = {}

class MinecraftServer:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.port = 25565  # Default Minecraft port
    
    def download_server(self):
        """Download the Fabric server JAR"""
        try:
            SERVER_DIR.mkdir(exist_ok=True)
            
            if not JAR_FILE.exists():
                print("Downloading Fabric server...")
                response = requests.get(FABRIC_DOWNLOAD_URL, stream=True)
                response.raise_for_status()
                
                with open(JAR_FILE, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print("Download completed!")
            
            return True
        except Exception as e:
            print(f"Download failed: {e}")
            return False
    
    def generate_server_files(self, config):
        """Generate server.properties and other necessary files"""
        try:
            # First run to generate basic files
            if not (SERVER_DIR / "world").exists():
                print("Generating server files...")
                subprocess.run(
                    ["java", "-jar", str(JAR_FILE), "nogui"],
                    cwd=SERVER_DIR,
                    timeout=30,
                    capture_output=True
                )
            
            # Accept EULA
            with open(EULA_FILE, 'w') as f:
                f.write("eula=true\n")
            
            # Update server.properties with custom configuration
            properties = {
                'motd': config.get('motd', 'A Minecraft Server'),
                'gamemode': config.get('gamemode', 'survival'),
                'difficulty': config.get('difficulty', 'easy'),
                'max-players': str(config.get('max_players', 20)),
                'server-port': str(config.get('port', 25565)),
                'online-mode': 'false',
                'enable-command-block': 'true',
                'spawn-protection': '0'
            }
            
            with open(SERVER_PROPERTIES, 'w') as f:
                for key, value in properties.items():
                    f.write(f"{key}={value}\n")
            
            return True
        except Exception as e:
            print(f"File generation failed: {e}")
            return False
    
    def start(self, config):
        """Start the Minecraft server"""
        try:
            self.port = config.get('port', 25565)
            
            # Download server if needed
            if not self.download_server():
                return False
            
            # Generate configuration files
            if not self.generate_server_files(config):
                return False
            
            # Start the server
            print("Starting Minecraft server...")
            self.process = subprocess.Popen(
                ["java", "-Xmx2G", "-Xms1G", "-jar", str(JAR_FILE), "nogui"],
                cwd=SERVER_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            self.is_running = True
            print(f"Minecraft server started on port {self.port}")
            
            # Monitor server output
            def monitor_output():
                while self.process and self.process.poll() is None:
                    try:
                        output = self.process.stdout.readline()
                        if output:
                            print(f"[MC Server] {output.strip()}")
                    except:
                        break
            
            threading.Thread(target=monitor_output, daemon=True).start()
            return True
            
        except Exception as e:
            print(f"Server start failed: {e}")
            return False
    
    def stop(self):
        """Stop the Minecraft server"""
        try:
            if self.process:
                # Send stop command to the server
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
                
                # Wait for process to terminate
                self.process.wait(timeout=30)
                self.process = None
            
            self.is_running = False
            print("Minecraft server stopped")
            return True
        except Exception as e:
            print(f"Server stop failed: {e}")
            # Force kill if graceful stop fails
            if self.process:
                self.process.terminate()
            return False

# Global server instance
mc_server = MinecraftServer()

@app.route('/')
def index():
    """Serve the main control page"""
    return render_template('index.html')

@app.route('/start-server', methods=['POST'])
def start_server():
    """Start the Minecraft server with custom configuration"""
    global current_config
    
    try:
        config = request.json
        current_config = {
            'motd': config.get('motd', 'A Minecraft Server'),
            'gamemode': config.get('gamemode', 'survival'),
            'difficulty': config.get('difficulty', 'easy'),
            'max_players': config.get('maxPlayers', 20),
            'port': 25565  # Standard Minecraft port
        }
        
        if mc_server.is_running:
            return jsonify({
                'success': False,
                'error': 'Server is already running'
            })
        
        success = mc_server.start(current_config)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Server started successfully',
                'server_config': current_config
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to start server'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/stop-server', methods=['POST'])
def stop_server():
    """Stop the Minecraft server"""
    try:
        if not mc_server.is_running:
            return jsonify({
                'success': False,
                'error': 'Server is not running'
            })
        
        success = mc_server.stop()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Server stopped successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to stop server'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/server-status')
def server_status():
    """Get current server status"""
    return jsonify({
        'running': mc_server.is_running,
        'config': current_config if mc_server.is_running else {}
    })

@app.route('/api/config', methods=['GET', 'POST'])
def server_config():
    """Get or update server configuration"""
    global current_config
    
    if request.method == 'POST':
        if mc_server.is_running:
            return jsonify({
                'success': False,
                'error': 'Cannot change config while server is running'
            })
        
        config = request.json
        current_config.update(config)
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated',
            'config': current_config
        })
    else:
        return jsonify({
            'config': current_config,
            'running': mc_server.is_running
        })

def cleanup():
    """Cleanup function to stop server on exit"""
    if mc_server.is_running:
        mc_server.stop()

if __name__ == '__main__':
    import atexit
    atexit.register(cleanup)
    
    print("Minecraft Server API starting...")
    print(f"Access the control panel at: http://localhost:5000")
    print("The server will download Fabric automatically on first run")
    
    # Use waitress for production serving
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
