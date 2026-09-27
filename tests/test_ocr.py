"""Tests for the OCR field parser.

``parse_fields`` is a pure function over text, so these run against captured
OCR output in ``tests/fixtures/`` and never need Tesseract installed. The
fixtures are synthetic: they copy the layout of a real admission form but
contain invented names and numbers only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from records_manager.scanning import ocr, scanner

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture
def typical() -> dict[str, str | None]:
    return ocr.parse_fields(read_fixture("typical_form"))


# --------------------------------------------------------------------------- #
# A well-scanned form
# --------------------------------------------------------------------------- #
class TestTypicalForm:
    def test_all_fields_are_found(self, typical) -> None:
        assert typical == {
            "hospital_num": "20481",
            "episode": "20481",
            "episode_suffix": None,
            "surname": "NCUBE",
            "first_names": "THANDIWE",
        }

    def test_values_are_returned_as_read(self, typical) -> None:
        # Forms are filled in capitals; presenting them is the caller's job.
        assert typical["surname"] == "NCUBE"

    def test_first_names_stop_at_the_next_column(self, typical) -> None:
        # The label line continues "Title MS Episode Number 20481".
        assert typical["first_names"] == "THANDIWE"

    def test_the_patients_surname_wins_over_the_next_of_kin(self, typical) -> None:
        # The form repeats "Surname" for the next of kin (MOYO) further down.
        assert typical["surname"] == "NCUBE"

    def test_members_surname_is_not_mistaken_for_the_patients(self, typical) -> None:
        # "Member's Surname SIBANDA" must not match the anchored label.
        assert typical["surname"] != "SIBANDA"

    def test_always_returns_the_same_keys(self, typical) -> None:
        assert set(typical) == {"hospital_num", "episode", "episode_suffix",
                                "surname", "first_names"}


# --------------------------------------------------------------------------- #
# Episode number handling
# --------------------------------------------------------------------------- #
class TestEpisodeNumber:
    def test_the_hospital_number_is_the_base_only(self) -> None:
        # "A10619:2" is file 10619, admission 2. Running them together gives
        # 106192, which is a different patient's file.
        fields = ocr.parse_fields(read_fixture("episode_with_a_prefix"))
        assert fields["hospital_num"] == "10619"

    def test_the_raw_episode_is_kept_for_reference(self) -> None:
        fields = ocr.parse_fields(read_fixture("episode_with_a_prefix"))
        assert fields["episode"] == "A10619:2"

    def test_the_suffix_is_returned_separately(self) -> None:
        # It names the admission, and the scan is filed under it.
        fields = ocr.parse_fields(read_fixture("episode_with_a_prefix"))
        assert fields["episode_suffix"] == "2"

    def test_no_suffix_when_the_number_has_none(self) -> None:
        assert ocr.parse_fields("Episode Number 20481")["episode_suffix"] is None

    def test_only_the_leading_a_is_stripped(self) -> None:
        # The old parser removed every "A", which corrupted names and any
        # number containing the letter.
        fields = ocr.parse_fields(read_fixture("episode_with_a_prefix"))
        assert fields["surname"] == "MAKANDA"
        assert fields["first_names"] == "ANNAH"

    @pytest.mark.parametrize("raw, base, suffix", [
        ("A10619:2", "10619", "2"),
        ("a10619:2", "10619", "2"),
        ("20481", "20481", None),
        ("A20481", "20481", None),
        ("10:2", "10", "2"),
        ("A3071:5", "3071", "5"),
        ("A1A2", "1A2", None),      # only the first A goes
        ("AA123", "A123", None),    # only one A is stripped
        ("50287:12", "50287", "12"),
    ])
    def test_split_episode(self, raw: str, base: str, suffix: str | None) -> None:
        assert ocr.split_episode(raw) == (base, suffix)

    @pytest.mark.parametrize("raw, expected", [
        ("A10619:2", "10619"),
        ("20481", "20481"),
        ("10:2", "10"),
    ])
    def test_hospital_number_uses_the_base(self, raw: str, expected: str) -> None:
        assert ocr.parse_fields(f"Episode Number {raw}")["hospital_num"] == expected

    def test_a_suffix_is_never_folded_into_the_number(self) -> None:
        first = ocr.parse_fields("Episode Number A10619:2")["hospital_num"]
        second = ocr.parse_fields("Episode Number A10619:3")["hospital_num"]
        assert first == second == "10619", \
            "two admissions of one patient are the same file"


class TestDigitConfusions:
    """OCR reads O for 0 and l or I for 1. Correct that, in numbers only."""

    @pytest.mark.parametrize("raw, expected", [
        ("2O481", "20481"),
        ("2o481", "20481"),
        ("l0619", "10619"),
        ("I0619", "10619"),
        ("AIO6I9:2", "10619"),
        ("OOO12", "00012"),
    ])
    def test_letters_are_corrected_in_the_number(self, raw: str,
                                                 expected: str) -> None:
        assert ocr.parse_fields(f"Episode Number {raw}")["hospital_num"] == expected

    def test_leading_zeros_survive_the_correction(self) -> None:
        assert ocr.parse_fields("Episode Number OOl23")["hospital_num"] == "00123"

    @pytest.mark.parametrize("field, name", [
        ("Surname", "IONA"),
        ("First Names", "OLIVIA"),
    ])
    def test_names_are_left_alone(self, field: str, name: str) -> None:
        # "Ian" must not become "1an": the fixups apply to the number only.
        key = "surname" if field == "Surname" else "first_names"
        assert ocr.parse_fields(f"{field} {name}")[key] == name


class TestTitleCase:
    @pytest.mark.parametrize("raw, expected", [
        ("NCUBE", "Ncube"),
        ("TENDAI JOHN", "Tendai John"),
        ("MAKANDA-NCUBE", "Makanda-Ncube"),
        ("THANDIWE", "Thandiwe"),
        ("o'brien", "O'Brien"),
        ("  SPACED   OUT  ", "Spaced Out"),
    ])
    def test_title_case(self, raw: str, expected: str) -> None:
        assert ocr.title_case(raw) == expected

    def test_none_stays_none(self) -> None:
        assert ocr.title_case(None) is None

    def test_parse_fields_itself_stays_raw(self) -> None:
        fields = ocr.parse_fields(read_fixture("typical_form"))
        assert fields["surname"] == "NCUBE", "parsing must not reformat"


class TestCompoundNames:
    def test_two_word_first_names_are_kept_whole(self) -> None:
        fields = ocr.parse_fields(read_fixture("two_word_first_names"))
        assert fields["first_names"] == "TENDAI JOHN"
        assert fields["surname"] == "GUMBO"

    def test_a_hyphenated_surname_survives(self) -> None:
        fields = ocr.parse_fields(read_fixture("hyphenated_surname"))
        assert fields["surname"] == "MAKANDA-NCUBE"
        assert fields["first_names"] == "RUVARASHE"

    def test_a_hyphenated_surname_with_an_episode_suffix(self) -> None:
        fields = ocr.parse_fields(read_fixture("hyphenated_surname"))
        assert fields["hospital_num"] == "50287"
        assert fields["episode"] == "A50287:4"

    def test_compound_names_title_case_correctly(self) -> None:
        fields = ocr.parse_fields(read_fixture("hyphenated_surname"))
        assert ocr.title_case(fields["surname"]) == "Makanda-Ncube"
        names = ocr.parse_fields(read_fixture("two_word_first_names"))
        assert ocr.title_case(names["first_names"]) == "Tendai John"


class TestEpisodeFieldEdgeCases:
    """Abbreviations, bare numbers, and fields with nothing in them."""

    def test_missing_episode_number_is_none(self) -> None:
        assert ocr.parse_fields("Surname NCUBE")["hospital_num"] is None

    def test_episode_no_abbreviation_is_matched(self) -> None:
        assert ocr.parse_fields("Episode No. 20481")["hospital_num"] == "20481"

    def test_a_bare_episode_number_is_matched(self) -> None:
        assert ocr.parse_fields("Episode 20481")["hospital_num"] == "20481"

    def test_an_empty_episode_field_does_not_capture_its_own_label(self) -> None:
        assert ocr.parse_fields("Episode Number")["hospital_num"] is None
        assert ocr.parse_fields("Episode No.")["hospital_num"] is None

    def test_an_empty_episode_field_does_not_reach_the_next_line(self) -> None:
        text = "Episode Number\nOccupation TEACHER"
        assert ocr.parse_fields(text)["hospital_num"] is None


# --------------------------------------------------------------------------- #
# Missing and blank fields
# --------------------------------------------------------------------------- #
class TestMissingFields:
    def test_absent_fields_are_none_not_placeholders(self) -> None:
        fields = ocr.parse_fields(read_fixture("missing_fields"))
        assert fields["first_names"] == "BLESSING"
        assert fields["surname"] is None
        assert fields["hospital_num"] is None

    def test_no_not_found_placeholder_strings(self) -> None:
        # The old parser wrote "Not Found" into the record.
        fields = ocr.parse_fields(read_fixture("missing_fields"))
        assert "Not Found" not in fields.values()

    def test_a_blank_form_yields_all_none(self) -> None:
        fields = ocr.parse_fields(read_fixture("blank_form"))
        assert fields == {"hospital_num": None, "episode": None,
                          "episode_suffix": None, "surname": None,
                          "first_names": None}

    def test_empty_text(self) -> None:
        assert ocr.parse_fields("") == {
            "hospital_num": None, "episode": None, "episode_suffix": None,
            "surname": None, "first_names": None}

    def test_unrelated_text(self) -> None:
        assert ocr.parse_fields("this is not a form at all") == {
            "hospital_num": None, "episode": None, "episode_suffix": None,
            "surname": None, "first_names": None}


# --------------------------------------------------------------------------- #
# Noisy scans
# --------------------------------------------------------------------------- #
class TestNoisyOCR:
    @pytest.fixture
    def noisy(self) -> dict[str, str | None]:
        return ocr.parse_fields(read_fixture("noisy_ocr"))

    def test_fields_survive_a_noisy_scan(self, noisy) -> None:
        assert noisy == {
            "hospital_num": "3071",
            "episode": "A3071:5",
            "episode_suffix": "5",
            "surname": "CHIKOWORE",
            "first_names": "RUFARO",
        }

    def test_trailing_punctuation_is_trimmed(self, noisy) -> None:
        assert noisy["surname"] == "CHIKOWORE", "a trailing '.' must not be kept"

    def test_irregular_spacing_in_the_label(self, noisy) -> None:
        # The fixture reads "Episode  Number   A3071:5" with doubled spaces.
        assert noisy["hospital_num"] == "3071"
        assert noisy["episode"] == "A3071:5"

    def test_runs_of_whitespace_are_collapsed(self) -> None:
        assert ocr.parse_fields("Surname    VAN    DER    BERG")["surname"] \
            == "VAN DER BERG"


# --------------------------------------------------------------------------- #
# Capture boundaries
# --------------------------------------------------------------------------- #
class TestCapturesAreSingleLine:
    def test_a_value_never_runs_onto_the_next_line(self) -> None:
        text = "Surname\nDate of Birth 04/08/1991\nOccupation TEACHER"
        # The old DOTALL pattern swallowed everything up to "Date".
        assert ocr.parse_fields(text)["surname"] is None

    def test_a_label_with_no_value_is_none(self) -> None:
        assert ocr.parse_fields("Surname   \nFirst Names   ")["surname"] is None

    def test_multi_word_first_names_are_kept_whole(self) -> None:
        text = "First Names  MARY JANE  Title MS"
        assert ocr.parse_fields(text)["first_names"] == "MARY JANE"

    def test_the_label_is_matched_case_insensitively(self) -> None:
        assert ocr.parse_fields("SURNAME  NCUBE")["surname"] == "NCUBE"

    def test_an_indented_label_still_matches(self) -> None:
        assert ocr.parse_fields("    Surname  NCUBE")["surname"] == "NCUBE"


# --------------------------------------------------------------------------- #
# Optional dependencies
# --------------------------------------------------------------------------- #
class TestAvailability:
    """The app must import and run whether or not Tesseract is installed."""

    def test_ocr_is_available_returns_a_bool_without_raising(self) -> None:
        assert isinstance(ocr.is_available(), bool)

    def test_scanner_is_available_returns_a_bool_without_raising(self) -> None:
        assert isinstance(scanner.is_available(), bool)

    def test_parse_fields_works_without_tesseract(self) -> None:
        # The whole point of keeping parsing pure: it needs no binary.
        assert ocr.parse_fields("Episode Number 20481")["hospital_num"] == "20481"

class TestUnavailable:
    """The degraded path, exercised whether or not the extras are installed.

    These used to skip on a machine that had Tesseract, which meant the
    behaviour that matters most -- what happens on a machine without it --
    went untested exactly where it was easiest to test.
    """

    @pytest.fixture
    def no_ocr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ocr.DISABLE_ENV, "1")

    @pytest.fixture
    def no_scanner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(scanner.DISABLE_ENV, "1")

    def test_ocr_reports_itself_unavailable(self, no_ocr) -> None:
        assert ocr.is_available() is False

    def test_scanner_reports_itself_unavailable(self, no_scanner) -> None:
        assert scanner.is_available() is False

    def test_extract_text_raises_a_clear_error(self, no_ocr) -> None:
        from PIL import Image
        with pytest.raises(ocr.OCRUnavailableError, match="switched off"):
            ocr.extract_text(Image.new("L", (10, 10)))

    def test_preprocess_raises_a_clear_error(self, no_ocr) -> None:
        from PIL import Image
        with pytest.raises(ocr.OCRUnavailableError, match="switched off"):
            ocr.preprocess(Image.new("L", (10, 10)))

    def test_scan_page_raises_a_clear_error(self, no_scanner) -> None:
        with pytest.raises(scanner.ScannerUnavailableError, match="switched off"):
            scanner.scan_page()

    def test_parsing_still_works_without_tesseract(self, no_ocr) -> None:
        # The whole point of keeping parse_fields pure: reading a form needs
        # Tesseract, but making sense of the text does not.
        fields = ocr.parse_fields(read_fixture("typical_form"))
        assert fields["hospital_num"] == "20481"
        assert fields["surname"] == "NCUBE"

    def test_the_switches_are_independent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Turning OCR off must not claim the scanner is gone too, whatever
        # this particular machine happens to have attached.
        baseline = scanner.is_available()
        monkeypatch.setenv(ocr.DISABLE_ENV, "1")
        assert ocr.is_available() is False
        assert scanner.is_available() is baseline

    def test_availability_returns_when_the_switch_is_cleared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ocr.DISABLE_ENV, "1")
        assert ocr.is_available() is False
        monkeypatch.delenv(ocr.DISABLE_ENV)
        # Back to whatever this machine can actually do.
        assert isinstance(ocr.is_available(), bool)
