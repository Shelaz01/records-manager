"""Tests for where scans are filed and how OCR'd names are matched.

Pure functions, so none of this needs a display, a scanner or Tesseract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from records_manager.scanning.filing import (DEFAULT_EXTENSION, names_match,
                                             scan_filename, scans_dir)


class TestScanFilename:
    def test_a_file_with_no_admission_suffix(self) -> None:
        assert scan_filename("00123", None, ".png") == "00123.png"

    def test_the_suffix_keeps_admissions_apart(self) -> None:
        # Without it, a second admission would overwrite the first form.
        assert scan_filename("10619", "2", ".jpg") == "10619_2.jpg"
        assert scan_filename("10619", "3", ".jpg") == "10619_3.jpg"

    def test_two_admissions_never_collide(self) -> None:
        first = scan_filename("10619", "2", ".jpg")
        second = scan_filename("10619", "3", ".jpg")
        assert first != second

    def test_leading_zeros_are_kept(self) -> None:
        assert scan_filename("00042", None, ".png").startswith("00042")

    @pytest.mark.parametrize("extension, expected", [
        (".PNG", ".png"),
        ("png", ".png"),
        (".jpeg", ".jpeg"),
        (".TIF", ".tif"),
    ])
    def test_extensions_are_normalised(self, extension: str,
                                       expected: str) -> None:
        assert scan_filename("1", None, extension).endswith(expected)

    @pytest.mark.parametrize("extension", [".exe", ".pdf", "", ".", "..."])
    def test_an_unknown_extension_falls_back(self, extension: str) -> None:
        assert scan_filename("1", None, extension).endswith(DEFAULT_EXTENSION)

    @pytest.mark.parametrize("number", [
        "../escape", "a/b", "a\\b", "with space", "semi;colon", "..",
    ])
    def test_a_number_cannot_escape_the_folder(self, number: str) -> None:
        name = scan_filename(number, None, ".png")
        assert "/" not in name and "\\" not in name
        assert not name.startswith(".")
        assert Path(name).name == name

    def test_a_suffix_is_sanitised_too(self) -> None:
        assert "/" not in scan_filename("1", "../x", ".png")


class TestScansDir:
    def test_sits_beside_the_database(self, tmp_path: Path) -> None:
        assert scans_dir(tmp_path / "records.db") == tmp_path / "scans"

    def test_follows_a_database_somewhere_else(self, tmp_path: Path) -> None:
        # --db elsewhere keeps its scans with it, rather than in the default
        # folder where they would be orphaned.
        elsewhere = tmp_path / "clinic" / "records.db"
        assert scans_dir(elsewhere) == tmp_path / "clinic" / "scans"


class TestNamesMatch:
    def test_the_same_name_matches(self) -> None:
        assert names_match("Ncube", "Thandiwe", "Ncube", "Thandiwe")

    def test_case_and_spacing_are_ignored(self) -> None:
        assert names_match("Ncube", "Thandiwe", "NCUBE", "  thandiwe ")

    def test_slight_ocr_noise_still_matches(self) -> None:
        # One misread character should not accuse the user of an error.
        assert names_match("Chikowore", "Rufaro", "Chikowore", "Rufara")

    def test_a_different_surname_does_not_match(self) -> None:
        # This is the signal that the hospital number was misread.
        assert not names_match("Ncube", "Thandiwe", "Gumbo", "Tendai")

    def test_a_different_person_entirely(self) -> None:
        assert not names_match("Banda", "Dumisani", "Mutasa", "Yeukai")

    def test_unread_names_are_not_treated_as_a_mismatch(self) -> None:
        # OCR finding nothing is no evidence either way.
        assert names_match("Ncube", "Thandiwe", None, None)
        assert names_match("Ncube", "Thandiwe", "", "")

    def test_a_partial_read_is_judged_on_what_was_read(self) -> None:
        # OCR routinely gets the surname and misses the first names. That
        # must not be reported as the wrong patient.
        assert names_match("Ncube", "Thandiwe", "Ncube", None)
        assert names_match("Ncube", "Thandiwe", None, "Thandiwe")
        assert not names_match("Ncube", "Thandiwe", "Gumbo", None)

    def test_only_part_of_a_first_name_still_matches(self) -> None:
        assert names_match("Gumbo", "Tendai John", "Gumbo", "Tendai")

    def test_a_wrong_first_name_is_caught_even_if_the_surname_fits(self) -> None:
        assert not names_match("Gumbo", "Tendai John", "Gumbo", "Yeukai")

    def test_a_hyphenated_surname_matches_itself(self) -> None:
        assert names_match("Makanda-Ncube", "Ruvarashe",
                           "Makanda-Ncube", "Ruvarashe")

    def test_two_word_first_names_match(self) -> None:
        assert names_match("Gumbo", "Tendai John", "Gumbo", "Tendai John")
