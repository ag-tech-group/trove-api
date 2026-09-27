from decimal import Decimal

import pytest

from app.imports.catalogit import ImportFileError, plan_import, read_entries, read_media_index
from tests.catalogit_factory import entries_json, entries_zip, entry, media_csv


def _plan(*entries, media=()):
    return plan_import(list(entries), read_media_index(media_csv(list(media))))


def _notes(item) -> dict[str, str]:
    return {note.title: note.body for note in item.notes}


def test_maps_what_has_a_column():
    raw = entry(
        **{
            "Entry/Object ID": "A-01",
            "Description": "A small silver caddy.",
            "Acquisition": {
                "Acquired From": "Estate sale",
                "Acquisition Method": "Bought",
                "Amount Paid": "$1,200.00",
                "Date": "1994",
                "Place": "Springfield",
            },
            "Dimensions": {"Height": "15 in", "Diameter": "3-1/2 in"},
            "Made/Created": {
                "Artist Information": {"Artist": "Unknown maker"},
                "Date made": "1885 - 1920",
                "Place": "England",
            },
            "Materials": {"Material": "Silver"},
            "Condition": {"Overall Condition": "Excellent"},
            "Location": {"Location": ["Study", "Shelf 2"]},
        }
    )

    (item,) = _plan(raw).items

    assert item.fields == {
        "name": "Tea caddy",
        "reference_number": "A-01",
        "description": "A small silver caddy.",
        "acquisition_source": "Estate sale",
        "acquisition_method": "purchase",
        "acquisition_price": Decimal("1200.00"),
        "acquisition_date": "1994",
        "acquisition_place": "Springfield",
        "height_cm": Decimal("38.10"),
        "diameter_cm": Decimal("8.89"),
        "artist_maker": "Unknown maker",
        "date_era": "1885 - 1920",
        "origin": "England",
        "materials": "Silver",
        "condition": "excellent",
        "location": "Study; Shelf 2",
    }
    assert item.notes == []


def test_valuations_become_records_and_the_latest_is_the_current_value():
    raw = entry(
        Valuations=[
            {
                "Value": "$250.00",
                "Date": "August 16, 2025",
                "Estimator": "Appraiser B",
                "Valuation Type": "Estimate",
            },
            {"Value": "$100.00", "Date": "March 5, 2019", "Notes": "For insurance"},
        ]
    )

    (item,) = _plan(raw).items

    assert [(v.value, v.valued_on) for v in item.valuations] == [
        (Decimal("250.00"), "2025-08-16"),
        (Decimal("100.00"), "2019-03-05"),
    ]
    assert item.valuations[0].appraiser == "Appraiser B"
    assert item.valuations[0].valuation_type == "Estimate"
    assert item.valuations[1].notes == "For insurance"
    assert item.fields["estimated_value"] == Decimal("250.00")


def test_what_has_no_column_is_a_note_titled_by_its_section():
    raw = entry(
        **{
            "Glassware Details": {"Technique": "Blown", "Notes": "Iridescent"},
            "Acquisition": {"Notes": "From a dealer's stall"},
            "Other Names and Numbers": {"Other Names": {"Other Name": "Bride's bowl"}},
            "Colour Scheme": "Blue",
        }
    )

    notes = _notes(_plan(raw).items[0])

    assert notes["Glassware Details"] == "Technique: Blown\nNotes: Iridescent"
    assert notes["Acquisition"] == "Notes: From a dealer's stall"
    assert notes["Other Names and Numbers"] == "Other Names › Other Name: Bride's bowl"
    assert notes["Other details"] == "Colour Scheme: Blue"


def test_what_cannot_be_read_is_kept_and_flagged():
    raw = entry(
        **{
            "Entry/Object ID": "A-02",
            "Acquisition": {"Amount Paid": "€500", "Date": "circa 1990"},
            "Dimensions": {"Height": "12 hands"},
            "Valuations": {"Value": "priceless", "Valuation Type": "Guess"},
        }
    )

    plan = _plan(raw)
    (item,) = plan.items

    assert "acquisition_price" not in item.fields
    assert "acquisition_date" not in item.fields
    assert "height_cm" not in item.fields
    assert item.valuations == []
    notes = _notes(item)
    assert "Amount Paid: €500" in notes["Acquisition"]
    assert "Date: circa 1990" in notes["Acquisition"]
    assert notes["Dimensions"] == "Height: 12 hands"
    assert "Value: priceless" in notes["Valuations"]
    assert {(issue.code, issue.entry) for issue in plan.issues} == {("unread_value", "A-02")}
    assert len(plan.issues) == 3


def test_catalogits_bookkeeping_is_not_imported():
    raw = entry(**{"Created By": "Someone Typing", "Create Date": "2025-07-13"})

    plan = _plan(raw)

    assert plan.items[0].notes == []
    assert {"source": "Created By", "destination": "not imported", "count": 1} in plan.fields.rows()


