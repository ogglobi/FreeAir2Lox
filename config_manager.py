"""
FreeAir Bridge - Configuration Management
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

@dataclass
class LoxoneServer:
    """Loxone Miniserver Configuration (v1.4.0+)"""
    id: str  # Unique identifier (e.g., 'default', 'loxone_office', etc.)
    name: str  # Human-readable name (e.g., 'Wohnzimmer Miniserver')
    ip: str
    port: int
    api_key: str = ""  # Auto-generated UUID for API authentication
    enabled: bool = True

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data: dict):
        return LoxoneServer(**data)

@dataclass
class FreeAirDevice:
    """FreeAir Device Configuration"""
    id: str
    name: str
    serial_no: str
    password: str
    enabled: bool = True
    loxone_fields: list = field(default_factory=list)
    loxone_servers: list = field(default_factory=list)  # List of server IDs this device sends to (v1.4.0+)

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data: dict):
        # Handle missing loxone_fields in older configs
        if 'loxone_fields' not in data:
            data['loxone_fields'] = []
        # Handle missing loxone_servers for backward compatibility (v1.3 -> v1.4 migration)
        if 'loxone_servers' not in data:
            data['loxone_servers'] = []
        return FreeAirDevice(**data)

@dataclass
class LoxoneConfig:
    """Loxone Server Configuration"""
    ip: str
    port: int
    enabled: bool = True
    api_key: str = ""  # Auto-generated UUID for API authentication

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data: dict):
        return LoxoneConfig(**data)

class ConfigManager:
    """Manage application configuration"""

    # Use /app/config for Docker, fallback to local config/ for development
    CONFIG_FILE = os.getenv("CONFIG_FILE", "/app/config/FreeAir2Lox_config.json")
    DEFAULT_CONFIG = {
        "devices": [],
        "loxone": {
            "ip": "192.168.1.50",
            "port": 5555,
            "enabled": True,
            "api_key": ""
        },
        "loxone_servers": [],  # New in v1.4.0
        "http_port": 80,
        "udp_port": 5555,
        "admin_password_hash": None
    }

    def __init__(self):
        self.config_dir = os.path.dirname(self.CONFIG_FILE)
        self.ensure_config_dir()
        self.config = self.load_config()
        self._migrate_legacy_loxone_config()  # Auto-migrate v1.3 -> v1.4
        self.ensure_api_key()  # Auto-generate API key if missing

    def ensure_config_dir(self):
        """Ensure config directory exists"""
        os.makedirs(self.config_dir, exist_ok=True)

    def load_config(self) -> dict:
        """Load configuration from file"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r') as f:
                    return json.load(f)
            else:
                self.save_config(self.DEFAULT_CONFIG)
                return self.DEFAULT_CONFIG
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self.DEFAULT_CONFIG

    def ensure_api_key(self):
        """Ensure API key exists, generate if missing"""
        loxone = self.config.get("loxone", {})
        if not loxone.get("api_key"):
            loxone["api_key"] = str(uuid.uuid4())
            self.config["loxone"] = loxone
            self.save_config()
            logger.info(f"Generated new API key for Loxone commands: {loxone['api_key']}")

    def _migrate_legacy_loxone_config(self):
        """
        Auto-migrate from v1.3 single-server config to v1.4 multi-server config.
        
        v1.3 structure:
        {
            "loxone": {"ip": "192.168.1.50", "port": 5555, "enabled": True, "api_key": "..."}
        }
        
        v1.4 structure:
        {
            "loxone": {...},  # Kept for backward compatibility
            "loxone_servers": [
                {
                    "id": "default",
                    "name": "Default Miniserver",
                    "ip": "192.168.1.50",
                    "port": 5555,
                    "api_key": "...",
                    "enabled": True
                }
            ]
        }
        
        Devices get auto-assigned to "default" server on first migration.
        """
        try:
            # Check if migration already done
            if "loxone_servers" in self.config and len(self.config.get("loxone_servers", [])) > 0:
                return  # Already migrated
            
            # Initialize loxone_servers if missing
            if "loxone_servers" not in self.config:
                self.config["loxone_servers"] = []
            
            # Migrate old loxone config to new servers array
            old_loxone = self.config.get("loxone", {})
            if old_loxone and old_loxone.get("ip"):  # Only migrate if old config exists
                default_server = {
                    "id": "default",
                    "name": "Default Miniserver",
                    "ip": old_loxone.get("ip", "192.168.1.50"),
                    "port": old_loxone.get("port", 5555),
                    "api_key": old_loxone.get("api_key", ""),
                    "enabled": old_loxone.get("enabled", True)
                }
                self.config["loxone_servers"] = [default_server]
                logger.info("Migrated legacy Loxone config to multi-server format")
            
            # Auto-assign all devices to "default" server if not already assigned
            for device in self.config.get("devices", []):
                if not device.get("loxone_servers"):
                    device["loxone_servers"] = ["default"]
            
            self.save_config()
            logger.info("Completed migration from v1.3 to v1.4 config format")
        except Exception as e:
            logger.error(f"Error during legacy config migration: {e}")

    def save_config(self, config: dict = None):
        """Save configuration to file"""
        try:
            if config is None:
                config = self.config
            self.ensure_config_dir()
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get_devices(self) -> List[FreeAirDevice]:
        """Get all devices"""
        devices = []
        for device_data in self.config.get("devices", []):
            try:
                devices.append(FreeAirDevice.from_dict(device_data))
            except Exception as e:
                logger.error(f"Error loading device: {e}")
        return devices

    def add_device(self, device: FreeAirDevice) -> bool:
        """Add a new device"""
        try:
            # Check if device ID already exists
            existing_ids = [d["id"] for d in self.config.get("devices", [])]
            if device.id in existing_ids:
                logger.error(f"Device ID {device.id} already exists")
                return False

            self.config["devices"].append(device.to_dict())
            self.save_config()
            logger.info(f"Device {device.id} added")
            return True
        except Exception as e:
            logger.error(f"Error adding device: {e}")
            return False

    def update_device(self, device_id: str, device: FreeAirDevice) -> bool:
        """Update device configuration"""
        try:
            for i, d in enumerate(self.config.get("devices", [])):
                if d["id"] == device_id:
                    self.config["devices"][i] = device.to_dict()
                    self.save_config()
                    logger.info(f"Device {device_id} updated")
                    return True
            logger.error(f"Device {device_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error updating device: {e}")
            return False

    def delete_device(self, device_id: str) -> bool:
        """Delete device configuration"""
        try:
            self.config["devices"] = [d for d in self.config.get("devices", []) if d["id"] != device_id]
            self.save_config()
            logger.info(f"Device {device_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Error deleting device: {e}")
            return False

    def get_device(self, device_id: str) -> Optional[FreeAirDevice]:
        """Get specific device"""
        for device_data in self.config.get("devices", []):
            if device_data["id"] == device_id:
                try:
                    return FreeAirDevice.from_dict(device_data)
                except Exception as e:
                    logger.error(f"Error loading device: {e}")
        return None

    def get_loxone_config(self) -> LoxoneConfig:
        """Get Loxone configuration"""
        loxone_data = self.config.get("loxone", {})
        try:
            return LoxoneConfig.from_dict(loxone_data)
        except Exception as e:
            logger.error(f"Error loading Loxone config: {e}")
            return LoxoneConfig(**self.DEFAULT_CONFIG["loxone"])

    def update_loxone_config(self, loxone: LoxoneConfig) -> bool:
        """Update Loxone configuration"""
        try:
            self.config["loxone"] = loxone.to_dict()
            self.save_config()
            logger.info("Loxone config updated")
            return True
        except Exception as e:
            logger.error(f"Error updating Loxone config: {e}")
            return False

    # ===== MULTI-SERVER LOXONE METHODS (v1.4.0+) =====

    def get_loxone_servers(self) -> List[LoxoneServer]:
        """Get all configured Loxone servers"""
        servers = []
        for server_data in self.config.get("loxone_servers", []):
            try:
                servers.append(LoxoneServer.from_dict(server_data))
            except Exception as e:
                logger.error(f"Error loading Loxone server: {e}")
        return servers

    def get_loxone_server(self, server_id: str) -> Optional[LoxoneServer]:
        """Get specific Loxone server by ID"""
        for server_data in self.config.get("loxone_servers", []):
            if server_data.get("id") == server_id:
                try:
                    return LoxoneServer.from_dict(server_data)
                except Exception as e:
                    logger.error(f"Error loading Loxone server {server_id}: {e}")
        return None

    def add_loxone_server(self, server: LoxoneServer) -> bool:
        """Add a new Loxone server"""
        try:
            # Check if server ID already exists
            existing_ids = [s.get("id") for s in self.config.get("loxone_servers", [])]
            if server.id in existing_ids:
                logger.error(f"Loxone server ID {server.id} already exists")
                return False
            
            # Auto-generate API key if not provided
            if not server.api_key:
                server.api_key = str(uuid.uuid4())
            
            self.config["loxone_servers"].append(server.to_dict())
            self.save_config()
            logger.info(f"Loxone server {server.id} added with IP {server.ip}:{server.port}")
            return True
        except Exception as e:
            logger.error(f"Error adding Loxone server: {e}")
            return False

    def update_loxone_server(self, server_id: str, server: LoxoneServer) -> bool:
        """Update existing Loxone server"""
        try:
            for i, s in enumerate(self.config.get("loxone_servers", [])):
                if s.get("id") == server_id:
                    self.config["loxone_servers"][i] = server.to_dict()
                    self.save_config()
                    logger.info(f"Loxone server {server_id} updated")
                    return True
            logger.error(f"Loxone server {server_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error updating Loxone server: {e}")
            return False

    def delete_loxone_server(self, server_id: str) -> bool:
        """Delete Loxone server"""
        try:
            # Prevent deletion of the "default" server if it's the only one
            if server_id == "default":
                remaining_servers = [s for s in self.config.get("loxone_servers", []) if s.get("id") != "default"]
                if not remaining_servers:
                    logger.error("Cannot delete the only Loxone server (default)")
                    return False
            
            # Remove server from config
            self.config["loxone_servers"] = [s for s in self.config.get("loxone_servers", []) if s.get("id") != server_id]
            
            # Remove server assignments from all devices
            for device in self.config.get("devices", []):
                device["loxone_servers"] = [srv_id for srv_id in device.get("loxone_servers", []) if srv_id != server_id]
            
            self.save_config()
            logger.info(f"Loxone server {server_id} deleted and unassigned from all devices")
            return True
        except Exception as e:
            logger.error(f"Error deleting Loxone server: {e}")
            return False

    def assign_device_to_server(self, device_id: str, server_id: str) -> bool:
        """Assign a device to a Loxone server"""
        try:
            # Verify device exists
            device_found = False
            for device in self.config.get("devices", []):
                if device.get("id") == device_id:
                    device_found = True
                    if server_id not in device.get("loxone_servers", []):
                        device["loxone_servers"].append(server_id)
                    break
            
            if not device_found:
                logger.error(f"Device {device_id} not found")
                return False
            
            # Verify server exists
            server_found = any(s.get("id") == server_id for s in self.config.get("loxone_servers", []))
            if not server_found:
                logger.error(f"Loxone server {server_id} not found")
                return False
            
            self.save_config()
            logger.info(f"Device {device_id} assigned to server {server_id}")
            return True
        except Exception as e:
            logger.error(f"Error assigning device to server: {e}")
            return False

    def unassign_device_from_server(self, device_id: str, server_id: str) -> bool:
        """Remove device assignment from a Loxone server"""
        try:
            for device in self.config.get("devices", []):
                if device.get("id") == device_id:
                    device["loxone_servers"] = [srv_id for srv_id in device.get("loxone_servers", []) if srv_id != server_id]
                    self.save_config()
                    logger.info(f"Device {device_id} unassigned from server {server_id}")
                    return True
            logger.error(f"Device {device_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error unassigning device from server: {e}")
            return False

    def get_device_servers(self, device_id: str) -> List[LoxoneServer]:
        """Get all Loxone servers a device is assigned to"""
        for device in self.config.get("devices", []):
            if device.get("id") == device_id:
                servers = []
                for server_id in device.get("loxone_servers", []):
                    server = self.get_loxone_server(server_id)
                    if server:
                        servers.append(server)
                return servers
        return []

    def is_first_setup(self) -> bool:
        """Check if this is the first setup (Loxone IP still at default value)"""
        loxone = self.config.get("loxone", {})

        # First setup = Loxone IP is still default
        # This way user can change IP and complete setup, then add devices later
        is_default_loxone_ip = loxone.get("ip") == "192.168.1.50"

        return is_default_loxone_ip

    def mark_setup_complete(self):
        """Mark setup as complete (just save config after user has configured)"""
        self.save_config()

    # ===== AUTH METHODS =====

    def is_password_set(self) -> bool:
        """Check if admin password is already set"""
        password_hash = self.config.get("admin_password_hash")
        return password_hash is not None and password_hash != ""

    def set_admin_password(self, password: str) -> bool:
        """Set admin password (hashed)"""
        try:
            if not password or len(password) < 4:
                logger.error("Password must be at least 4 characters")
                return False

            self.config["admin_password_hash"] = generate_password_hash(password)
            self.save_config()
            logger.info("Admin password set successfully")
            return True
        except Exception as e:
            logger.error(f"Error setting password: {e}")
            return False

    def verify_admin_password(self, password: str) -> bool:
        """Verify admin password"""
        try:
            password_hash = self.config.get("admin_password_hash")
            if not password_hash:
                logger.warning("No password set yet")
                return False

            return check_password_hash(password_hash, password)
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return False

    def change_admin_password(self, old_password: str, new_password: str) -> bool:
        """Change admin password"""
        try:
            # Verify old password
            if not self.verify_admin_password(old_password):
                logger.error("Old password verification failed")
                return False

            # Set new password
            return self.set_admin_password(new_password)
        except Exception as e:
            logger.error(f"Error changing password: {e}")
            return False
