"""Seed local development database with realistic test data.

Usage:
    cd trove-api
    uv run python scripts/seed.py --email user@example.com
    uv run python scripts/seed.py --email user@example.com --clear
"""

import argparse
import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Ensure the project root is on sys.path for standalone execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models.collection import Collection  # noqa: E402
from app.models.item import Item  # noqa: E402
from app.models.item_note import ItemNote  # noqa: E402
from app.models.mark import Mark  # noqa: E402
from app.models.provenance_entry import ProvenanceEntry  # noqa: E402
from app.models.tag import Tag, item_tags  # noqa: E402
from app.models.user import User  # noqa: E402


def uid() -> str:
    return str(uuid4())


# ── Tag names ────────────────────────────────────────────────────────────────

TAG_NAMES = [
    "vintage",
    "rare",
    "mint condition",
    "needs restoration",
    "gift",
    "inherited",
    "auction find",
    "estate sale",
    "flea market",
    "signed",
    "limited edition",
    "first edition",
    "damaged",
    "framed",
    "displayed",
    "stored",
    "insured",
    "appraised",
]


# ── Collection definitions ───────────────────────────────────────────────────

COLLECTIONS = [
    {
        "name": "World Stamps",
        "type": "stamp",
        "description": "Postage stamps from around the world, spanning the 1840s to the 1970s.",
    },
    {
        "name": "Mid-Century Ceramics",
        "type": "general",
        "description": "Studio pottery and production ceramics from the 1940s through 1970s.",
    },
    {
        "name": "Antique Maps & Atlases",
        "type": "general",
        "description": "Hand-engraved and lithographed maps from the 16th to 19th centuries.",
    },
    {
        "name": "Vinyl Records",
        "type": "general",
        "description": "LPs and 45s, mostly jazz and classic rock, original pressings when possible.",
    },
    {
        "name": "Pocket Watches",
        "type": "general",
        "description": "Mechanical pocket watches from American and European makers, 1850-1950.",
    },
]


# ── Item data per collection ─────────────────────────────────────────────────
# Keys: name (required), plus any Item field. Special keys:
#   tags: list[str]        — tag names to attach
#   marks: list[dict]      — Mark dicts (title, description)
#   notes: list[dict]      — ItemNote dicts (title, body)
#   provenance: list[dict] — ProvenanceEntry dicts

