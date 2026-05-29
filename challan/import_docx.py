"""
Import all .docx challan files into MongoDB.
Reads JSON from each docx, maps filename -> state_name, inserts into roadlaw.challans.
"""
import json
import re
import os
from pathlib import Path
from docx import Document
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = "roadlaw"

DOCX_DIR = Path(r"C:\Users\Deependra\Downloads\challan")

# Map filename -> (country, state_name)
FILE_STATE_MAP = {
    "Andra Pradesh json.docx":                ("India", "Andhra Pradesh"),
    "arunachal pradesh violation json.docx":   ("India", "Arunachal Pradesh"),
    "Assam challan violation json.docx":       ("India", "Assam"),
    "Bihar Violation challan.docx":            ("India", "Bihar"),
    "Chhattisgarh Violation challan.docx":     ("India", "Chhattisgarh"),
    "Goa Violation challan.docx":              ("India", "Goa"),
    "Gujrat Violation Challan.docx":           ("India", "Gujarat"),
    "Haryana Violation Challan.docx":          ("India", "Haryana"),
    "Himachal Pradesh Violation Challan.docx": ("India", "Himachal Pradesh"),
    "Jharkhand Violation Challan.docx":        ("India", "Jharkhand"),
    "Karnataka Violation Challan.docx":        ("India", "Karnataka"),
    "Kerala Violation Challan.docx":           ("India", "Kerala"),
    "MP traffic Violation rules.docx":         ("India", "Madhya Pradesh"),
    "Maharashtra Violation Challan.docx":      ("India", "Maharashtra"),
    "Manipur Violation Challan.docx":          ("India", "Manipur"),
    "Meghalaya Violation Challan.docx":        ("India", "Meghalaya"),
    "Mizoram Violation Challan.docx":          ("India", "Mizoram"),
    "nagaland challan json.docx":              ("India", "Nagaland"),
    "orisha challan json.docx":                ("India", "Odisha"),
    "punjab challan json file.docx":           ("India", "Punjab"),
    "rajasthan challan json.docx":             ("India", "Rajasthan"),
    "sikkim challan json.docx":                ("India", "Sikkim"),
    "tamilnadu challan json.docx":             ("India", "Tamil Nadu"),
    "telangana challan json .docx":            ("India", "Telangana"),
    "tripura challan json .docx":              ("India", "Tripura"),
    "up Violation challan.docx":               ("India", "Uttar Pradesh"),
    "uttrakhand challan json .docx":           ("India", "Uttarakhand"),
    "West Bengal challan json .docx":          ("India", "West Bengal"),
}

# Auto-generate keywords from violation name
def generate_keywords(violation: str, offense_id: str = "") -> list[str]:
    """Generate searchable keywords from the violation name."""
    keywords = []

    # Normalize violation text
    v = violation.lower().strip()

    # Direct keyword mappings
    keyword_map = {
        "helmet": ["no_helmet", "helmet", "bina_helmet", "without_helmet"],
        "seat belt": ["no_seatbelt", "seatbelt", "seat_belt", "bina_seatbelt"],
        "seatbelt": ["no_seatbelt", "seatbelt", "seat_belt"],
        "drunk": ["drunk_driving", "dui", "drink_drive", "alcohol", "nashe_mein"],
        "alcohol": ["drunk_driving", "alcohol"],
        "influence of drugs": ["drunk_driving", "drugs"],
        "speed": ["over_speeding", "speeding", "speed", "tez_speed"],
        "overspeeding": ["over_speeding", "speeding"],
        "red light": ["red_light_jump", "signal_jump", "red_light", "traffic_signal"],
        "signal": ["red_light_jump", "signal_jump", "signal_todna"],
        "without license": ["no_license", "without_license", "bina_license", "no_dl"],
        "without holding": ["no_license", "without_license"],
        "unlicensed": ["no_license"],
        "without insurance": ["no_insurance", "insurance_expired", "bima_nahi"],
        "insurance": ["no_insurance", "insurance"],
        "mobile": ["using_phone", "mobile_phone", "phone_driving", "phone"],
        "phone": ["using_phone", "phone"],
        "wrong side": ["wrong_side", "wrong_way", "galat_side"],
        "parking": ["no_parking", "illegal_parking", "parking_violation"],
        "triple": ["triple_riding", "3_riding", "teen_savari"],
        "pillion": ["triple_riding"],
        "registration": ["no_registration", "expired_registration", "rc_expired"],
        "puc": ["no_puc", "puc_expired", "pollution"],
        "pollution": ["no_puc", "pollution"],
        "dangerous": ["dangerous_driving", "rash_driving"],
        "rash": ["rash_driving", "dangerous_driving", "reckless_driving"],
        "reckless": ["rash_driving", "reckless_driving"],
        "juvenile": ["juvenile_driving", "underage_driving", "minor_driving"],
        "under aged": ["juvenile_driving", "underage_driving", "minor_driving"],
        "underage": ["juvenile_driving", "underage_driving"],
        "overloading": ["overloading", "overweight"],
        "overload": ["overloading"],
        "number plate": ["no_number_plate", "number_plate", "fancy_plate"],
        "number plat": ["no_number_plate", "number_plate"],
        "fancy": ["fancy_plate", "number_plate"],
        "horn": ["excessive_horn", "horn", "honking"],
        "noise": ["excessive_horn", "noise_pollution"],
        "towing": ["illegal_towing", "towing"],
        "ambulance": ["blocking_ambulance", "emergency_vehicle"],
        "emergency": ["blocking_ambulance", "emergency_vehicle"],
        "one way": ["one_way_violation", "wrong_way"],
        "zebra": ["zebra_crossing", "pedestrian"],
        "pedestrian": ["pedestrian_crossing", "zebra_crossing"],
        "stop line": ["stop_line_violation"],
        "modification": ["illegal_modification", "vehicle_modification"],
        "modified": ["illegal_modification"],
        "honking": ["excessive_horn", "honking"],
        "silencer": ["modified_silencer", "illegal_modification"],
        "tint": ["dark_tint", "window_tint"],
        "black film": ["dark_tint", "window_tint"],
    }

    for trigger, kws in keyword_map.items():
        if trigger in v:
            keywords.extend(kws)

    # Add the violation name itself as underscore keyword
    base_kw = re.sub(r'[^a-z0-9\s]', '', v)
    base_kw = re.sub(r'\s+', '_', base_kw.strip())
    if base_kw and base_kw not in keywords:
        keywords.append(base_kw)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            unique.append(k)

    return unique if unique else [base_kw]


