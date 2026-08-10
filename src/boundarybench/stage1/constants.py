"""Constants for Stage 1 RPMS-shaped projection and corruption generation.

The terminology table is a narrow, approximate synthetic-data crosswalk. It is
not a clinical crosswalk and must not be used as coding authority.
"""

from __future__ import annotations

DEM_FIELDS = [
    "DFN",
    "HRN",
    "SSN",
    "LAST",
    "FIRST",
    "MIDDLE",
    "DOB",
    "SEX",
    "RACE",
    "ETHNICITY",
    "STREET",
    "CITY",
    "STATE",
    "ZIP",
    "PHONE",
    "MARITAL_STATUS",
    "COMMUNITY",
    "SERVICE_UNIT",
    "ELIGIBILITY",
    "DECEASED_DATE",
]

PXX_FIELDS = [
    "VISIT_IEN",
    "PATIENT_ID",
    "VISIT_DATETIME",
    "VISIT_TYPE",
    "CLINIC",
    "PROVIDER",
    "VISIT_REASON_TEXT",
    "POV_ICD",
    "POV_ICD_VERSION",
]

LAB_FIELDS = [
    "LAB_IEN",
    "PATIENT_ID",
    "ACCESSION",
    "COLLECTION_DATETIME",
    "TEST_NAME",
    "LOINC",
    "RESULT_VALUE",
    "UNITS",
    "ABNORMAL_FLAG",
]

PROB_FIELDS = [
    "PROB_IEN",
    "PATIENT_ID",
    "ICD_CODE",
    "ICD_VERSION",
    "NARRATIVE",
    "ONSET_DATE",
    "STATUS",
    "PROVIDER",
]

RPMS_FIELDS = {
    "DEM": DEM_FIELDS,
    "PXX": PXX_FIELDS,
    "LAB": LAB_FIELDS,
    "PROB": PROB_FIELDS,
}

FREE_TEXT_SNIPPETS = [
    "pt c/o here for f/u, denies CP/SOB",
    "see nursing note 3south",
    "call back re: refill, no show",
    "translator needed - Lakota speaking",
    "transportation van pickup requested",
    "pending - see scanned doc",
    "verify w/ registration desk",
    "chart note cont'd on back",
    "pt declined to answer",
    "unable to reach by phone x3",
    "see behavioral health consult",
    "specimen hemolyzed, redraw ordered",
    "results called to provider 1500",
    "dx pending, see clinician addendum",
    "community health rep home visit",
]

ORPHAN_IDS = ["900001", "900002", "PRH-900003", "0900004", "900-005", "IHS900006"]

ELIGIBILITY_CHOICES = ["DIRECT", "DIRECT", "DIRECT", "CHS", "REFERRED", "NON-BEN"]

ENCOUNTER_CLASS_MAP = {
    "AMB": "AMBULATORY",
    "EMER": "EMERGENCY",
    "IMP": "INPATIENT",
    "OBSENC": "OBSERVATION",
    "VR": "VIRTUAL",
}

CORRUPTIBLE_FIELDS = {
    "DEM": {
        "SSN",
        "LAST",
        "FIRST",
        "MIDDLE",
        "SEX",
        "STREET",
        "CITY",
        "STATE",
        "ZIP",
        "PHONE",
        "MARITAL_STATUS",
        "COMMUNITY",
    },
    "PXX": {"VISIT_TYPE", "CLINIC", "PROVIDER", "VISIT_REASON_TEXT"},
    "LAB": {"TEST_NAME", "LOINC", "RESULT_VALUE", "UNITS", "ABNORMAL_FLAG"},
    "PROB": {"NARRATIVE", "STATUS", "PROVIDER"},
}

BLEED_FIELDS = {
    ("DEM", "SEX"),
    ("DEM", "ZIP"),
    ("PXX", "VISIT_REASON_TEXT"),
    ("LAB", "RESULT_VALUE"),
    ("PROB", "NARRATIVE"),
}

# SNOMED -> (ICD-10-CM, ICD-9-CM, chronic/problem-list eligible).
# Approximate mapping for synthetic benchmark boundary tests only.
SNOMED_CROSSWALK = {
    "44054006": ("E11.9", "250.00", True),
    "15777000": ("R73.03", "790.29", True),
    "714628002": ("R73.03", "790.29", True),
    "127013003": ("E11.29", "250.40", True),
    "422034002": ("E11.319", "250.50", True),
    "368581000119106": ("E11.40", "250.60", True),
    "162864005": ("E66.9", "278.00", True),
    "237602007": ("E88.81", "277.70", True),
    "59621000": ("I10", "401.90", True),
    "55822004": ("E78.5", "272.40", True),
    "302870006": ("E78.1", "272.10", True),
    "53741008": ("I25.10", "414.00", True),
    "88805009": ("I50.9", "428.00", True),
    "230690007": ("I63.9", "434.91", True),
    "49436004": ("I48.91", "427.31", True),
    "22298006": ("I21.9", "410.90", False),
    "399211009": ("I25.2", "412", True),
    "26929004": ("G30.9", "331.0", True),
    "271737000": ("D64.9", "285.9", True),
    "64859006": ("M81.0", "733.00", True),
    "443165006": ("M80.00XA", "733.10", True),
    "239873007": ("M17.9", "715.96", True),
    "201834006": ("M18.9", "715.94", True),
    "82423001": ("G89.29", "338.29", True),
    "124171000119105": ("G43.109", "346.10", True),
    "128613002": ("G40.909", "345.90", True),
    "192127007": ("F90.9", "314.01", True),
    "195967001": ("J45.909", "493.90", True),
    "185086009": ("J44.9", "491.20", True),
    "87433001": ("J43.9", "492.80", True),
    "40055000": ("J32.9", "473.90", True),
    "36971009": ("J32.9", "473.90", True),
    "232353008": ("J30.89", "477.9", True),
    "446096008": ("J30.89", "477.8", True),
    "444814009": ("J01.90", "461.90", False),
    "195662009": ("J02.9", "462", False),
    "10509002": ("J20.9", "466.00", False),
    "65363002": ("H66.90", "382.9", False),
    "43878008": ("J02.0", "034.00", False),
    "75498004": ("J01.90", "461.90", False),
    "72892002": ("Z34.90", "V22.2", False),
    "19169002": ("O03.9", "634.90", False),
    "156073000": ("O03.9", "634.90", False),
    "35999006": ("O02.0", "631.8", False),
    "398254007": ("O14.90", "642.40", False),
    "198992004": ("O15.00", "642.60", False),
    "74400008": ("K37", "541", False),
    "47693006": ("K35.32", "540.10", False),
    "68496003": ("K63.5", "211.3", False),
    "196416002": ("K01.1", "520.6", False),
    "80394007": ("R73.9", "790.29", False),
    "55680006": ("T50.901A", "977.90", False),
    "370247008": ("S01.90XA", "873.40", False),
    "44465007": ("S93.409A", "845.00", False),
    "70704007": ("S63.90XA", "842.00", False),
    "58150001": ("S42.009A", "810.00", False),
    "65966004": ("S52.90XA", "813.80", False),
    "39848009": ("S13.4XXA", "847.0", False),
    "62106007": ("S06.0X0A", "850.11", False),
    "284549007": ("S61.409A", "882.0", False),
    "284551006": ("S91.309A", "892.0", False),
    "263102004": ("S63.009A", "833.00", False),
}