STAMPS = [
    {
        "name": "Penny Black",
        "description": "The world's first adhesive postage stamp, issued May 1840.",
        "condition": "good",
        "origin": "United Kingdom",
        "date_era": "1840",
        "acquisition_date": date(2019, 3, 15),
        "acquisition_price": Decimal("2500.00"),
        "acquisition_source": "Christie's auction",
        "estimated_value": Decimal("3200.00"),
        "height_cm": Decimal("2.20"),
        "width_cm": Decimal("1.80"),
        "materials": "Paper, ink",
        "type_fields": {
            "denomination": "1d",
            "color": "Black",
            "catalogue_number": "SG 1",
            "mint_status": "used",
            "perforation": "Imperforate",
            "watermark": "Small Crown",
            "series": "Line-engraved",
            "issue_date": "1840-05-06",
            "country_of_issue": "United Kingdom",
        },
        "tags": ["rare", "vintage", "insured", "appraised", "auction find"],
        "provenance": [
            {
                "owner_name": "Sir Rowland Hill Estate",
                "date_from": "1840",
                "date_to": "1879",
                "notes": "Part of the original presentation sheets",
            },
            {
                "owner_name": "Thomas Keay Tapling",
                "date_from": "1880",
                "date_to": "1913",
            },
        ],
        "notes": [
            {
                "title": "Authentication",
                "body": "Authenticated by the Royal Philatelic Society London in 2018. Certificate on file.",
            },
        ],
    },
    {
        "name": "Inverted Jenny",
        "description": "US 24-cent airmail stamp with inverted center, 1918. A modern reprint/facsimile.",
        "condition": "excellent",
        "origin": "United States",
        "date_era": "1918 (reprint 2013)",
        "acquisition_price": Decimal("45.00"),
        "acquisition_source": "USPS",
        "type_fields": {
            "denomination": "24c",
            "color": "Carmine rose and blue",
            "catalogue_number": "C3a",
            "mint_status": "mint_never_hinged",
            "perforation": "11",
            "country_of_issue": "United States",
        },
        "tags": ["mint condition", "displayed", "framed"],
    },
    {
        "name": "Basel Dove",
        "description": "1845 stamp from the Swiss canton of Basel, featuring a white dove.",
        "condition": "fair",
        "origin": "Switzerland",
        "date_era": "1845",
        "estimated_value": Decimal("1800.00"),
        "type_fields": {
            "denomination": "2½ rappen",
            "color": "Black, crimson, blue",
            "catalogue_number": "Zumstein 8",
            "mint_status": "used",
            "country_of_issue": "Switzerland",
        },
        "tags": ["rare", "vintage", "appraised"],
    },
    {
        "name": "1935 Silver Jubilee Kenya",
        "description": "King George V Silver Jubilee issue, Kenya/Uganda/Tanganyika.",
        "condition": "good",
        "origin": "Kenya",
        "date_era": "1935",
        "type_fields": {
            "denomination": "30c",
            "color": "Black and ultramarine",
            "mint_status": "mint_hinged",
            "series": "Silver Jubilee",
            "issue_date": "1935-05-06",
            "country_of_issue": "Kenya, Uganda & Tanganyika",
        },
        "tags": ["vintage"],
    },
    {
        "name": "Japan 1871 Dragon 48 mon",
        "description": "Early Meiji-era hand-engraved issue featuring a dragon.",
        "condition": "fair",
        "origin": "Japan",
        "date_era": "1871",
        "acquisition_date": date(2020, 11, 2),
        "acquisition_source": "eBay",
        "acquisition_price": Decimal("320.00"),
        "type_fields": {
            "denomination": "48 mon",
            "color": "Brown",
            "catalogue_number": "JSCA 1",
            "mint_status": "used",
            "variety": "Plate I, Position 21",
            "country_of_issue": "Japan",
        },
        "tags": ["rare", "vintage", "auction find"],
    },
    {
        "name": "Sweden Treskilling Yellow",
        "description": "Colour error on Swedish 3-skilling stamp. This is a study reproduction.",
        "condition": "excellent",
        "origin": "Sweden",
        "date_era": "1855 (reproduction 2005)",
        "acquisition_price": Decimal("15.00"),
        "type_fields": {
            "denomination": "3 skilling banco",
            "color": "Yellow (error — should be green)",
            "mint_status": "mint_never_hinged",
            "country_of_issue": "Sweden",
        },
        "tags": ["stored"],
    },
    {
        "name": "India 1854 Half Anna",
        "description": "First issue of British India, lithographed.",
        "condition": "poor",
        "origin": "India",
        "date_era": "1854",
        "type_fields": {
            "denomination": "½ anna",
            "color": "Blue",
            "catalogue_number": "SG 2",
            "mint_status": "used",
            "watermark": "None",
            "country_of_issue": "India",
        },
        "tags": ["vintage", "damaged"],
    },
    {
        "name": "Cape of Good Hope Triangular",
        "description": "Distinctive triangular stamp from the Cape Colony, 1853.",
        "condition": "good",
        "origin": "South Africa",
        "date_era": "1853",
        "acquisition_date": date(2022, 6, 10),
        "acquisition_source": "Spink & Son",
        "acquisition_price": Decimal("680.00"),
        "estimated_value": Decimal("750.00"),
        "type_fields": {
            "denomination": "1d",
            "color": "Red",
            "catalogue_number": "SG 1",
            "mint_status": "used",
            "country_of_issue": "Cape of Good Hope",
        },
        "tags": ["rare", "vintage", "insured", "auction find"],
    },
    {
        "name": "France 1849 Cérès 20c Black",
        "description": "First issue of the French Republic.",
        "condition": "good",
        "origin": "France",
        "date_era": "1849",
        "type_fields": {
            "denomination": "20c",
            "color": "Black",
            "mint_status": "used",
            "issue_date": "1849-01-01",
            "country_of_issue": "France",
        },
        "tags": ["vintage"],
    },
    {
        "name": "US 1869 Pictorials 15c Columbus",
        "description": "Landing of Columbus, type II, from the 1869 pictorial series.",
        "condition": "fair",
        "origin": "United States",
        "date_era": "1869",
        "type_fields": {
            "denomination": "15c",
            "color": "Brown and blue",
            "catalogue_number": "Scott 119",
            "mint_status": "used",
            "series": "1869 Pictorial Issue",
            "country_of_issue": "United States",
        },
        "tags": ["vintage", "displayed"],
    },
    {
        "name": "Mauritius Post Office 2d Blue",
        "description": "Study facsimile of the famous 1847 Mauritius issue.",
        "condition": "excellent",
        "origin": "Mauritius",
        "date_era": "1847 (facsimile 2000)",
        "acquisition_price": Decimal("8.00"),
        "type_fields": {
            "denomination": "2d",
            "color": "Blue",
            "mint_status": "mint_never_hinged",
            "country_of_issue": "Mauritius",
        },
        "tags": ["stored"],
    },
    {
        "name": "Hawaiian Missionaries 2c",
        "description": "1851 Hawaii issue, known as 'Missionaries' because missionaries sent them home.",
        "condition": "poor",
        "origin": "Hawaii",
        "date_era": "1851",
        "estimated_value": Decimal("450.00"),
        "type_fields": {
            "denomination": "2c",
            "color": "Blue",
            "catalogue_number": "Scott 1",
            "mint_status": "used",
            "country_of_issue": "Hawaii",
        },
        "tags": ["rare", "vintage", "damaged", "appraised"],
    },
    {
        "name": "Austrian 1850 9 Kreuzer Blue",
        "description": "First Austrian Empire stamp issue.",
        "condition": "good",
        "origin": "Austria",
        "date_era": "1850",
        "type_fields": {
            "denomination": "9 kr",
            "color": "Blue",
            "mint_status": "used",
            "perforation": "Imperforate",
            "watermark": "BRIEF-MARKE in sheet",
            "country_of_issue": "Austria",
        },
        "tags": ["vintage"],
    },
    {
        "name": "Brazil 1843 Bull's Eye 30 réis",
        "description": "One of the earliest stamps issued outside Europe, second only to Great Britain.",
        "condition": "fair",
        "origin": "Brazil",
        "date_era": "1843",
        "acquisition_date": date(2023, 1, 20),
        "acquisition_source": "Harmers International",
        "acquisition_price": Decimal("1100.00"),
        "type_fields": {
            "denomination": "30 réis",
            "color": "Black",
            "catalogue_number": "Scott 1",
            "mint_status": "used",
            "country_of_issue": "Brazil",
        },
        "tags": ["rare", "vintage", "auction find", "insured"],
    },
    {
        "name": "Russia 1857 10 Kopek",
        "description": "First Russian Empire postage stamp.",
        "condition": "good",
        "origin": "Russia",
        "date_era": "1857",
        "type_fields": {
            "denomination": "10 kopek",
            "color": "Brown and blue",
            "mint_status": "used",
            "perforation": "Imperforate",
            "watermark": "Numeral 1",
            "country_of_issue": "Russia",
        },
        "tags": ["vintage"],
    },
    {
        "name": "New Zealand 1855 Chalon Head 1d",
        "description": "Full-face Queen Victoria portrait, London print.",
        "condition": "good",
        "origin": "New Zealand",
        "date_era": "1855",
        "type_fields": {
            "denomination": "1d",
            "color": "Red",
            "mint_status": "used",
            "perforation": "Imperforate",
            "watermark": "Large Star",
            "country_of_issue": "New Zealand",
        },
        "tags": ["vintage", "estate sale"],
    },
    {
        "name": "Germany 1872 Imperial Eagle 1 Groschen",
        "description": "First stamp of the unified German Empire, small shield design.",
        "condition": "excellent",
        "origin": "Germany",
        "date_era": "1872",
        "type_fields": {
            "denomination": "1 Groschen",
            "color": "Rose",
            "mint_status": "mint_og",
            "perforation": "13½ x 14½",
            "series": "Imperial Eagle, Small Shield",
            "country_of_issue": "Germany",
        },
        "tags": ["vintage", "mint condition"],
    },
    {
        "name": "Canada 1851 Threepenny Beaver",
        "description": "First Canadian stamp, designed by Sandford Fleming.",
        "condition": "fair",
        "origin": "Canada",
        "date_era": "1851",
        "artist_maker": "Sandford Fleming",
        "type_fields": {
            "denomination": "3d",
            "color": "Red",
            "catalogue_number": "Scott 4",
            "mint_status": "used",
            "country_of_issue": "Canada",
        },
        "tags": ["vintage", "rare"],
    },
    {
        "name": "Spain 1850 6 Cuartos",
        "description": "First Spanish postage stamp.",
        "condition": "good",
        "origin": "Spain",
        "date_era": "1850",
        "type_fields": {
            "denomination": "6 cuartos",
            "color": "Black",
            "mint_status": "used",
            "country_of_issue": "Spain",
        },
    },
    {
        "name": "Norway 1855 Oscar I 4 Skilling",
        "description": "First Norwegian stamp, King Oscar I portrait.",
        "condition": "good",
        "origin": "Norway",
        "date_era": "1855",
        "type_fields": {
            "denomination": "4 skilling",
            "color": "Blue",
            "mint_status": "on_piece",
            "country_of_issue": "Norway",
        },
    },
]