def normalize_fine(challan_amount) -> int:
    """Extract a single integer fine amount from various formats."""
    if isinstance(challan_amount, int):
        return challan_amount
    if isinstance(challan_amount, float):
        return int(challan_amount)
    if isinstance(challan_amount, dict):
        # Try first_offense, minimum, or first numeric value
        for key in ["first_offense", "minimum", "LMV", "first"]:
            if key in challan_amount:
                val = challan_amount[key]
                if isinstance(val, (int, float)):
                    return int(val)
        # Fallback: first numeric value
        for val in challan_amount.values():
            if isinstance(val, (int, float)):
                return int(val)
    if isinstance(challan_amount, str):
        nums = re.findall(r'\d+', challan_amount)
        if nums:
            return int(nums[0])
    return 0


def main():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db["challans"]

    total_imported = 0

    for filename, (country, state_name) in FILE_STATE_MAP.items():
        filepath = DOCX_DIR / filename

        if not filepath.exists():
            print(f"  [SKIP] File not found: {filename}")
            continue

        print(f"\n  Reading: {filename} -> {country}/{state_name}")

        # Read docx
        doc = Document(str(filepath))
        text = "\n".join([p.text for p in doc.paragraphs])

        # Extract JSON array from text
        try:
            # Find the JSON array
            start = text.index("[")
            end = text.rindex("]") + 1
            json_text = text[start:end]
            records = json.loads(json_text)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  [ERR] Could not parse JSON from {filename}: {e}")
            continue

        # Remove existing records for this state
        deleted = collection.delete_many({"country": country, "state_name": state_name})
        if deleted.deleted_count > 0:
            print(f"  [CLEAN] Removed {deleted.deleted_count} old records for {state_name}")

        # Transform and insert
        docs_to_insert = []
        for rec in records:
            violation = rec.get("violation", rec.get("offense", "Unknown"))
            offense_id = rec.get("offense_id", "")

            doc_entry = {
                "country": country,
                "state_name": state_name,
                "offense_id": offense_id,
                "category": rec.get("category", ""),
                "offense": violation,
                "keywords": generate_keywords(violation, offense_id),
                "section": rec.get("law_section", "N/A"),
                "description": violation,
                "fine_amount": normalize_fine(rec.get("challan_amount", 0)),
                "challan_amount_raw": rec.get("challan_amount"),
                "vehicle_type": rec.get("vehicle_type", None),
                "applicable_to": rec.get("applicable_to", None),
                "detection_method": rec.get("detection_method", None),
                "additional_action": rec.get("additional_action", rec.get("additional_punishment", None)),
                "repeat_offense_action": rec.get("repeat_offense_action", None),
                "notes": rec.get("notes", None),
            }
            docs_to_insert.append(doc_entry)

        if docs_to_insert:
            collection.insert_many(docs_to_insert)
            total_imported += len(docs_to_insert)
            print(f"  [OK] Imported {len(docs_to_insert)} challans for {state_name}")

    print(f"\n{'='*60}")
    print(f"  TOTAL: {total_imported} records imported into MongoDB")
    print(f"{'='*60}\n")

    # Print summary
    pipeline = [
        {"$group": {"_id": {"country": "$country", "state": "$state_name"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.state": 1}},
    ]
    print("  MongoDB Summary:")
    for doc in collection.aggregate(pipeline):
        print(f"    {doc['_id']['country']}/{doc['_id']['state']}: {doc['count']} records")

    client.close()


if __name__ == "__main__":
    main()
