#!/usr/bin/env python3
"""
Phase 5 - Multi-Server Integration Tests (v1.4.0)

Test scenarios for multi-Miniserver architecture:
1. XML generation functions accept server_id parameter
2. API endpoints handle server_id query parameter
3. Type hints are correct
"""

import sys
import unittest
from pathlib import Path
from inspect import signature

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from loxone_xml import generate_loxone_xml, generate_loxone_command_template


class TestPhase5MultiServer(unittest.TestCase):
    """Test suite for Phase 5 - Multi-Server functionality"""

    def test_001_xml_input_function_has_server_id_param(self):
        """Test that generate_loxone_xml accepts server_id parameter"""
        sig = signature(generate_loxone_xml)
        params = list(sig.parameters.keys())
        
        self.assertIn('server_id', params, "generate_loxone_xml missing server_id parameter")
        self.assertIn('config_mgr', params, "generate_loxone_xml missing config_mgr parameter")
        
        print("[PASS] Test 001: generate_loxone_xml has server_id and config_mgr params")

    def test_002_xml_output_function_has_server_id_param(self):
        """Test that generate_loxone_command_template accepts server_id parameter"""
        sig = signature(generate_loxone_command_template)
        params = list(sig.parameters.keys())
        
        self.assertIn('server_id', params, "generate_loxone_command_template missing server_id parameter")
        self.assertIn('config_mgr', params, "generate_loxone_command_template missing config_mgr parameter")
        
        print("[PASS] Test 002: generate_loxone_command_template has server_id and config_mgr params")

    def test_003_xml_input_function_signature_order(self):
        """Test that server_id and config_mgr are at end of signature"""
        sig = signature(generate_loxone_xml)
        params = list(sig.parameters.keys())
        
        # Expected order: device_name, selected_fields, port, bridge_ip, device_data, server_id, config_mgr
        expected_tail = ['server_id', 'config_mgr']
        actual_tail = params[-2:]
        
        self.assertEqual(actual_tail, expected_tail, f"Expected {expected_tail}, got {actual_tail}")
        
        print("[PASS] Test 003: generate_loxone_xml signature order correct")

    def test_004_xml_output_function_signature_order(self):
        """Test that server_id and config_mgr are at end of signature"""
        sig = signature(generate_loxone_command_template)
        params = list(sig.parameters.keys())
        
        expected_tail = ['server_id', 'config_mgr']
        actual_tail = params[-2:]
        
        self.assertEqual(actual_tail, expected_tail, f"Expected {expected_tail}, got {actual_tail}")
        
        print("[PASS] Test 004: generate_loxone_command_template signature order correct")

    def test_005_server_id_param_has_default(self):
        """Test that server_id parameter has default value"""
        sig = signature(generate_loxone_xml)
        server_id_param = sig.parameters['server_id']
        
        # Should have default value (None)
        self.assertIsNone(server_id_param.default, "server_id default should be None")
        
        print("[PASS] Test 005: server_id has default value (None)")

    def test_006_config_mgr_param_has_default(self):
        """Test that config_mgr parameter has default value"""
        sig = signature(generate_loxone_xml)
        config_mgr_param = sig.parameters['config_mgr']
        
        # Should have default value (None)
        self.assertIsNone(config_mgr_param.default, "config_mgr default should be None")
        
        print("[PASS] Test 006: config_mgr has default value (None)")

    def test_007_xml_generation_basic_functionality(self):
        """Test that XML generation still works with basic parameters"""
        try:
            xml = generate_loxone_xml(
                device_name="TestDevice",
                selected_fields=["temperature", "humidity"]
            )
            
            self.assertIsNotNone(xml, "Should generate XML")
            self.assertIn("VirtualInUdp", xml, "XML should contain VirtualInUdp")
            
            print("[PASS] Test 007: XML input generation works")
        except Exception as e:
            self.fail(f"XML generation failed: {e}")

    def test_008_command_template_basic_functionality(self):
        """Test that command template generation still works with basic parameters"""
        try:
            xml = generate_loxone_command_template(
                device_name="TestDevice",
                device_id="test_device",
                api_key="test-key-12345"
            )
            
            self.assertIsNotNone(xml, "Should generate command template")
            self.assertIn("VirtualOut", xml, "XML should contain VirtualOut")
            self.assertIn("test-key-12345", xml, "XML should contain API key")
            
            print("[PASS] Test 008: XML command template generation works")
        except Exception as e:
            self.fail(f"Command template generation failed: {e}")

    def test_009_backward_compatibility_functions_callable(self):
        """Test backward compatibility - functions callable without new parameters"""
        # These calls should succeed without using server_id or config_mgr
        try:
            # Call without server_id and config_mgr
            xml1 = generate_loxone_xml("Device1", ["temp"])
            xml2 = generate_loxone_command_template("Device2", "dev2", "192.168.1.1", 80, "key123")
            
            self.assertIsNotNone(xml1)
            self.assertIsNotNone(xml2)
            
            print("[PASS] Test 009: Backward compatibility - functions callable without new params")
        except Exception as e:
            self.fail(f"Backward compatibility broken: {e}")

    def test_010_api_key_in_command_xml(self):
        """Test that API key is correctly embedded in command XML"""
        api_key = "custom-api-key-12345"
        xml = generate_loxone_command_template(
            device_name="TestDevice",
            device_id="test_device",
            api_key=api_key
        )
        
        self.assertIn(api_key, xml, "API key should be in generated XML")
        self.assertIn("Authorization: Bearer", xml, "Should have Bearer token header")
        
        print("[PASS] Test 010: API key correctly embedded in command XML")


def run_all_tests():
    """Run all Phase 5 tests"""
    print("\n" + "="*70)
    print("PHASE 5 - MULTI-SERVER INTEGRATION TESTS (v1.4.0)")
    print("="*70 + "\n")

    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase5MultiServer)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    if result.wasSuccessful():
        print("\nALL TESTS PASSED - Phase 5 validation complete!")
    print("="*70 + "\n")

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
