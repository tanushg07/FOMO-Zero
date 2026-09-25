import subprocess
import requests
import time

def test_pipeline():
    print("Submitting notice to backend API...")
    res = requests.post("http://127.0.0.1:8000/api/notices", json={
        "title": "Test Notice",
        "text": "The final exam for CS101 has been moved to December 15th at 9:00 AM. It is mandatory for all undergraduate students. Failure to attend will result in an automatic F."
    })
    
    if res.status_code != 201:
        print(f"Error submitting notice: {res.text}")
        return
        
    notice_id = res.json()["id"]
    print(f"Created notice {notice_id}. Running worker...")
    
    # Run the worker for this notice
    subprocess.run([".venv/Scripts/python", "-m", "fomo_zero.worker", "--notice-id", notice_id], check=True)
    
    print("Worker finished. Fetching notice...")
    res2 = requests.get(f"http://127.0.0.1:8000/api/notices/{notice_id}")
    data = res2.json()
    
    print("\n--- Processed Notice ---")
    print(f"Title: {data['title']}")
    print(f"Validation Status: {data['validation_status']}")
    print(f"Core Update: {data['core_update']}")
    print(f"Target Audience: {data['target_audience']}")
    print(f"Critical Dates: {data['critical_dates']}")
    print(f"Action Checklist: {data['action_checklist']}")
    print(f"Evidence: {data['raw_evidence'][:100]}...")

if __name__ == "__main__":
    test_pipeline()