CERAMICS = [
    {
        "name": "Russel Wright Iroquois Casual Pitcher",
        "description": "Ice-lip pitcher in Cantaloupe glaze, from the Iroquois Casual China line.",
        "condition": "excellent",
        "artist_maker": "Russel Wright",
        "origin": "United States",
        "date_era": "1946-1966",
        "location": "Display cabinet, shelf 2",
        "height_cm": Decimal("23.50"),
        "width_cm": Decimal("18.00"),
        "depth_cm": Decimal("13.00"),
        "weight_kg": Decimal("0.680"),
        "materials": "Stoneware, glazed",
        "acquisition_date": date(2021, 9, 5),
        "acquisition_price": Decimal("85.00"),
        "acquisition_source": "Brimfield Antique Show",
        "estimated_value": Decimal("120.00"),
        "tags": ["vintage", "displayed", "flea market"],
        "marks": [
            {
                "title": "Backstamp",
                "description": "Raised 'IROQUOIS CASUAL CHINA by Russel Wright' in oval",
            },
        ],
    },
    {
        "name": "Heath Ceramics Rim Dinner Plate",
        "description": "10.5-inch dinner plate in Redwood glaze from Sausalito studio.",
        "condition": "good",
        "artist_maker": "Edith Heath",
        "origin": "United States",
        "date_era": "1950s",
        "materials": "Stoneware",
        "height_cm": Decimal("2.50"),
        "width_cm": Decimal("26.70"),
        "tags": ["vintage", "displayed"],
        "marks": [
            {
                "title": "Impressed mark",
                "description": "'HEATH' impressed into foot ring",
            },
        ],
    },
    {
        "name": "Bitossi Rimini Blu Vase",
        "description": "Cylindrical vase with hand-carved geometric relief in signature blue glaze.",
        "condition": "excellent",
        "artist_maker": "Aldo Londi",
        "origin": "Italy",
        "date_era": "1960s",
        "location": "Living room mantel",
        "height_cm": Decimal("30.00"),
        "width_cm": Decimal("12.00"),
        "materials": "Earthenware, glazed",
        "acquisition_date": date(2020, 7, 18),
        "acquisition_price": Decimal("220.00"),
        "acquisition_source": "1stDibs",
        "estimated_value": Decimal("350.00"),
        "tags": ["vintage", "displayed", "insured", "auction find"],
        "marks": [
            {
                "title": "Base label",
                "description": "Paper label reading 'BITOSSI — MADE IN ITALY' with gold border",
            },
            {
                "title": "Incised number",
                "description": "'727/30' incised into base",
            },
        ],
        "provenance": [
            {
                "owner_name": "Estate of Margaret Loewe",
                "date_from": "1965",
                "date_to": "2019",
                "notes": "Purchased during a trip to Florence, per family records",
            },
        ],
    },
    {
        "name": "Kaj Franck Kilta Creamer",
        "description": "Small cream pitcher in white glaze, part of the iconic Kilta line.",
        "condition": "good",
        "artist_maker": "Kaj Franck",
        "origin": "Finland",
        "date_era": "1953-1974",
        "materials": "Stoneware",
        "height_cm": Decimal("8.00"),
        "tags": ["vintage"],
    },
    {
        "name": "Lucie Rie Sgraffito Bowl",
        "description": "Small footed bowl with sgraffito cross-hatch pattern through manganese glaze.",
        "condition": "excellent",
        "artist_maker": "Dame Lucie Rie",
        "origin": "United Kingdom",
        "date_era": "1960s",
        "height_cm": Decimal("7.50"),
        "width_cm": Decimal("14.00"),
        "weight_kg": Decimal("0.290"),
        "materials": "Porcelain",
        "acquisition_date": date(2018, 11, 30),
        "acquisition_price": Decimal("4200.00"),
        "acquisition_source": "Maak Contemporary Ceramics",
        "estimated_value": Decimal("5500.00"),
        "tags": ["rare", "signed", "insured", "appraised", "displayed"],
        "marks": [
            {
                "title": "LR seal",
                "description": "Impressed 'LR' monogram seal in foot ring",
            },
        ],
        "provenance": [
            {
                "owner_name": "Private London collection",
                "date_from": "1968",
                "date_to": "2015",
            },
            {
                "owner_name": "Maak Contemporary Ceramics",
                "date_from": "2015",
                "date_to": "2018",
                "notes": "Gallery consignment, exhibited in 'Post-War Studio Ceramics' show 2017",
            },
        ],
        "notes": [
            {
                "title": "Condition report",
                "body": "No chips, cracks, or repairs. Minor surface scratching on base from use. Glaze in excellent condition with no crazing.",
            },
        ],
    },
    {
        "name": "Gustavsberg Argenta Tray",
        "description": "Green-glazed stoneware tray with applied silver fish motif.",
        "condition": "good",
        "artist_maker": "Wilhelm Kåge",
        "origin": "Sweden",
        "date_era": "1940s",
        "materials": "Stoneware, silver overlay",
        "width_cm": Decimal("22.00"),
        "height_cm": Decimal("3.00"),
        "tags": ["vintage", "signed", "displayed"],
        "marks": [
            {
                "title": "Anchor mark",
                "description": "Impressed Gustavsberg anchor with 'ARGENTA' and hand-painted model number",
            },
        ],
    },
    {
        "name": "Marcello Fantoni Brutalist Sculpture Vase",
        "description": "Tall slab-built vase with applied abstract figures, dark brown matte glaze.",
        "condition": "fair",
        "artist_maker": "Marcello Fantoni",
        "origin": "Italy",
        "date_era": "1960s",
        "height_cm": Decimal("42.00"),
        "width_cm": Decimal("16.00"),
        "depth_cm": Decimal("14.00"),
        "materials": "Stoneware",
        "tags": ["vintage", "signed", "needs restoration"],
        "notes": [
            {
                "title": "Damage note",
                "body": "Hairline crack on back near base, approximately 4cm long. Stable — does not appear to be worsening. Professional restoration recommended if piece is to be used for flowers.",
            },
        ],
    },
    {
        "name": "Rörstrand Pop Sugar Bowl",
        "description": "Sugar bowl with lid from the 'Pop' line in orange and brown.",
        "condition": "good",
        "origin": "Sweden",
        "date_era": "1970s",
        "materials": "Earthenware, glazed",
        "tags": ["vintage", "stored"],
    },
    {
        "name": "Peter Voulkos Stacked Vessel",
        "description": "Large wood-fired stoneware vessel with torn and stacked forms.",
        "condition": "excellent",
        "artist_maker": "Peter Voulkos",
        "origin": "United States",
        "date_era": "1978",
        "height_cm": Decimal("55.00"),
        "width_cm": Decimal("35.00"),
        "weight_kg": Decimal("8.500"),
        "materials": "Stoneware, wood-fired",
        "acquisition_date": date(2017, 5, 12),
        "acquisition_price": Decimal("28000.00"),
        "acquisition_source": "Frank Lloyd Gallery",
        "estimated_value": Decimal("42000.00"),
        "tags": ["rare", "signed", "insured", "appraised", "displayed"],
        "marks": [
            {
                "title": "Signature",
                "description": "'VOULKOS' scratched into wet clay on base",
            },
        ],
        "provenance": [
            {
                "owner_name": "Peter Voulkos Studio",
                "date_from": "1978",
                "date_to": "1978",
            },
            {
                "owner_name": "Daniel Jacobs collection",
                "date_from": "1978",
                "date_to": "2016",
                "notes": "Purchased directly from the artist during Montana studio visit",
            },
            {
                "owner_name": "Frank Lloyd Gallery",
                "date_from": "2016",
                "date_to": "2017",
            },
        ],
        "notes": [
            {
                "title": "Insurance",
                "body": "Insured under fine art policy FA-2024-1182. Appraised by Bonhams 2023 at $42,000.",
            },
            {
                "title": "Display notes",
                "body": "Sits on custom steel pedestal (24in height). Must be moved by two people — weight exceeds 8kg. Keep away from high-traffic areas.",
            },
        ],
    },
    {
        "name": "Eva Zeisel Town and Country Salt & Pepper",
        "description": "Organic-form nesting salt and pepper shakers in Dusk Blue.",
        "condition": "excellent",
        "artist_maker": "Eva Zeisel",
        "origin": "United States",
        "date_era": "1947",
        "height_cm": Decimal("10.00"),
        "materials": "Earthenware, glazed",
        "tags": ["vintage", "mint condition", "displayed"],
        "marks": [
            {
                "title": "Backstamp",
                "description": "'Red Wing TOWN AND COUNTRY Designed by Eva Zeisel' printed in red",
            },
        ],
    },
    {
        "name": "Stig Lindberg Faience Leaf Dish",
        "description": "Hand-painted leaf-shaped dish with striped pattern in green and white.",
        "condition": "good",
        "artist_maker": "Stig Lindberg",
        "origin": "Sweden",
        "date_era": "1950s",
        "width_cm": Decimal("24.00"),
        "materials": "Faience",
        "tags": ["vintage", "signed"],
    },
    {
        "name": "Arabia Finland Pastoraali Plate",
        "description": "Dinner plate from the Pastoraali series with pastoral scene in blue.",
        "condition": "good",
        "origin": "Finland",
        "date_era": "1960s",
        "materials": "Stoneware",
    },
    {
        "name": "Gertrud & Otto Natzler Crater Glaze Bowl",
        "description": "Thrown bowl with volcanic crater glaze in deep blue-green.",
        "condition": "excellent",
        "artist_maker": "Gertrud & Otto Natzler",
        "origin": "United States",
        "date_era": "1956",
        "height_cm": Decimal("8.50"),
        "width_cm": Decimal("19.00"),
        "materials": "Earthenware",
        "acquisition_price": Decimal("7500.00"),
        "acquisition_source": "Los Angeles Modern Auctions",
        "estimated_value": Decimal("9000.00"),
        "tags": ["rare", "signed", "insured", "appraised", "auction find"],
        "marks": [
            {
                "title": "Paper label",
                "description": "Original Natzler studio label with handwritten glaze code 'N562'",
            },
        ],
    },
    {
        "name": "Hornsea Fauna Sugar Storage Jar",
        "description": "Cylindrical storage jar with embossed rabbit motif, matte brown glaze.",
        "condition": "good",
        "origin": "United Kingdom",
        "date_era": "1960s",
        "height_cm": Decimal("16.00"),
        "materials": "Earthenware",
        "tags": ["vintage", "stored"],
    },
    {
        "name": "Robert Picault Fish Plate",
        "description": "Hand-painted plate with stylized fish in polychrome glaze.",
        "condition": "fair",
        "artist_maker": "Robert Picault",
        "origin": "France",
        "date_era": "1950s",
        "width_cm": Decimal("25.00"),
        "materials": "Earthenware, glazed",
        "tags": ["vintage", "needs restoration"],
    },
    {
        "name": "Murano Glass Paperweight",
        "description": "Millefiori paperweight with concentric rings of canes in red, white, and blue.",
        "condition": "excellent",
        "origin": "Murano, Italy",
        "date_era": "1960s",
        "height_cm": Decimal("5.00"),
        "width_cm": Decimal("7.50"),
        "weight_kg": Decimal("0.420"),
        "materials": "Glass",
        "tags": ["vintage", "displayed", "gift"],
    },
    {
        "name": "Bakelite Radio — Emerson Patriot",
        "description": "1940 Emerson model 400 'Patriot' catalin radio in marbled red.",
        "condition": "fair",
        "artist_maker": "Emerson Radio",
        "origin": "United States",
        "date_era": "1940",
        "height_cm": Decimal("18.00"),
        "width_cm": Decimal("25.00"),
        "depth_cm": Decimal("14.00"),
        "weight_kg": Decimal("2.100"),
        "materials": "Catalin (Bakelite), metal chassis, vacuum tubes",
        "estimated_value": Decimal("1200.00"),
        "tags": ["vintage", "rare", "needs restoration", "appraised"],
        "notes": [
            {
                "title": "Electrical safety",
                "body": "Has NOT been re-capped. Do not plug in without replacing electrolytic capacitors — fire risk. Original power cord is frayed and must be replaced.",
            },
        ],
    },
]