def test_classification_fields_become_tags_once():
    raw = entry(
        **{
            "Category": ["Porcelain", "porcelain"],
            "Item Type": "Vase",
            "Type of Painting": "Oil",
        }
    )

    assert _plan(raw).items[0].tags == ["Porcelain", "Vase", "Oil"]


def test_inscriptions_become_marks():
    raw = entry(**{"Inscription/Signature/Marks": "Signed lower right\nwith a monogram"})

    (mark,) = _plan(raw).items[0].marks

    assert mark.title == "Signed lower right"
    assert mark.description == "Signed lower right\nwith a monogram"


def test_general_notes_keep_their_type_as_title():
    raw = entry(
        **{"General Notes": [{"Note": "Made for a wedding.", "Note Type": "Historical Note"}]}
    )

    assert _notes(_plan(raw).items[0]) == {"Historical Note": "Made for a wedding."}


def test_long_text_is_shortened_and_kept_whole_in_a_note():
    long_name = " ".join(["Tea caddy"] * 30)
    raw = entry(name=long_name)

    plan = _plan(raw)
    (item,) = plan.items

    assert len(item.fields["name"]) <= 200
    assert _notes(item)["Name/Title"] == long_name
    assert [issue.code for issue in plan.issues] == ["shortened"]


def test_entries_need_an_id_but_not_a_name():
    plan = _plan(
        {"Name/Title": "No id"},
        entry("cit-2", name=None, **{"Entry/Object ID": "B-07"}),
    )

    assert [item.fields["name"] for item in plan.items] == ["B-07"]
    assert {issue.code for issue in plan.issues} == {"no_id", "no_name"}


def test_photos_join_their_entries_in_order():
    plan = _plan(
        entry("cit-1"),
        entry("cit-2", name="Brooch"),
        media=[
            ("cit-1", "a-front.jpg", "Front", ""),
            ("cit-1", "a-base.jpg", "", "The maker's mark on the base"),
            ("cit-2", "b.jpg", "", ""),
            ("cit-9", "orphan.jpg", "", ""),
            ("cit-2", "a-front.jpg", "", ""),
        ],
    )

    first, second = plan.items
    assert [p.filename for p in first.photos] == ["a-front.jpg", "a-base.jpg"]
    assert first.photos[0].caption == "Front"
    assert first.photos[1].description == "The maker's mark on the base"
    assert [p.looks_like_mark for p in first.photos] == [False, True]
    assert [p.filename for p in second.photos] == ["b.jpg"]
    assert {(i.code, i.entry) for i in plan.issues} == {
        ("photo_without_entry", "orphan.jpg"),
        ("duplicate_photo", "a-front.jpg"),
    }


def test_photos_beyond_the_items_limit_are_left_out():
    plan = _plan(entry(), media=[("cit-1", f"p{n}.jpg", "", "") for n in range(12)])

    assert len(plan.items[0].photos) == 10
    assert [issue.code for issue in plan.issues] == ["too_many_photos"]


def test_report_groups_by_reference_prefix_ignoring_case():
    plan = _plan(
        entry("c1", **{"Entry/Object ID": "P-J-01"}),
        entry("c2", **{"Entry/Object ID": "P-J-02"}),
        entry("c3", **{"Entry/Object ID": "P-j-03"}),
        entry("c4", **{"Entry/Object ID": "2019.001.003"}),
        entry("c5", **{"Entry/Object ID": "C-C-32a"}),
    )

    groups = plan.report()["groupings"]["reference_prefix"]

    assert groups == [
        {"key": "P-J", "count": 3},
        {"key": "2019.001", "count": 1},
        {"key": "C-C", "count": 1},
    ]


def test_report_counts_units_and_shared_numbers():
    plan = _plan(
        entry("c1", **{"Entry/Object ID": "A-01", "Dimensions": {"Height": "3 in"}}),
        entry("c2", **{"Entry/Object ID": "A-01"}),
    )

    report = plan.report()

    assert report["units"] == ["imperial"]
    assert report["counts"]["items"] == 2
    assert [(i["code"], i["entry"]) for i in report["issues"]] == [("shared_reference", "A-01")]


def test_reads_the_zip_as_downloaded_and_its_json():
    entries = [entry()]

    assert read_entries(entries_zip(entries)) == entries
    assert read_entries(entries_json(entries)) == entries


@pytest.mark.parametrize(
    "data",
    [b"not json", b'{"a": 1}', b"[1, 2]", entries_json([{"Name/Title": "no ids anywhere"}])],
    ids=["not json", "an object", "not objects", "no CatalogIt ids"],
)
def test_refuses_what_is_not_an_entries_export(data):
    with pytest.raises(ImportFileError):
        read_entries(data)


def test_refuses_a_csv_that_is_not_a_media_index():
    with pytest.raises(ImportFileError):
        read_media_index(b"name,size\nphoto.jpg,1\n")
