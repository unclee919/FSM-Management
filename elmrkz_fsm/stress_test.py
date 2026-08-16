import sys
import json

# This script is intended to be run via `bench execute` on the production server.
# It simulates 50+ assignment scenarios to validate the engine accuracy.

def run_stress_test():
    import frappe
    from elmrkz_fsm.assignment import _score_technician, calculate_distance
    
    # Ensure FSM Settings are loaded
    settings = frappe.get_doc("FSM Settings", "FSM Settings")
    
    # Mock data for scenarios
    # We will create temporary technicians and service requests in memory for scoring
    # without necessarily saving them to the DB if possible, or using existing ones.
    
    scenarios = []
    
    # Helper to create a mock tech object
    def create_mock_tech(name, lat, lon, status="Available", territory="Cairo", open_count=0):
        class MockTech:
            def __init__(self):
                self.name = name
                self.current_latitude = lat
                self.current_longitude = lon
                self.availability_status = status
                self.territory = territory
        return MockTech()

    # Helper to create a mock item object
    def create_mock_item(device, failure, brand=None):
        class MockItem:
            def __init__(self):
                self.device_name = device
                self.failure_reason = failure
                self.brand = brand
        return MockItem()

    # Helper to create a mock service request
    def create_mock_sr(lat, lon, territory="Cairo"):
        class MockSR:
            def __init__(self):
                self.latitude = lat
                self.longitude = lon
                self.territory = territory
        return MockSR()

    # 1. Proximity vs Skill (10 scenarios)
    for i in range(10):
        sr = create_mock_sr(30.0, 31.0)
        item = create_mock_item("AC Unit", "Cooling Failure")
        
        # Tech 1: Very close (1km), but no skills
        t1 = create_mock_tech(f"T1_{i}", 30.01, 31.01)
        # Tech 2: Further (10km), but has skills
        t2 = create_mock_tech(f"T2_{i}", 30.1, 31.1)
        
        scenarios.append({
            "name": f"Proximity vs Skill {i}",
            "sr": sr,
            "item": item,
            "techs": [t1, t2],
            "expected": "T2" # Skill match usually weighted higher or combined
        })

    # 2. Workload Balance (10 scenarios)
    for i in range(10):
        sr = create_mock_sr(30.0, 31.0)
        item = create_mock_item("General", "General")
        
        # Tech 1: Available, 0 load
        t1 = create_mock_tech(f"T_LowLoad_{i}", 30.01, 31.01, open_count=0)
        # Tech 2: Available, 8 load
        t2 = create_mock_tech(f"T_HighLoad_{i}", 30.01, 31.01, open_count=8)
        
        scenarios.append({
            "name": f"Workload Balance {i}",
            "sr": sr,
            "item": item,
            "techs": [t1, t2],
            "expected": "T_LowLoad"
        })

    # 3. Territory Match (10 scenarios)
    for i in range(10):
        sr = create_mock_sr(30.0, 31.0, territory="Cairo")
        item = create_mock_item("General", "General")
        
        # Tech 1: Same territory
        t1 = create_mock_tech(f"T_Cairo_{i}", 30.05, 31.05, territory="Cairo")
        # Tech 2: Different territory, slightly closer
        t2 = create_mock_tech(f"T_Giza_{i}", 30.02, 31.02, territory="Giza")
        
        scenarios.append({
            "name": f"Territory Match {i}",
            "sr": sr,
            "item": item,
            "techs": [t1, t2],
            "expected": "T_Cairo"
        })

    # 4. Fuzzy Skill Match (10 scenarios)
    for i in range(10):
        sr = create_mock_sr(30.0, 31.0)
        # User might type "Air Con"
        item = create_mock_item("Air Con", "Water Leak")
        
        # Tech 1: Has skill "AC Unit"
        t1 = create_mock_tech(f"T_AC_{i}", 30.01, 31.01)
        # Tech 2: No relevant skills
        t2 = create_mock_tech(f"T_None_{i}", 30.01, 31.01)
        
        scenarios.append({
            "name": f"Fuzzy Skill Match {i}",
            "sr": sr,
            "item": item,
            "techs": [t1, t2],
            "expected": "T_AC"
        })

    # 5. Complex Combined (10+ scenarios)
    for i in range(15):
        sr = create_mock_sr(30.0, 31.0, territory="Alexandria")
        item = create_mock_item("Refrigerator", "Not Cooling", "Samsung")
        
        # Various techs with mixed attributes
        t1 = create_mock_tech(f"T_Complex1_{i}", 30.02, 31.02, territory="Alexandria", open_count=2)
        t2 = create_mock_tech(f"T_Complex2_{i}", 30.01, 31.01, territory="Cairo", open_count=0)
        t3 = create_mock_tech(f"T_Complex3_{i}", 30.5, 31.5, territory="Alexandria", open_count=5)
        
        scenarios.append({
            "name": f"Complex Combined {i}",
            "sr": sr,
            "item": item,
            "techs": [t1, t2, t3],
            "expected": "Variable"
        })

    results = []
    
    # We need to monkeypatch frappe.db.count and _technician_skills to avoid DB hits during stress test
    # for pure logic validation.
    
    original_count = frappe.db.count
    original_skills = sys.modules['elmrkz_fsm.assignment']._technician_skills
    original_completion = sys.modules['elmrkz_fsm.assignment'].get_completion_rate
    original_route = sys.modules['elmrkz_fsm.assignment'].get_route_suitability
    
    # Simple mock skill mapping for the test
    mock_skills_db = {
        "T2": {"device_name": ["AC Unit"], "failure_reason": ["Cooling Failure"], "brand": []},
        "T_AC": {"device_name": ["AC Unit", "Air Conditioner"], "failure_reason": [], "brand": []},
        "T_Complex1": {"device_name": ["Refrigerator"], "failure_reason": ["Not Cooling"], "brand": ["Samsung"]},
    }

    def mock_skills(tech_name):
        base_name = tech_name.split('_')[0] + "_" + tech_name.split('_')[1] if "_" in tech_name else tech_name
        # Match prefixes for our test techs
        for key in mock_skills_db:
            if tech_name.startswith(key):
                return mock_skills_db[key]
        return {"device_name": [], "failure_reason": [], "brand": []}

    def mock_db_count(doctype, filters=None):
        if doctype == "Service Request":
            # Extract load from name for our test
            if "assigned_technician" in filters:
                tech_name = filters["assigned_technician"]
                if "HighLoad" in tech_name: return 8
                if "LowLoad" in tech_name: return 0
                if "Complex1" in tech_name: return 2
                if "Complex3" in tech_name: return 5
        return 0

    def mock_completion(tech_name):
        return 0.8 # Default high performance

    def mock_route(tech_name, lat, lon):
        return 1.0 # Default good route

    # Apply mocks
    sys.modules['elmrkz_fsm.assignment']._technician_skills = mock_skills
    frappe.db.count = mock_db_count
    sys.modules['elmrkz_fsm.assignment'].get_completion_rate = mock_completion
    sys.modules['elmrkz_fsm.assignment'].get_route_suitability = mock_route

    try:
        for s in scenarios:
            scores = []
            for t in s["techs"]:
                score = _score_technician(t, s["sr"], settings, s["item"])
                scores.append({"tech": t.name, "score": score})
            
            # Sort by score descending
            scores.sort(key=lambda x: x["score"], reverse=True)
            winner = scores[0]["tech"]
            
            results.append({
                "scenario": s["name"],
                "winner": winner,
                "scores": scores
            })
    finally:
        # Restore originals
        frappe.db.count = original_count
        sys.modules['elmrkz_fsm.assignment']._technician_skills = original_skills
        sys.modules['elmrkz_fsm.assignment'].get_completion_rate = original_completion
        sys.modules['elmrkz_fsm.assignment'].get_route_suitability = original_route

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run_stress_test()