MAPS = [
    {
        "name": "Ortelius Typus Orbis Terrarum",
        "description": "World map from Theatrum Orbis Terrarum, the first modern atlas.",
        "condition": "fair",
        "artist_maker": "Abraham Ortelius",
        "origin": "Antwerp, Low Countries",
        "date_era": "1570",
        "height_cm": Decimal("35.00"),
        "width_cm": Decimal("50.00"),
        "materials": "Laid paper, hand-colored copper engraving",
        "acquisition_date": date(2016, 10, 8),
        "acquisition_price": Decimal("6800.00"),
        "acquisition_source": "Sotheby's",
        "estimated_value": Decimal("8500.00"),
        "tags": ["rare", "vintage", "framed", "insured", "appraised", "auction find"],
        "provenance": [
            {
                "owner_name": "Bibliothèque Municipale de Lyon",
                "date_from": "1600s",
                "date_to": "1952",
                "notes": "Deaccessioned in 1952 as a duplicate",
            },
            {
                "owner_name": "Henri Schiller, dealer",
                "date_from": "1952",
                "date_to": "1960",
            },
        ],
        "notes": [
            {
                "title": "Conservation",
                "body": "Conserved in 2017 by Northeast Document Conservation Center. Old tape removed from verso, flattened, deacidified. Housed in acid-free mat with UV-filtering glazing.",
            },
        ],
    },
    {
        "name": "Blaeu Nova Totius Terrarum",
        "description": "Double-hemisphere world map with allegorical borders.",
        "condition": "good",
        "artist_maker": "Joan Blaeu",
        "origin": "Amsterdam, Dutch Republic",
        "date_era": "1664",
        "height_cm": Decimal("41.00"),
        "width_cm": Decimal("54.00"),
        "materials": "Laid paper, hand-colored copper engraving",
        "location": "Study, north wall",
        "tags": ["vintage", "framed", "displayed"],
    },
    {
        "name": "Speed Map of Virginia",
        "description": "John Speed's map of 'Virginia and Maryland', with Smith's explorations.",
        "condition": "good",
        "artist_maker": "John Speed",
        "origin": "London, England",
        "date_era": "1676",
        "height_cm": Decimal("39.00"),
        "width_cm": Decimal("51.00"),
        "materials": "Laid paper, hand-colored copper engraving",
        "tags": ["vintage", "framed"],
    },
    {
        "name": "Homann Map of the Americas",
        "description": "Americae Mappa Generalis showing North and South America.",
        "condition": "good",
        "artist_maker": "Johann Baptist Homann",
        "origin": "Nuremberg, Germany",
        "date_era": "1746",
        "height_cm": Decimal("49.00"),
        "width_cm": Decimal("58.00"),
        "materials": "Laid paper, hand-colored copper engraving",
        "acquisition_price": Decimal("950.00"),
        "acquisition_source": "The Old Print Shop, NYC",
        "tags": ["vintage", "framed", "displayed"],
    },
    {
        "name": "Cassini Map of the Moon",
        "description": "Giovanni Cassini's detailed lunar map, one of the earliest accurate charts.",
        "condition": "fair",
        "artist_maker": "Giovanni Cassini",
        "origin": "Paris, France",
        "date_era": "1679",
        "height_cm": Decimal("46.00"),
        "width_cm": Decimal("46.00"),
        "materials": "Laid paper, copper engraving",
        "tags": ["rare", "vintage", "framed", "insured"],
        "notes": [
            {
                "title": "Framing",
                "body": "Reframed in 2020 with museum glass. Previous frame had acidic mat causing foxing along edges.",
            },
        ],
    },
    {
        "name": "Mercator Map of the World 1569 (facsimile)",
        "description": "High-quality facsimile of the famous 1569 Mercator projection.",
        "condition": "excellent",
        "artist_maker": "Gerardus Mercator (facsimile)",
        "origin": "United Kingdom",
        "date_era": "1569 (facsimile 1990)",
        "height_cm": Decimal("131.00"),
        "width_cm": Decimal("198.00"),
        "materials": "Acid-free paper, offset lithograph",
        "acquisition_price": Decimal("45.00"),
        "tags": ["displayed"],
    },
    {
        "name": "Colton Atlas Map of Texas",
        "description": "G.W. & C.B. Colton hand-colored atlas page showing Texas with county divisions.",
        "condition": "good",
        "origin": "New York, United States",
        "date_era": "1855",
        "height_cm": Decimal("38.00"),
        "width_cm": Decimal("30.00"),
        "materials": "Wove paper, hand-colored lithograph",
        "tags": ["vintage", "stored"],
    },
    {
        "name": "Bowles Pocket Atlas of England",
        "description": "Miniature folding atlas of English counties, original leather case.",
        "condition": "fair",
        "artist_maker": "Carington Bowles",
        "origin": "London, England",
        "date_era": "1785",
        "height_cm": Decimal("12.00"),
        "width_cm": Decimal("8.00"),
        "depth_cm": Decimal("2.00"),
        "weight_kg": Decimal("0.150"),
        "materials": "Paper, leather, hand-colored copper engravings",
        "acquisition_date": date(2023, 9, 14),
        "acquisition_source": "Estate sale, Oxfordshire",
        "acquisition_price": Decimal("380.00"),
        "tags": ["vintage", "estate sale", "needs restoration"],
        "notes": [
            {
                "title": "Condition issues",
                "body": "Leather case cracked along spine. Several map sheets have small tears at folds. No losses. Candidate for professional book conservation.",
            },
        ],
    },
    {
        "name": "Piranesi Plan of Rome",
        "description": "Large-format engraved plan of ancient Rome from Le Antichità Romane.",
        "condition": "good",
        "artist_maker": "Giovanni Battista Piranesi",
        "origin": "Rome, Italy",
        "date_era": "1756",
        "height_cm": Decimal("53.00"),
        "width_cm": Decimal("76.00"),
        "materials": "Laid paper, etching",
        "estimated_value": Decimal("3200.00"),
        "tags": ["rare", "vintage", "framed", "appraised"],
    },
    {
        "name": "Sanborn Fire Insurance Map — Lower Manhattan",
        "description": "Sheet 1 of the 1905 Sanborn atlas showing building footprints and construction.",
        "condition": "good",
        "origin": "New York, United States",
        "date_era": "1905",
        "height_cm": Decimal("64.00"),
        "width_cm": Decimal("53.00"),
        "materials": "Paper, color lithograph",
        "tags": ["vintage"],
    },
    {
        "name": "Jaillot Carte de l'Asie",
        "description": "Large decorative map of Asia with elaborate cartouche.",
        "condition": "good",
        "artist_maker": "Alexis-Hubert Jaillot",
        "origin": "Paris, France",
        "date_era": "1692",
        "height_cm": Decimal("58.00"),
        "width_cm": Decimal("88.00"),
        "materials": "Laid paper, hand-colored copper engraving",
        "tags": ["vintage", "framed"],
    },
    {
        "name": "Catalan Atlas Fragment (facsimile)",
        "description": "Panel from the 1375 Catalan Atlas showing the eastern Mediterranean.",
        "condition": "excellent",
        "origin": "Spain",
        "date_era": "1375 (facsimile 2008)",
        "materials": "Parchment-style paper, offset print",
        "acquisition_price": Decimal("35.00"),
    },
    {
        "name": "Japanese Woodblock Print — Hiroshige",
        "description": "Sudden Shower over Shin-Ōhashi Bridge, from One Hundred Famous Views of Edo.",
        "condition": "good",
        "artist_maker": "Utagawa Hiroshige",
        "origin": "Japan",
        "date_era": "1857",
        "height_cm": Decimal("36.00"),
        "width_cm": Decimal("25.00"),
        "materials": "Washi paper, woodblock print",
        "acquisition_date": date(2020, 2, 14),
        "acquisition_price": Decimal("1600.00"),
        "acquisition_source": "Scholten Japanese Art",
        "tags": ["vintage", "framed", "displayed", "insured"],
    },
]

