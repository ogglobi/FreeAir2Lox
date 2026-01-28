"""
AES-128-CBC Cryptography Utilities for FreeAir Bridge
Ported from ioBroker.freeair DataParser
"""

import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)


def decrypt_freeair_payload(b_value, password):
    """
    Decrypt FreeAir device payload using AES-128-CBC
    
    Args:
        b_value (str): Base64URL-encoded encrypted data
        password (str): Device password
        
    Returns:
        bytes: Decrypted payload, or None if decryption fails
    """
    try:
        # Decode base64 (URL-safe variant): - -> +, _ -> /
        b64_str = b_value.replace('-', '+').replace('_', '/')
        
        # Add padding if needed
        missing_padding = len(b64_str) % 4
        if missing_padding:
            b64_str += '=' * (4 - missing_padding)
        
        encrypted_data = base64.b64decode(b64_str)
        
        # Key derivation: password padded to 16 bytes with CHARACTER '0'
        # EXACT from ioBroker: key = CryptoJS.enc.Utf8.parse(password.padEnd(16, "0"))
        if isinstance(password, str):
            padded_pw = (password + '0' * 16)[:16]
            key = padded_pw.encode('utf-8')
        else:
            key = password
        
        # Fixed IV for FreeAir protocol
        iv = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
        
        # AES-128-CBC decryption
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
        
        return decrypted
        
    except Exception as e:
        logger.error(f"Decryption failed: {e}", exc_info=True)
        return None


def encrypt_freeair_response(response_text, password):
    """
    Encrypt FreeAir device response using AES-128-CBC
    
    Args:
        response_text (str): Response text (e.g., "heart__beat1151\n")
        password (str): Device password
        
    Returns:
        str: Base64URL-encoded encrypted data, or None if encryption fails
    """
    try:
        # Prepare response as bytes
        if isinstance(response_text, str):
            response_data = response_text.encode('utf-8')
        else:
            response_data = response_text
        
        # Pad to 16-byte boundary with zero padding
        pad_len = 16 - (len(response_data) % 16)
        if pad_len > 0:
            response_data += bytes([0] * pad_len)
        
        # Key derivation
        if isinstance(password, str):
            padded_pw = (password + '0' * 16)[:16]
            key = padded_pw.encode('utf-8')
        else:
            key = password
        
        # Fixed IV
        iv = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
        
        # AES-128-CBC encryption
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(response_data) + encryptor.finalize()
        
        # Encode to base64URL
        b64 = base64.b64encode(encrypted).decode('utf-8')
        b64_url = b64.replace('+', '-').replace('/', '_').rstrip('=')
        
        return b64_url
        
    except Exception as e:
        logger.error(f"Encryption failed: {e}", exc_info=True)
        return None
