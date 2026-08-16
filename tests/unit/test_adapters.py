"""Tests for the built-in adapters and adapter dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from mlcontract import Contract, ContractValidationError, DType, Feature, IntegrationError
from mlcontract.adapters import CsvSource, MappingSource, resolve
from tests._support import requires_no_pandas


def contract(*features: Feature) -> Contract:
    return Contract(name="t", version="1.0.0", features=features)


def write(tmp_path: Any, text: str, name: str = "data.csv") -> Any:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestMappingSource:
    def test_columns_are_the_union_of_keys(self):
        source = MappingSource([{"a": 1}, {"b": 2}])
        assert set(source.column_names()) == {"a", "b"}

    def test_column_order_follows_first_appearance(self):
        source = MappingSource([{"b": 1}, {"a": 2, "b": 3}])
        assert source.column_names() == ("b", "a")

    def test_row_count(self):
        assert MappingSource([{"a": 1}, {"a": 2}]).row_count() == 2

    def test_empty_input(self):
        source = MappingSource([])
        assert source.row_count() == 0
        assert source.column_names() == ()

    def test_absent_key_is_null(self):
        assert MappingSource([{"a": 1}, {}]).null_count("a") == 1

    def test_nan_is_null(self):
        """NaN is how most numeric formats spell "missing"."""
        assert MappingSource([{"a": float("nan")}]).null_count("a") == 1

    def test_iter_values_skips_nulls_and_keeps_row_numbers(self):
        source = MappingSource([{"a": 1}, {"a": None}, {"a": 3}])
        assert list(source.iter_values("a")) == [(0, 1), (2, 3)]

    def test_dtype_inference(self):
        assert MappingSource([{"a": 1}, {"a": 2}]).observed_dtype("a") is DType.INTEGER

    def test_mixed_integers_and_floats_infer_as_float(self):
        assert MappingSource([{"a": 1}, {"a": 2.5}]).observed_dtype("a") is DType.FLOAT

    def test_genuinely_mixed_types_infer_as_unknown(self):
        assert MappingSource([{"a": 1}, {"a": "x"}]).observed_dtype("a") is None

    def test_all_null_column_infers_as_unknown(self):
        assert MappingSource([{"a": None}]).observed_dtype("a") is None

    def test_description_mentions_the_size(self):
        assert "2" in MappingSource([{"a": 1}, {"a": 2}]).describe()


class TestCsvSource:
    def test_reads_header_and_rows(self, tmp_path):
        path = write(tmp_path, "a,b\n1,2\n3,4\n")
        source = CsvSource(path, contract(Feature("a", DType.INTEGER)))
        assert source.column_names() == ("a", "b")
        assert source.row_count() == 2

    def test_integers_are_parsed(self, tmp_path):
        path = write(tmp_path, "a\n1\n2\n")
        source = CsvSource(path, contract(Feature("a", DType.INTEGER)))
        assert source.observed_dtype("a") is DType.INTEGER
        assert list(source.iter_values("a")) == [(0, 1), (1, 2)]

    def test_floats_are_parsed(self, tmp_path):
        path = write(tmp_path, "a\n1.5\n")
        source = CsvSource(path, contract(Feature("a", DType.FLOAT)))
        assert source.observed_dtype("a") is DType.FLOAT

    @pytest.mark.parametrize("text", ["true", "TRUE", "yes", "1"])
    def test_truthy_booleans(self, tmp_path, text):
        path = write(tmp_path, f"a\n{text}\n")
        source = CsvSource(path, contract(Feature("a", DType.BOOLEAN)))
        assert list(source.iter_values("a")) == [(0, True)]

    @pytest.mark.parametrize("text", ["false", "No", "0"])
    def test_falsy_booleans(self, tmp_path, text):
        path = write(tmp_path, f"a\n{text}\n")
        source = CsvSource(path, contract(Feature("a", DType.BOOLEAN)))
        assert list(source.iter_values("a")) == [(0, False)]

    def test_dates_are_parsed(self, tmp_path):
        path = write(tmp_path, "d\n2026-01-31\n")
        source = CsvSource(path, contract(Feature("d", DType.DATE)))
        assert source.observed_dtype("d") is DType.DATE

    def test_empty_field_is_null(self, tmp_path):
        # A wholly blank line is skipped by the CSV reader, so an empty field
        # only exists unambiguously alongside a populated one.
        path = write(tmp_path, "a,b\n1,x\n,y\n")
        source = CsvSource(path, contract(Feature("a", DType.INTEGER)))
        assert source.row_count() == 2
        assert source.null_count("a") == 1

    def test_blank_lines_are_not_rows(self, tmp_path):
        path = write(tmp_path, "a\n1\n\n2\n")
        source = CsvSource(path, contract(Feature("a", DType.INTEGER)))
        assert source.row_count() == 2

    def test_unparseable_value_is_kept_as_text(self, tmp_path):
        """Keeping unparseable text makes the type violation name the culprit."""
        path = write(tmp_path, "a\n1\nabc\n")
        source = CsvSource(path, contract(Feature("a", DType.INTEGER)))
        assert source.observed_dtype("a") is None
        assert (1, "abc") in list(source.iter_values("a"))

    def test_undeclared_column_stays_text(self, tmp_path):
        path = write(tmp_path, "a,extra\n1,x\n")
        source = CsvSource(path, contract(Feature("a", DType.INTEGER)))
        assert list(source.iter_values("extra")) == [(0, "x")]

    def test_description_is_the_filename(self, tmp_path):
        path = write(tmp_path, "a\n1\n", name="customers.csv")
        assert CsvSource(path, contract(Feature("a", DType.INTEGER))).describe() == (
            "customers.csv"
        )

    def test_end_to_end_validation(self, tmp_path):
        path = write(tmp_path, "age,country\n30,IN\n12,FR\n")
        report = contract(
            Feature("age", DType.INTEGER, min=18),
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US"]),
        ).validate(path)
        assert {v.code.code for v in report.violations} == {"MLC203", "MLC205"}


class TestResolve:
    def test_list_of_mappings(self):
        assert isinstance(resolve([{"a": 1}], contract(Feature("a", DType.INTEGER))), MappingSource)

    def test_csv_path(self, tmp_path):
        path = write(tmp_path, "a\n1\n")
        assert isinstance(resolve(path, contract(Feature("a", DType.INTEGER))), CsvSource)

    def test_csv_path_as_a_string(self, tmp_path):
        path = write(tmp_path, "a\n1\n")
        assert isinstance(resolve(str(path), contract(Feature("a", DType.INTEGER))), CsvSource)

    def test_tsv_uses_tab_delimiter(self, tmp_path):
        path = write(tmp_path, "a\tb\n1\t2\n", name="data.tsv")
        source = resolve(path, contract(Feature("a", DType.INTEGER)))
        assert source.column_names() == ("a", "b")

    def test_existing_data_source_passes_through(self):
        source = MappingSource([{"a": 1}])
        assert resolve(source, contract(Feature("a", DType.INTEGER))) is source

    def test_missing_file(self, tmp_path):
        with pytest.raises(ContractValidationError) as exc:
            resolve(tmp_path / "absent.csv", contract(Feature("a", DType.INTEGER)))
        assert exc.value.code.code == "MLC902"

    def test_unsupported_file_extension(self, tmp_path):
        path = write(tmp_path, "a\n1\n", name="data.parquet")
        with pytest.raises(ContractValidationError) as exc:
            resolve(path, contract(Feature("a", DType.INTEGER)))
        assert exc.value.code.code == "MLC902"

    def test_sequence_of_non_mappings(self):
        with pytest.raises(ContractValidationError, match="not every item is a mapping"):
            resolve([1, 2, 3], contract(Feature("a", DType.INTEGER)))

    def test_unsupported_object(self):
        with pytest.raises(ContractValidationError) as exc:
            resolve(42, contract(Feature("a", DType.INTEGER)))
        assert exc.value.code.code == "MLC902"

    @requires_no_pandas
    def test_dataframe_without_the_extra_names_the_extra(self):
        """Duck-typed so the core never imports pandas to detect pandas."""

        class FakeFrame:
            columns = ()
            dtypes = ()
            iloc = ()

        with pytest.raises(IntegrationError) as exc:
            resolve(FakeFrame(), contract(Feature("a", DType.INTEGER)))
        assert 'pip install "mlcontract[pandas]"' in str(exc.value)


class TestCustomAdapter:
    """A third-party adapter needs nothing from this package but the protocol.

    This is the architectural claim Phase 2 rests on: the engine imports no data
    library, so anyone can add a backend by implementing six methods. If that
    ever stops being true, this test breaks.
    """

    class ColumnStore:
        """A column-oriented source, deliberately unlike the built-in adapters."""

        def __init__(self, columns: dict[str, list[Any]]) -> None:
            self._columns = columns

        def describe(self) -> str:
            return "in-memory column store"

        def column_names(self) -> tuple[str, ...]:
            return tuple(self._columns)

        def row_count(self) -> int:
            return max((len(v) for v in self._columns.values()), default=0)

        def observed_dtype(self, column: str) -> DType | None:
            from mlcontract._values import infer

            return infer(self._columns[column])

        def null_count(self, column: str) -> int:
            return sum(1 for v in self._columns[column] if v is None)

        def iter_values(self, column: str) -> Any:
            for index, value in enumerate(self._columns[column]):
                if value is not None:
                    yield index, value

    def test_a_foreign_source_validates(self):
        source = self.ColumnStore({"age": [30, 12]})
        report = contract(Feature("age", DType.INTEGER, min=18)).validate(source)
        assert [v.code.code for v in report.violations] == ["MLC203"]

    def test_the_report_names_the_foreign_source(self):
        source = self.ColumnStore({"age": [30]})
        report = contract(Feature("age", DType.INTEGER)).validate(source)
        assert report.source == "in-memory column store"

    def test_range_checks_tolerate_a_lying_adapter(self):
        """An adapter may lie about dtype; the engine skips rather than raising."""

        class Liar(TestCustomAdapter.ColumnStore):
            def observed_dtype(self, column: str) -> DType | None:
                return DType.FLOAT

        report = contract(Feature("a", DType.FLOAT, min=0)).validate(
            Liar({"a": [1.0, "not a number", -5.0]})
        )
        assert [v.code.code for v in report.violations] == ["MLC203"]


class TestByteOrderMarks:
    """Windows tools write UTF-8 with a BOM by default.

    Excel, Notepad and PowerShell's Out-File all do it. Without handling, the
    mark is absorbed into the first column's name, producing a header like
    "\ufeffid" that silently matches nothing in the contract.
    """

    def test_a_bom_is_stripped_from_the_header(self, tmp_path):
        path = tmp_path / "bom.csv"
        path.write_text("id,age\n1,30\n", encoding="utf-8-sig")
        source = CsvSource(path, contract(Feature("id", DType.INTEGER)))
        assert source.column_names() == ("id", "age")

    def test_data_with_a_bom_validates(self, tmp_path):
        path = tmp_path / "bom.csv"
        path.write_text("id,age\n1,30\n", encoding="utf-8-sig")
        report = contract(Feature("id", DType.INTEGER), Feature("age", DType.INTEGER)).validate(
            path
        )
        assert report.is_valid

    def test_a_file_without_a_bom_is_unaffected(self, tmp_path):
        path = tmp_path / "plain.csv"
        path.write_text("id,age\n1,30\n", encoding="utf-8")
        source = CsvSource(path, contract(Feature("id", DType.INTEGER)))
        assert source.column_names() == ("id", "age")

    def test_non_ascii_content_survives(self, tmp_path):
        path = tmp_path / "bom.csv"
        path.write_text("city\nBengalūru\n", encoding="utf-8-sig")
        source = CsvSource(path, contract(Feature("city", DType.STRING)))
        assert list(source.iter_values("city")) == [(0, "Bengalūru")]