RECORDS = [
    {
        "name": "Miles Davis — Kind of Blue",
        "description": "1959 Columbia mono pressing, deep groove '6-eye' label.",
        "condition": "good",
        "artist_maker": "Miles Davis",
        "origin": "United States",
        "date_era": "1959",
        "location": "Record shelf A, Jazz",
        "acquisition_date": date(2015, 4, 22),
        "acquisition_price": Decimal("280.00"),
        "acquisition_source": "Princeton Record Exchange",
        "estimated_value": Decimal("450.00"),
        "materials": "Vinyl, cardboard sleeve",
        "tags": ["vintage", "rare", "first edition", "insured", "displayed"],
        "notes": [
            {
                "title": "Pressing details",
                "body": "CL 1355, mono, deep groove both sides. Matrix: XSM 43611-1A / XSM 43612-1A. Plays with minimal surface noise.",
            },
        ],
    },
    {
        "name": "The Beatles — Abbey Road",
        "description": "UK first pressing with misaligned Apple logo on rear.",
        "condition": "good",
        "artist_maker": "The Beatles",
        "origin": "United Kingdom",
        "date_era": "1969",
        "location": "Record shelf A, Rock",
        "acquisition_price": Decimal("350.00"),
        "acquisition_source": "Discogs",
        "tags": ["vintage", "first edition", "insured"],
    },
    {
        "name": "John Coltrane — A Love Supreme",
        "description": "Impulse! orange/black label, original Van Gelder pressing.",
        "condition": "excellent",
        "artist_maker": "John Coltrane",
        "origin": "United States",
        "date_era": "1965",
        "location": "Record shelf A, Jazz",
        "acquisition_price": Decimal("190.00"),
        "tags": ["vintage", "first edition"],
    },
    {
        "name": "Joni Mitchell — Blue",
        "description": "Reprise first pressing, textured gatefold sleeve.",
        "condition": "good",
        "artist_maker": "Joni Mitchell",
        "origin": "United States",
        "date_era": "1971",
        "tags": ["vintage"],
    },
    {
        "name": "Thelonious Monk — Brilliant Corners",
        "description": "Riverside deep groove pressing with Bill Grauer credit on back.",
        "condition": "fair",
        "artist_maker": "Thelonious Monk",
        "origin": "United States",
        "date_era": "1957",
        "acquisition_source": "Flea market, Brooklyn",
        "acquisition_price": Decimal("12.00"),
        "estimated_value": Decimal("150.00"),
        "tags": ["vintage", "flea market"],
    },
    {
        "name": "Pink Floyd — The Dark Side of the Moon",
        "description": "UK first pressing with solid blue triangle on labels, two posters and stickers.",
        "condition": "excellent",
        "artist_maker": "Pink Floyd",
        "origin": "United Kingdom",
        "date_era": "1973",
        "location": "Record shelf B, Rock",
        "tags": ["vintage", "first edition", "displayed"],
        "notes": [
            {
                "title": "Inserts",
                "body": "Both original posters present and in good condition. Sticker sheet is missing.",
            },
        ],
    },
    {
        "name": "Nina Simone — I Put a Spell on You",
        "description": "Philips stereo pressing, Dutch import.",
        "condition": "good",
        "artist_maker": "Nina Simone",
        "origin": "Netherlands",
        "date_era": "1965",
        "tags": ["vintage"],
    },
    {
        "name": "Kraftwerk — Autobahn",
        "description": "Original German Vertigo pressing, swirl label.",
        "condition": "good",
        "artist_maker": "Kraftwerk",
        "origin": "Germany",
        "date_era": "1974",
        "acquisition_price": Decimal("75.00"),
        "acquisition_source": "Amoeba Music, SF",
        "tags": ["vintage", "rare"],
    },
    {
        "name": "Stevie Wonder — Songs in the Key of Life",
        "description": "Double LP with bonus 7-inch EP and booklet. Tamla original.",
        "condition": "good",
        "artist_maker": "Stevie Wonder",
        "origin": "United States",
        "date_era": "1976",
        "tags": ["vintage"],
    },
    {
        "name": "Radiohead — OK Computer",
        "description": "Parlophone UK first pressing, NODATA 02.",
        "condition": "excellent",
        "artist_maker": "Radiohead",
        "origin": "United Kingdom",
        "date_era": "1997",
        "acquisition_price": Decimal("60.00"),
        "tags": ["first edition"],
    },
    {
        "name": "Charles Mingus — The Black Saint and the Sinner Lady",
        "description": "Impulse! mono pressing with Van Gelder stamp in dead wax.",
        "condition": "good",
        "artist_maker": "Charles Mingus",
        "origin": "United States",
        "date_era": "1963",
        "location": "Record shelf A, Jazz",
        "tags": ["vintage"],
    },
    {
        "name": "Sade — Diamond Life",
        "description": "Epic UK first pressing.",
        "condition": "excellent",
        "artist_maker": "Sade",
        "origin": "United Kingdom",
        "date_era": "1984",
    },
    {
        "name": "Talking Heads — Remain in Light",
        "description": "Sire original pressing with computer-designed sleeve.",
        "condition": "good",
        "artist_maker": "Talking Heads",
        "origin": "United States",
        "date_era": "1980",
        "tags": ["vintage"],
    },
    {
        "name": "Bill Evans — Waltz for Debby",
        "description": "Riverside deep groove mono pressing, recorded live at the Village Vanguard.",
        "condition": "fair",
        "artist_maker": "Bill Evans Trio",
        "origin": "United States",
        "date_era": "1962",
        "acquisition_date": date(2022, 8, 3),
        "acquisition_price": Decimal("420.00"),
        "acquisition_source": "Jazz Record Center, NYC",
        "tags": ["vintage", "rare", "first edition", "auction find"],
    },
    {
        "name": "Buena Vista Social Club — S/T",
        "description": "World Circuit original 2LP pressing.",
        "condition": "excellent",
        "artist_maker": "Buena Vista Social Club",
        "origin": "United Kingdom",
        "date_era": "1997",
        "acquisition_price": Decimal("25.00"),
        "tags": ["displayed"],
    },
]

WATCHES = [
    {
        "name": "Waltham Model 1883 Railroad Grade",
        "description": "18-size open-face railroad pocket watch, lever-set, Appleton Tracy movement.",
        "condition": "good",
        "artist_maker": "American Waltham Watch Co.",
        "origin": "United States",
        "date_era": "1898",
        "location": "Watch case, drawer 1",
        "height_cm": Decimal("6.20"),
        "width_cm": Decimal("5.40"),
        "depth_cm": Decimal("1.50"),
        "weight_kg": Decimal("0.135"),
        "materials": "Gold-filled case, nickel movement",
        "acquisition_date": date(2019, 12, 1),
        "acquisition_price": Decimal("320.00"),
        "acquisition_source": "NAWCC regional mart",
        "estimated_value": Decimal("400.00"),
        "tags": ["vintage", "insured", "displayed"],
        "marks": [
            {
                "title": "Case mark",
                "description": "Inside case back: 'WARRANTED 20 YEARS / KEYSTONE WATCH CASE CO.' with star logo",
            },
            {
                "title": "Movement serial",
                "description": "Serial #8,542,116 on movement plate. 17 jewels, adjusted.",
            },
        ],
        "notes": [
            {
                "title": "Service history",
                "body": "Serviced by James Whitaker, NAWCC member, in January 2020. Cleaned, oiled, regulated. Running within 15 seconds/day.",
            },
        ],
    },
    {
        "name": "Elgin B.W. Raymond 21J",
        "description": "16-size railroad-grade pocket watch, 21 jewels, adjusted 5 positions.",
        "condition": "excellent",
        "artist_maker": "Elgin National Watch Co.",
        "origin": "United States",
        "date_era": "1925",
        "location": "Watch case, drawer 1",
        "height_cm": Decimal("5.50"),
        "width_cm": Decimal("5.00"),
        "depth_cm": Decimal("1.30"),
        "weight_kg": Decimal("0.115"),
        "materials": "White gold-filled case, nickel movement",
        "tags": ["vintage", "mint condition", "displayed"],
        "marks": [
            {
                "title": "Movement engraving",
                "description": "'B.W. Raymond / Elgin Natl. Watch Co.' on bridge. Serial #28,400,215.",
            },
        ],
    },
    {
        "name": "Omega Pocket Watch Cal. 38.5L",
        "description": "Slim Art Deco open-face pocket watch in 14K gold case.",
        "condition": "good",
        "artist_maker": "Omega",
        "origin": "Switzerland",
        "date_era": "1935",
        "weight_kg": Decimal("0.068"),
        "materials": "14K gold case, gilded movement",
        "acquisition_price": Decimal("850.00"),
        "acquisition_source": "Chrono24",
        "estimated_value": Decimal("1100.00"),
        "tags": ["vintage", "insured", "appraised"],
        "marks": [
            {
                "title": "Hallmark",
                "description": "Swiss 14K gold hallmark (squirrel) inside case back with Omega Ω logo",
            },
        ],
    },
    {
        "name": "Illinois Bunn Special 60-hour",
        "description": "16-size 21-jewel railroad watch with 60-hour mainspring, Bunn Special grade.",
        "condition": "good",
        "artist_maker": "Illinois Watch Co.",
        "origin": "United States",
        "date_era": "1929",
        "materials": "10K gold-filled case, nickel movement",
        "tags": ["vintage", "rare"],
    },
    {
        "name": "Patek Philippe Open-Face",
        "description": "18K gold open-face dress watch with enamel dial, stem-wind.",
        "condition": "excellent",
        "artist_maker": "Patek Philippe & Co.",
        "origin": "Switzerland",
        "date_era": "1905",
        "weight_kg": Decimal("0.082"),
        "materials": "18K gold case, enamel dial, nickel movement",
        "acquisition_date": date(2015, 6, 20),
        "acquisition_price": Decimal("12500.00"),
        "acquisition_source": "Antiquorum, Geneva",
        "estimated_value": Decimal("18000.00"),
        "tags": ["rare", "vintage", "insured", "appraised", "signed", "auction find"],
        "marks": [
            {
                "title": "Case hallmark",
                "description": "Geneva 18K gold hallmark (owl) with Patek Philippe 'PP' stamp inside case back",
            },
            {
                "title": "Movement engraving",
                "description": "'Patek Philippe & Co. / Genève / No. 168,432' engraved on movement. 18 jewels, wolf-tooth winding.",
            },
        ],
        "provenance": [
            {
                "owner_name": "Originally retailed by Shreve & Co., San Francisco",
                "date_from": "1905",
                "date_to": "Unknown",
                "notes": "Shreve & Co. retailer hallmark on case",
            },
        ],
        "notes": [
            {
                "title": "Authentication",
                "body": "Extract from Patek Philippe archives confirming manufacture in 1905, 18K gold case, enamel dial. Extract number PP-2015-04421.",
            },
        ],
    },
    {
        "name": "Hamilton 992B Railway Special",
        "description": "16-size 21-jewel railroad pocket watch, the most common American railroad watch.",
        "condition": "good",
        "artist_maker": "Hamilton Watch Co.",
        "origin": "United States",
        "date_era": "1942",
        "materials": "Gold-filled case, nickel movement",
        "location": "Watch case, drawer 2",
        "tags": ["vintage", "displayed"],
    },
    {
        "name": "Longines Silver Hunter Case",
        "description": "Full hunter-case pocket watch in 800 silver with engine-turned decoration.",
        "condition": "fair",
        "artist_maker": "Longines",
        "origin": "Switzerland",
        "date_era": "1910",
        "weight_kg": Decimal("0.098"),
        "materials": "800 silver case, gilded movement",
        "acquisition_source": "Inherited from grandfather",
        "tags": ["vintage", "inherited", "needs restoration"],
        "notes": [
            {
                "title": "Family history",
                "body": "Carried by my grandfather during WWI. Case has dents and the crystal is chipped. Mainspring is broken — does not run. Keeping as-is for sentimental value.",
            },
        ],
    },
    {
        "name": "South Bend Studebaker 323",
        "description": "16-size 17-jewel pocket watch, Studebaker grade, Art Deco case.",
        "condition": "good",
        "artist_maker": "South Bend Watch Co.",
        "origin": "United States",
        "date_era": "1929",
        "materials": "Gold-filled case, nickel movement",
    },
    {
        "name": "Chinese Duplex Escapement Watch",
        "description": "Floral-enamel case pocket watch made for the Chinese market, duplex escapement.",
        "condition": "fair",
        "origin": "Switzerland (made for China)",
        "date_era": "1830s",
        "weight_kg": Decimal("0.095"),
        "materials": "Gilt brass case, enamel, gilded movement",
        "estimated_value": Decimal("2200.00"),
        "tags": ["rare", "vintage", "appraised", "stored"],
        "marks": [
            {
                "title": "Enamel work",
                "description": "Polychrome floral enamel on both case covers. Minor enamel loss on hinge side.",
            },
        ],
    },
    {
        "name": "Howard Series 11 Railroad Chronometer",
        "description": "16-size 21-jewel railroad watch, one of the finest American movements.",
        "condition": "excellent",
        "artist_maker": "E. Howard Watch Co.",
        "origin": "United States",
        "date_era": "1915",
        "materials": "14K gold case, nickel movement",
        "acquisition_date": date(2021, 3, 28),
        "acquisition_price": Decimal("1800.00"),
        "acquisition_source": "Sotheby's online",
        "estimated_value": Decimal("2500.00"),
        "tags": ["rare", "vintage", "insured", "auction find"],
    },
    {
        "name": "Victorian Mourning Brooch",
        "description": "Black jet brooch with carved floral border and woven hair under glass.",
        "condition": "fair",
        "origin": "United Kingdom",
        "date_era": "1870s",
        "height_cm": Decimal("4.00"),
        "width_cm": Decimal("3.50"),
        "materials": "Whitby jet, glass, human hair",
        "tags": ["vintage", "inherited", "stored"],
    },
    {
        "name": "Art Deco Cigarette Case",
        "description": "Silver and enamel cigarette case with geometric black and red design.",
        "condition": "good",
        "origin": "Austria",
        "date_era": "1925",
        "materials": "Sterling silver, enamel",
        "weight_kg": Decimal("0.110"),
        "acquisition_source": "Estate sale, Vienna",
        "tags": ["vintage", "estate sale"],
        "marks": [
            {
                "title": "Silver hallmark",
                "description": "Austrian 935 silver hallmark (Diana head) with maker's mark 'GH' in lozenge",
            },
        ],
    },
]


# ── Seeding logic ────────────────────────────────────────────────────────────

ITEM_FIELDS = {
    "name",
    "description",
    "condition",
    "location",
    "acquisition_date",
    "acquisition_price",
    "acquisition_source",
    "estimated_value",
    "artist_maker",
    "origin",
    "date_era",
    "height_cm",
    "width_cm",
    "depth_cm",
    "weight_kg",
    "materials",
    "type_fields",
}


async def seed(email: str, clear: bool) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.unique().scalar_one_or_none()
        if not user:
            print(f"Error: no user found with email '{email}'")
            sys.exit(1)

        user_id = str(user.id)
        print(f"Found user: {email} (id: {user_id})")

        if clear:
            print("Clearing existing seed data...")
            await session.execute(delete(Item).where(Item.user_id == user_id))
            await session.execute(delete(Collection).where(Collection.user_id == user_id))
            await session.execute(delete(Tag).where(Tag.user_id == user_id))
            await session.commit()
            print("Cleared.")

        # ── Tags ──
        tag_map: dict[str, Tag] = {}
        for name in TAG_NAMES:
            tag = Tag(id=uid(), user_id=user_id, name=name)
            session.add(tag)
            tag_map[name] = tag
        await session.flush()
        print(f"Created {len(tag_map)} tags")

        # ── Collections + items ──
        all_items_data = [
            (COLLECTIONS[0], STAMPS),
            (COLLECTIONS[1], CERAMICS),
            (COLLECTIONS[2], MAPS),
            (COLLECTIONS[3], RECORDS),
            (COLLECTIONS[4], WATCHES),
        ]

        total_items = 0
        total_marks = 0
        total_notes = 0
        total_provenance = 0

        for coll_data, items_data in all_items_data:
            coll = Collection(
                id=uid(),
                user_id=user_id,
                name=coll_data["name"],
                type=coll_data["type"],
                description=coll_data.get("description"),
            )
            session.add(coll)
            await session.flush()

            for item_data in items_data:
                item_kwargs = {k: v for k, v in item_data.items() if k in ITEM_FIELDS}
                item = Item(
                    id=uid(),
                    user_id=user_id,
                    collection_id=coll.id,
                    **item_kwargs,
                )
                session.add(item)
                await session.flush()

                # Tags
                for tag_name in item_data.get("tags", []):
                    await session.execute(
                        item_tags.insert().values(item_id=item.id, tag_id=tag_map[tag_name].id)
                    )

                # Marks
                for mark_data in item_data.get("marks", []):
                    mark = Mark(id=uid(), item_id=item.id, **mark_data)
                    session.add(mark)
                    total_marks += 1

                # Notes
                for note_data in item_data.get("notes", []):
                    note = ItemNote(id=uid(), item_id=item.id, **note_data)
                    session.add(note)
                    total_notes += 1

                # Provenance
                for prov_data in item_data.get("provenance", []):
                    entry = ProvenanceEntry(id=uid(), item_id=item.id, **prov_data)
                    session.add(entry)
                    total_provenance += 1

                total_items += 1

            print(f"  Collection '{coll.name}': {len(items_data)} items")

        await session.commit()

        print("\nDone! Seeded:")
        print(f"  {len(COLLECTIONS)} collections")
        print(f"  {total_items} items")
        print(f"  {len(tag_map)} tags")
        print(f"  {total_marks} marks")
        print(f"  {total_notes} notes")
        print(f"  {total_provenance} provenance entries")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the database with test data.")
    parser.add_argument("--email", required=True, help="Email of the user to assign data to")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all existing items, collections, and tags for this user first",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.email, args.clear))
